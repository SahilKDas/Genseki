#include <windows.h>
#include <windowsx.h>
#include <commdlg.h>
#include <shellapi.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr int kPanelWidth = 318;
constexpr int kToolbarHeight = 34;
constexpr double kRoot3 = 1.7320508075688772;

enum class Color { white, black };
enum class Bug { queen, spider, beetle, grasshopper, ant };
enum class Mode { human, engine };

struct Hex {
    int q = 0;
    int r = 0;
    auto operator<=>(const Hex&) const = default;
};

struct Piece {
    Color color = Color::white;
    Bug bug = Bug::queen;
    int id = 0;
    auto operator<=>(const Piece&) const = default;
};

struct Stack {
    Hex cell{};
    std::vector<Piece> pieces{};
};

enum class MoveKind { placement, movement, pass };

struct Move {
    MoveKind kind = MoveKind::placement;
    std::optional<Hex> from{};
    Hex to{};
    Piece piece{};
    std::wstring uhp{};
};

struct Button {
    int id = 0;
    RECT rect{};
    std::wstring text{};
};

struct BotProfile {
    std::wstring name{};
    int depth = 1;
};

std::wstring widen(std::string_view text) {
    if (text.empty()) return {};
    const int needed = MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0);
    std::wstring out(static_cast<std::size_t>(needed), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), out.data(), needed);
    return out;
}

std::string narrow(std::wstring_view text) {
    if (text.empty()) return {};
    const int needed = WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    std::string out(static_cast<std::size_t>(needed), '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), out.data(), needed, nullptr, nullptr);
    return out;
}

std::vector<std::string> split(std::string_view text, char delimiter) {
    std::vector<std::string> out;
    std::size_t start = 0;
    while (start <= text.size()) {
        const auto end = text.find(delimiter, start);
        out.emplace_back(text.substr(start, end == std::string_view::npos ? text.size() - start : end - start));
        if (end == std::string_view::npos) break;
        start = end + 1;
    }
    return out;
}

std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

Hex add(Hex a, Hex b) { return {a.q + b.q, a.r + b.r}; }

constexpr std::array<Hex, 6> kDirections{{
    {1, 0}, {1, -1}, {0, -1}, {-1, 0}, {-1, 1}, {0, 1},
}};

char color_char(Color color) { return color == Color::white ? 'w' : 'b'; }
std::wstring color_name(Color color) { return color == Color::white ? L"White" : L"Black"; }

char bug_char(Bug bug) {
    switch (bug) {
        case Bug::queen: return 'Q';
        case Bug::spider: return 'S';
        case Bug::beetle: return 'B';
        case Bug::grasshopper: return 'G';
        case Bug::ant: return 'A';
    }
    return '?';
}

std::wstring bug_name(Bug bug) {
    switch (bug) {
        case Bug::queen: return L"Queen";
        case Bug::spider: return L"Spider";
        case Bug::beetle: return L"Beetle";
        case Bug::grasshopper: return L"Grasshopper";
        case Bug::ant: return L"Ant";
    }
    return L"?";
}

std::wstring piece_label(Piece piece) {
    std::wstring out;
    out += color_char(piece.color) == 'w' ? L"W" : L"B";
    out += static_cast<wchar_t>(bug_char(piece.bug));
    if (piece.bug != Bug::queen) out += static_cast<wchar_t>(L'1' + piece.id);
    return out;
}

std::optional<Bug> parse_bug(char value) {
    switch (value) {
        case 'Q': case 'q': return Bug::queen;
        case 'S': case 's': return Bug::spider;
        case 'B': case 'b': return Bug::beetle;
        case 'G': case 'g': return Bug::grasshopper;
        case 'A': case 'a': return Bug::ant;
        default: return std::nullopt;
    }
}

std::optional<Piece> parse_piece(std::string_view text) {
    if (text.size() < 2 || (text[0] != 'w' && text[0] != 'b')) return std::nullopt;
    auto bug = parse_bug(text[1]);
    if (!bug) return std::nullopt;
    int id = 0;
    if (*bug != Bug::queen) {
        if (text.size() != 3 || text[2] < '1' || text[2] > '3') return std::nullopt;
        id = text[2] - '1';
    } else if (text.size() != 2) {
        return std::nullopt;
    }
    return Piece{text[0] == 'w' ? Color::white : Color::black, *bug, id};
}

std::optional<Hex> direction_from_marker(char marker, bool after) {
    if (after) {
        if (marker == '-') return Hex{1, 0};
        if (marker == '/') return Hex{1, -1};
        if (marker == '\\') return Hex{0, 1};
    } else {
        if (marker == '-') return Hex{-1, 0};
        if (marker == '/') return Hex{-1, 1};
        if (marker == '\\') return Hex{0, -1};
    }
    return std::nullopt;
}

class EngineProcess {
public:
    bool start(const std::filesystem::path& path) {
        SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
        HANDLE child_stdout_read = nullptr;
        HANDLE child_stdout_write = nullptr;
        HANDLE child_stdin_read = nullptr;
        HANDLE child_stdin_write = nullptr;
        if (!CreatePipe(&child_stdout_read, &child_stdout_write, &sa, 0)) return false;
        if (!SetHandleInformation(child_stdout_read, HANDLE_FLAG_INHERIT, 0)) return false;
        if (!CreatePipe(&child_stdin_read, &child_stdin_write, &sa, 0)) return false;
        if (!SetHandleInformation(child_stdin_write, HANDLE_FLAG_INHERIT, 0)) return false;

        std::wstring command = L"\"" + path.wstring() + L"\"";
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        si.hStdOutput = child_stdout_write;
        si.hStdError = child_stdout_write;
        si.hStdInput = child_stdin_read;
        PROCESS_INFORMATION pi{};
        const BOOL ok = CreateProcessW(
            nullptr,
            command.data(),
            nullptr,
            nullptr,
            TRUE,
            CREATE_NO_WINDOW,
            nullptr,
            path.parent_path().c_str(),
            &si,
            &pi);
        CloseHandle(child_stdout_write);
        CloseHandle(child_stdin_read);
        if (!ok) {
            CloseHandle(child_stdout_read);
            CloseHandle(child_stdin_write);
            return false;
        }
        process_ = pi.hProcess;
        thread_ = pi.hThread;
        out_ = child_stdout_read;
        in_ = child_stdin_write;
        read_until_ok();
        return true;
    }

    ~EngineProcess() { stop(); }

    void stop() {
        if (in_) {
            send_only("exit");
            CloseHandle(in_);
            in_ = nullptr;
        }
        if (out_) {
            CloseHandle(out_);
            out_ = nullptr;
        }
        if (process_) {
            WaitForSingleObject(process_, 250);
            CloseHandle(process_);
            process_ = nullptr;
        }
        if (thread_) {
            CloseHandle(thread_);
            thread_ = nullptr;
        }
    }

    std::vector<std::string> command(std::string text) {
        send_only(text);
        return read_until_ok();
    }

private:
    void send_only(const std::string& text) {
        std::string line = text + "\n";
        DWORD written = 0;
        WriteFile(in_, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
    }

    std::string read_line() {
        std::string line;
        char ch = 0;
        DWORD read = 0;
        while (ReadFile(out_, &ch, 1, &read, nullptr) && read == 1) {
            if (ch == '\n') break;
            if (ch != '\r') line += ch;
        }
        return line;
    }

    std::vector<std::string> read_until_ok() {
        std::vector<std::string> lines;
        for (;;) {
            auto line = read_line();
            if (line == "ok" || line.empty()) break;
            lines.push_back(line);
        }
        return lines;
    }

    HANDLE process_ = nullptr;
    HANDLE thread_ = nullptr;
    HANDLE in_ = nullptr;
    HANDLE out_ = nullptr;
};

class MirrorBoard {
public:
    bool load_game_string(std::string_view game, std::wstring& error) {
        stacks_.clear();
        history_.clear();
        game_string_ = std::string(game);
        const auto fields = split(game, ';');
        if (fields.empty() || fields[0] != "Base") {
            error = L"Only Base games are supported.";
            return false;
        }
        result_ = fields.size() > 1 ? widen(fields[1]) : L"NotStarted";
        side_ = Color::white;
        if (fields.size() > 2 && fields[2].starts_with("Black")) side_ = Color::black;
        for (std::size_t i = 3; i < fields.size(); ++i) {
            auto move = parse_uhp(fields[i]);
            if (!move) {
                error = L"Could not mirror move: " + widen(fields[i]);
                return false;
            }
            apply(*move);
            history_.push_back(*move);
        }
        return true;
    }

    const std::vector<Stack>& stacks() const { return stacks_; }
    const std::vector<Move>& history() const { return history_; }
    Color side() const { return side_; }
    const std::wstring& result() const { return result_; }
    const std::string& game_string() const { return game_string_; }

    std::vector<Piece> reserve(Color color) const {
        std::array<int, 5> total{1, 2, 2, 3, 3};
        for (const auto& stack : stacks_) {
            for (const auto& piece : stack.pieces) {
                if (piece.color == color) --total[static_cast<int>(piece.bug)];
            }
        }
        std::vector<Piece> out;
        for (int bug = 0; bug < 5; ++bug) {
            for (int i = 0; i < total[bug]; ++i) out.push_back(Piece{color, static_cast<Bug>(bug), i});
        }
        return out;
    }

    const Stack* stack_at(Hex cell) const {
        const auto it = std::find_if(stacks_.begin(), stacks_.end(), [cell](const Stack& stack) { return stack.cell == cell; });
        return it == stacks_.end() ? nullptr : &*it;
    }

    std::optional<Hex> find_piece(Piece piece) const {
        for (const auto& stack : stacks_) {
            if (!stack.pieces.empty() && stack.pieces.back() == piece) return stack.cell;
        }
        return std::nullopt;
    }

private:
    std::optional<Move> parse_uhp(std::string_view text) const {
        if (text == "pass") return Move{MoveKind::pass, std::nullopt, {}, {}, L"pass"};
        const auto space = text.find(' ');
        auto moving = parse_piece(text.substr(0, space));
        if (!moving) return std::nullopt;
        const auto source = find_piece(*moving);
        if (space == std::string_view::npos) {
            return Move{source ? MoveKind::movement : MoveKind::placement, source, {0, 0}, *moving, widen(text)};
        }
        std::string ref_text{text.substr(space + 1)};
        if (ref_text.empty()) return std::nullopt;
        char before = 0;
        char after = 0;
        if (ref_text.front() == '-' || ref_text.front() == '/' || ref_text.front() == '\\') {
            before = ref_text.front();
            ref_text.erase(ref_text.begin());
        }
        if (!ref_text.empty() && (ref_text.back() == '-' || ref_text.back() == '/' || ref_text.back() == '\\')) {
            after = ref_text.back();
            ref_text.pop_back();
        }
        auto ref_piece = parse_piece(ref_text);
        if (!ref_piece) return std::nullopt;
        auto ref_cell = find_any_piece(*ref_piece);
        if (!ref_cell) return std::nullopt;
        Hex destination = *ref_cell;
        if (before) {
            auto direction = direction_from_marker(before, false);
            if (!direction) return std::nullopt;
            destination = add(destination, *direction);
        }
        if (after) {
            auto direction = direction_from_marker(after, true);
            if (!direction) return std::nullopt;
            destination = add(destination, *direction);
        }
        return Move{source ? MoveKind::movement : MoveKind::placement, source, destination, *moving, widen(text)};
    }

    std::optional<Hex> find_any_piece(Piece piece) const {
        for (const auto& stack : stacks_) {
            if (std::find(stack.pieces.begin(), stack.pieces.end(), piece) != stack.pieces.end()) return stack.cell;
        }
        return std::nullopt;
    }

    void apply(const Move& move) {
        if (move.kind == MoveKind::pass) {
            side_ = side_ == Color::white ? Color::black : Color::white;
            return;
        }
        if (move.kind == MoveKind::movement && move.from) {
            auto it = std::find_if(stacks_.begin(), stacks_.end(), [&](const Stack& stack) { return stack.cell == *move.from; });
            if (it != stacks_.end()) {
                it->pieces.pop_back();
                if (it->pieces.empty()) stacks_.erase(it);
            }
        }
        auto target = std::find_if(stacks_.begin(), stacks_.end(), [&](const Stack& stack) { return stack.cell == move.to; });
        if (target == stacks_.end()) stacks_.push_back(Stack{move.to, {move.piece}});
        else target->pieces.push_back(move.piece);
        side_ = side_ == Color::white ? Color::black : Color::white;
    }

    std::vector<Stack> stacks_{};
    std::vector<Move> history_{};
    Color side_ = Color::white;
    std::wstring result_ = L"NotStarted";
    std::string game_string_ = "Base";
};

class App {
public:
    int run(HINSTANCE instance, int show, std::filesystem::path engine_path) {
        instance_ = instance;
        engine_path_ = std::move(engine_path);
        WNDCLASSW wc{};
        wc.lpfnWndProc = App::window_proc;
        wc.hInstance = instance_;
        wc.lpszClassName = L"GensekiWin32Gui";
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
        RegisterClassW(&wc);
        hwnd_ = CreateWindowExW(
            0,
            wc.lpszClassName,
            L"Genseki - Native Hive GUI",
            WS_OVERLAPPEDWINDOW,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            1220,
            780,
            nullptr,
            nullptr,
            instance_,
            this);
        if (!hwnd_) return 1;
        ShowWindow(hwnd_, show);
        UpdateWindow(hwnd_);
        MSG msg{};
        while (GetMessageW(&msg, nullptr, 0, 0)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        return static_cast<int>(msg.wParam);
    }

private:
    static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
        App* app = nullptr;
        if (message == WM_NCCREATE) {
            app = static_cast<App*>(reinterpret_cast<CREATESTRUCTW*>(lparam)->lpCreateParams);
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(app));
            app->hwnd_ = hwnd;
        } else {
            app = reinterpret_cast<App*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
        }
        return app ? app->handle(message, wparam, lparam) : DefWindowProcW(hwnd, message, wparam, lparam);
    }

    LRESULT handle(UINT message, WPARAM wparam, LPARAM lparam) {
        switch (message) {
            case WM_CREATE:
                on_create();
                return 0;
            case WM_SIZE:
                layout();
                InvalidateRect(hwnd_, nullptr, TRUE);
                return 0;
            case WM_TIMER:
                maybe_engine_move();
                InvalidateRect(hwnd_, nullptr, FALSE);
                return 0;
            case WM_LBUTTONDOWN:
                on_left_down(GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam));
                return 0;
            case WM_LBUTTONUP:
                dragging_ = false;
                ReleaseCapture();
                return 0;
            case WM_MOUSEMOVE:
                on_mouse_move(GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam), (wparam & MK_LBUTTON) != 0);
                return 0;
            case WM_MOUSEWHEEL:
                on_wheel(GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam), GET_WHEEL_DELTA_WPARAM(wparam));
                return 0;
            case WM_COMMAND:
                on_command(LOWORD(wparam));
                return 0;
            case WM_PAINT:
                paint();
                return 0;
            case WM_DESTROY:
                KillTimer(hwnd_, 1);
                engine_.stop();
                PostQuitMessage(0);
                return 0;
        }
        return DefWindowProcW(hwnd_, message, wparam, lparam);
    }

    void on_create() {
        if (!engine_.start(engine_path_)) {
            status_ = L"Engine launch failed: " + engine_path_.wstring();
        } else {
            status_ = L"Engine ready";
            send_newgame("Base");
            send_options();
        }
        SetTimer(hwnd_, 1, 250, nullptr);
        layout();
    }

    void layout() {
        RECT rc{};
        GetClientRect(hwnd_, &rc);
        toolbar_ = {0, 0, rc.right, kToolbarHeight};
        board_rect_ = {0, kToolbarHeight, rc.right - kPanelWidth, rc.bottom};
        panel_rect_ = {rc.right - kPanelWidth, kToolbarHeight, rc.right, rc.bottom};
        buttons_.clear();
        int x = 6;
        add_button(101, x, 4, 76, L"New"); x += 82;
        add_button(102, x, 4, 70, L"Undo"); x += 76;
        add_button(103, x, 4, 86, L"Load UHP"); x += 92;
        add_button(104, x, 4, 96, L"Engine Now"); x += 104;
        add_button(105, x, 4, 98, L"White Bot"); x += 104;
        add_button(106, x, 4, 98, L"Black Bot"); x += 104;
        add_button(107, x, 4, 96, L"Both Bots"); x += 102;
        add_button(108, x, 4, 88, L"Greek");
    }

    void add_button(int id, int x, int y, int width, std::wstring text) {
        buttons_.push_back(Button{id, {x, y, x + width, y + 26}, std::move(text)});
    }

    void send_options() {
        const auto lines = engine_.command("options");
        if (!lines.empty()) status_ = widen(lines.front());
    }

    void send_newgame(const std::string& game) {
        selected_.reset();
        legal_.clear();
        auto lines = engine_.command("newgame " + game);
        consume_engine_response(lines);
        refresh_legal();
        white_elapsed_ = black_elapsed_ = std::chrono::seconds{0};
        last_tick_ = std::chrono::steady_clock::now();
    }

    void consume_engine_response(const std::vector<std::string>& lines) {
        for (const auto& line : lines) {
            if (line.starts_with("err ")) status_ = widen(line);
            else if (line.starts_with("invalidmove ")) status_ = widen(line);
            else if (line.starts_with("Base")) {
                std::wstring error;
                if (!board_.load_game_string(line, error)) status_ = error;
                else status_ = L"Position loaded";
            } else {
                status_ = widen(line);
            }
        }
    }

    void refresh_legal() {
        legal_.clear();
        auto lines = engine_.command("validmoves");
        for (const auto& line : lines) {
            if (line.starts_with("err ")) {
                status_ = widen(line);
                continue;
            }
            for (const auto& token : split(line, ';')) {
                if (token.empty()) continue;
                MirrorBoard mirror = board_;
                auto before = mirror.history().size();
                std::string game = board_.game_string();
                legal_.push_back(parse_legal_token(token));
                legal_.back().uhp = widen(token);
                (void)before;
            }
        }
        status_ = L"Legal moves: " + std::to_wstring(legal_.size());
    }

    Move parse_legal_token(const std::string& token) const {
        MirrorBoard mirror = board_;
        std::string synthetic = board_.game_string();
        if (synthetic == "Base") synthetic = "Base;NotStarted;White[1]";
        synthetic += ";" + token;
        std::wstring error;
        if (mirror.load_game_string(synthetic, error) && !mirror.history().empty()) {
            return mirror.history().back();
        }
        return Move{MoveKind::pass, std::nullopt, {}, {}, widen(token)};
    }

    void play_move(const std::wstring& uhp) {
        selected_.reset();
        const std::string command = uhp == L"pass" ? "pass" : "play " + narrow(uhp);
        consume_engine_response(engine_.command(command));
        refresh_legal();
    }

    void maybe_engine_move() {
        const auto now = std::chrono::steady_clock::now();
        const auto delta = std::chrono::duration_cast<std::chrono::seconds>(now - last_tick_);
        if (delta.count() > 0) {
            if (board_.side() == Color::white) white_elapsed_ += delta;
            else black_elapsed_ += delta;
            last_tick_ = now;
        }
        const Mode mode = board_.side() == Color::white ? white_mode_ : black_mode_;
        if (mode == Mode::engine && !thinking_ && board_.result() == L"InProgress") {
            thinking_ = true;
            status_ = L"Engine thinking (" + bot_name() + L")";
            auto lines = engine_.command("bestmove depth " + std::to_string(bot_profiles_[bot_index_].depth));
            if (!lines.empty() && !lines.front().starts_with("err ")) play_move(widen(lines.front()));
            thinking_ = false;
        }
    }

    POINT hex_to_point(Hex cell) const {
        const double x = origin_x_ + size_ * (1.5 * cell.q);
        const double y = origin_y_ + size_ * ((kRoot3 / 2.0) * cell.q + kRoot3 * cell.r);
        return {static_cast<LONG>(std::lround(x)), static_cast<LONG>(std::lround(y))};
    }

    Hex point_to_hex(int x, int y) const {
        const double px = (x - origin_x_) / size_;
        const double py = (y - origin_y_) / size_;
        const double qf = (2.0 / 3.0) * px;
        const double rf = (-1.0 / 3.0) * px + (kRoot3 / 3.0) * py;
        return round_hex(qf, rf);
    }

    static Hex round_hex(double q, double r) {
        double x = q;
        double z = r;
        double y = -x - z;
        int rx = static_cast<int>(std::round(x));
        int ry = static_cast<int>(std::round(y));
        int rz = static_cast<int>(std::round(z));
        const double dx = std::abs(rx - x);
        const double dy = std::abs(ry - y);
        const double dz = std::abs(rz - z);
        if (dx > dy && dx > dz) rx = -ry - rz;
        else if (dy > dz) ry = -rx - rz;
        else rz = -rx - ry;
        return {rx, rz};
    }

    void on_left_down(int x, int y) {
        for (const auto& button : buttons_) {
            if (PtInRect(&button.rect, {x, y})) {
                SendMessageW(hwnd_, WM_COMMAND, button.id, 0);
                return;
            }
        }
        if (x >= panel_rect_.left) {
            handle_panel_click(x, y);
            return;
        }
        Hex cell = point_to_hex(x, y);
        if (selected_) {
            auto it = std::find_if(legal_.begin(), legal_.end(), [&](const Move& move) {
                return move.piece == selected_->piece && move.to == cell
                    && ((!selected_->from && move.kind == MoveKind::placement) || move.from == selected_->from);
            });
            if (it != legal_.end()) {
                play_move(it->uhp);
                InvalidateRect(hwnd_, nullptr, TRUE);
                return;
            }
        }
        if (const auto* stack = board_.stack_at(cell); stack && !stack->pieces.empty()) {
            Piece top = stack->pieces.back();
            if (top.color == board_.side()) {
                selected_ = Move{MoveKind::movement, cell, {}, top, {}};
                status_ = L"Selected " + piece_label(top);
                InvalidateRect(hwnd_, nullptr, TRUE);
                return;
            }
        }
        dragging_ = true;
        last_mouse_ = {x, y};
        SetCapture(hwnd_);
    }

    void handle_panel_click(int x, int y) {
        for (const auto& hit : reserve_hits_) {
            if (PtInRect(&hit.first, {x, y})) {
                selected_ = Move{MoveKind::placement, std::nullopt, {}, hit.second, {}};
                status_ = L"Selected reserve " + piece_label(hit.second);
                InvalidateRect(hwnd_, nullptr, TRUE);
                return;
            }
        }
    }

    void on_mouse_move(int x, int y, bool left_down) {
        if (dragging_ && left_down) {
            origin_x_ += x - last_mouse_.x;
            origin_y_ += y - last_mouse_.y;
            last_mouse_ = {x, y};
            InvalidateRect(hwnd_, nullptr, FALSE);
        }
    }

    void on_wheel(int screen_x, int screen_y, int delta) {
        POINT client{screen_x, screen_y};
        ScreenToClient(hwnd_, &client);
        const double old = size_;
        size_ = std::clamp(size_ * (delta > 0 ? 1.12 : 0.89), 18.0, 88.0);
        const double scale = size_ / old;
        origin_x_ = client.x - (client.x - origin_x_) * scale;
        origin_y_ = client.y - (client.y - origin_y_) * scale;
        InvalidateRect(hwnd_, nullptr, FALSE);
    }

    void on_command(int id) {
        if (id == 101) send_newgame("Base");
        if (id == 102) {
            consume_engine_response(engine_.command("undo 1"));
            refresh_legal();
        }
        if (id == 103) load_game_dialog();
        if (id == 104) maybe_engine_once();
        if (id == 105) white_mode_ = white_mode_ == Mode::human ? Mode::engine : Mode::human;
        if (id == 106) black_mode_ = black_mode_ == Mode::human ? Mode::engine : Mode::human;
        if (id == 107) {
            white_mode_ = Mode::engine;
            black_mode_ = Mode::engine;
        }
        if (id == 108) {
            bot_index_ = (bot_index_ + 1) % bot_profiles_.size();
            status_ = L"Selected " + bot_name();
        }
        InvalidateRect(hwnd_, nullptr, TRUE);
    }

    void maybe_engine_once() {
        auto lines = engine_.command("bestmove depth " + std::to_string(bot_profiles_[bot_index_].depth));
        if (!lines.empty() && !lines.front().starts_with("err ")) play_move(widen(lines.front()));
        else consume_engine_response(lines);
    }

    void load_game_dialog() {
        wchar_t buffer[4096] = L"Base;NotStarted;White[1]";
        const int result = MessageBoxW(hwnd_, L"Paste a UHP game string into the next input box is not available in raw Win32 here. Load the current clipboard text?", L"Load UHP", MB_OKCANCEL);
        if (result != IDOK) return;
        if (OpenClipboard(hwnd_)) {
            HANDLE data = GetClipboardData(CF_UNICODETEXT);
            if (data) {
                auto* text = static_cast<const wchar_t*>(GlobalLock(data));
                if (text) {
                    wcsncpy_s(buffer, text, _TRUNCATE);
                    GlobalUnlock(data);
                }
            }
            CloseClipboard();
        }
        send_newgame(narrow(buffer));
    }

    void paint() {
        PAINTSTRUCT ps{};
        HDC hdc = BeginPaint(hwnd_, &ps);
        RECT rc{};
        GetClientRect(hwnd_, &rc);
        HBRUSH bg = CreateSolidBrush(RGB(238, 238, 234));
        FillRect(hdc, &rc, bg);
        DeleteObject(bg);
        paint_toolbar(hdc);
        paint_board(hdc);
        paint_panel(hdc);
        EndPaint(hwnd_, &ps);
    }

    void paint_toolbar(HDC hdc) {
        HBRUSH brush = CreateSolidBrush(RGB(222, 222, 218));
        FillRect(hdc, &toolbar_, brush);
        DeleteObject(brush);
        SetBkMode(hdc, TRANSPARENT);
        for (const auto& button : buttons_) {
            Rectangle(hdc, button.rect.left, button.rect.top, button.rect.right, button.rect.bottom);
            DrawTextW(hdc, button.text.c_str(), -1, const_cast<RECT*>(&button.rect), DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
        RECT bot{760, 5, toolbar_.right - 10, 28};
        std::wstring modes = L"White: " + mode_name(white_mode_) + L"   Black: " + mode_name(black_mode_) + L"   Bot: " + bot_name();
        DrawTextW(hdc, modes.c_str(), -1, &bot, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    }

    std::wstring mode_name(Mode mode) const { return mode == Mode::human ? L"Human" : L"Engine"; }

    std::wstring bot_name() const {
        return bot_profiles_[bot_index_].name + L" d" + std::to_wstring(bot_profiles_[bot_index_].depth);
    }

    void paint_board(HDC hdc) {
        HBRUSH board_bg = CreateSolidBrush(RGB(248, 247, 242));
        FillRect(hdc, &board_rect_, board_bg);
        DeleteObject(board_bg);
        HRGN clip = CreateRectRgn(board_rect_.left, board_rect_.top, board_rect_.right, board_rect_.bottom);
        SelectClipRgn(hdc, clip);
        paint_legal(hdc);
        for (const auto& stack : board_.stacks()) paint_stack(hdc, stack);
        SelectClipRgn(hdc, nullptr);
        DeleteObject(clip);
    }

    void polygon_for_hex(POINT center, POINT out[6], double radius) const {
        for (int i = 0; i < 6; ++i) {
            const double angle = (60.0 * i) * 3.141592653589793 / 180.0;
            out[i] = {
                static_cast<LONG>(std::lround(center.x + radius * std::cos(angle))),
                static_cast<LONG>(std::lround(center.y + radius * std::sin(angle))),
            };
        }
    }

    void paint_legal(HDC hdc) {
        HBRUSH brush = CreateSolidBrush(RGB(191, 216, 151));
        HPEN pen = CreatePen(PS_SOLID, 1, RGB(102, 134, 65));
        auto old_brush = SelectObject(hdc, brush);
        auto old_pen = SelectObject(hdc, pen);
        std::set<Hex> destinations;
        for (const auto& move : legal_) {
            if (!selected_ || move.piece != selected_->piece) continue;
            if (selected_->from != move.from) continue;
            destinations.insert(move.to);
        }
        for (const auto& cell : destinations) {
            POINT center = hex_to_point(cell);
            Ellipse(hdc, center.x - 7, center.y - 7, center.x + 7, center.y + 7);
        }
        SelectObject(hdc, old_brush);
        SelectObject(hdc, old_pen);
        DeleteObject(brush);
        DeleteObject(pen);
    }

    void paint_stack(HDC hdc, const Stack& stack) {
        POINT center = hex_to_point(stack.cell);
        POINT points[6]{};
        polygon_for_hex(center, points, size_ * 0.82);
        const Piece top = stack.pieces.back();
        const COLORREF fill = top.color == Color::white ? RGB(246, 246, 238) : RGB(58, 60, 62);
        const COLORREF edge = selected_ && selected_->from == stack.cell ? RGB(40, 120, 190) : RGB(56, 56, 50);
        HBRUSH brush = CreateSolidBrush(fill);
        HPEN pen = CreatePen(PS_SOLID, selected_ && selected_->from == stack.cell ? 3 : 1, edge);
        auto old_brush = SelectObject(hdc, brush);
        auto old_pen = SelectObject(hdc, pen);
        Polygon(hdc, points, 6);
        SelectObject(hdc, old_brush);
        SelectObject(hdc, old_pen);
        DeleteObject(brush);
        DeleteObject(pen);
        SetBkMode(hdc, TRANSPARENT);
        SetTextColor(hdc, top.color == Color::white ? RGB(20, 20, 20) : RGB(245, 245, 240));
        RECT label{center.x - 32, center.y - 12, center.x + 32, center.y + 12};
        const auto text = piece_label(top);
        DrawTextW(hdc, text.c_str(), -1, &label, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        if (stack.pieces.size() > 1) {
            RECT badge{center.x + 16, center.y + 12, center.x + 44, center.y + 30};
            const auto height = L"x" + std::to_wstring(stack.pieces.size());
            SetTextColor(hdc, RGB(20, 20, 20));
            DrawTextW(hdc, height.c_str(), -1, &badge, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
    }

    void paint_panel(HDC hdc) {
        HBRUSH panel = CreateSolidBrush(RGB(232, 232, 226));
        FillRect(hdc, &panel_rect_, panel);
        DeleteObject(panel);
        SetBkMode(hdc, TRANSPARENT);
        int y = panel_rect_.top + 10;
        draw_line(hdc, 10, y, L"Side: " + color_name(board_.side())); y += 22;
        draw_line(hdc, 10, y, L"Result: " + board_.result()); y += 22;
        draw_line(hdc, 10, y, L"Clock W/B: " + clock_text(white_elapsed_) + L" / " + clock_text(black_elapsed_)); y += 22;
        draw_line(hdc, 10, y, L"Status: " + status_); y += 22;
        draw_line(hdc, 10, y, L"Greek: " + bot_name()); y += 42;
        draw_reserve(hdc, y, Color::white); y += 96;
        draw_reserve(hdc, y, Color::black); y += 104;
        draw_line(hdc, 10, y, L"Legal destinations: " + std::to_wstring(legal_.size())); y += 24;
        draw_line(hdc, 10, y, L"Move history"); y += 22;
        RECT hist{panel_rect_.left + 10, y, panel_rect_.right - 10, panel_rect_.bottom - 10};
        std::wstring text;
        int n = 1;
        for (const auto& move : board_.history()) {
            text += std::to_wstring(n++) + L". " + move.uhp + L"\r\n";
        }
        DrawTextW(hdc, text.c_str(), -1, &hist, DT_LEFT | DT_TOP | DT_NOPREFIX);
    }

    std::wstring clock_text(std::chrono::seconds seconds) const {
        const auto total = seconds.count();
        wchar_t buffer[32]{};
        swprintf_s(buffer, L"%02lld:%02lld", total / 60, total % 60);
        return buffer;
    }

    void draw_line(HDC hdc, int x, int y, const std::wstring& text) {
        RECT line{panel_rect_.left + x, y, panel_rect_.right - 10, y + 20};
        DrawTextW(hdc, text.c_str(), -1, &line, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    }

    void draw_reserve(HDC hdc, int y, Color color) {
        draw_line(hdc, 10, y, color_name(color) + L" reserve");
        y += 24;
        auto pieces = board_.reserve(color);
        int x = panel_rect_.left + 10;
        if (color == Color::white) reserve_hits_.clear();
        for (const auto& piece : pieces) {
            RECT rc{x, y, x + 48, y + 28};
            HBRUSH brush = CreateSolidBrush(piece.color == Color::white ? RGB(250, 250, 244) : RGB(65, 67, 70));
            FillRect(hdc, &rc, brush);
            DeleteObject(brush);
            Rectangle(hdc, rc.left, rc.top, rc.right, rc.bottom);
            SetTextColor(hdc, piece.color == Color::white ? RGB(10, 10, 10) : RGB(250, 250, 245));
            auto label = piece_label(piece);
            DrawTextW(hdc, label.c_str(), -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            reserve_hits_.push_back({rc, piece});
            x += 54;
            if (x + 48 > panel_rect_.right - 8) {
                x = panel_rect_.left + 10;
                y += 34;
            }
        }
        SetTextColor(hdc, RGB(0, 0, 0));
    }

    HINSTANCE instance_ = nullptr;
    HWND hwnd_ = nullptr;
    std::filesystem::path engine_path_{L"genseki.exe"};
    EngineProcess engine_{};
    MirrorBoard board_{};
    RECT toolbar_{};
    RECT board_rect_{};
    RECT panel_rect_{};
    std::vector<Button> buttons_{};
    std::vector<Move> legal_{};
    std::vector<std::pair<RECT, Piece>> reserve_hits_{};
    std::optional<Move> selected_{};
    std::wstring status_ = L"Starting";
    std::array<BotProfile, 24> bot_profiles_{{
        {L"Alpha handcrafted", 1},
        {L"Beta handcrafted", 2},
        {L"Gamma NNUE", 1},
        {L"Delta NNUE", 2},
        {L"Epsilon dense", 1},
        {L"Zeta dense", 2},
        {L"Eta convolutional", 1},
        {L"Theta convolutional", 2},
        {L"Iota handcrafted", 3},
        {L"Kappa NNUE", 3},
        {L"Lambda dense", 3},
        {L"Mu convolutional", 3},
        {L"Nu handcrafted", 4},
        {L"Xi NNUE", 4},
        {L"Omicron dense", 4},
        {L"Pi convolutional", 4},
        {L"Rho handcrafted", 5},
        {L"Sigma NNUE", 5},
        {L"Tau dense", 5},
        {L"Upsilon convolutional", 5},
        {L"Phi handcrafted", 6},
        {L"Chi NNUE", 6},
        {L"Psi dense", 6},
        {L"Omega convolutional", 6},
    }};
    std::size_t bot_index_ = 0;
    Mode white_mode_ = Mode::human;
    Mode black_mode_ = Mode::human;
    bool thinking_ = false;
    bool dragging_ = false;
    POINT last_mouse_{};
    double size_ = 38.0;
    double origin_x_ = 390.0;
    double origin_y_ = 330.0;
    std::chrono::seconds white_elapsed_{0};
    std::chrono::seconds black_elapsed_{0};
    std::chrono::steady_clock::time_point last_tick_ = std::chrono::steady_clock::now();
};

std::filesystem::path default_engine_path(wchar_t* exe) {
    std::filesystem::path path = exe;
    auto sibling = path.parent_path() / L"genseki.exe";
    if (std::filesystem::exists(sibling)) return sibling;
    return L"genseki.exe";
}

}  // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR command_line, int show) {
    (void)command_line;
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::filesystem::path engine = argc > 1 ? std::filesystem::path(argv[1]) : default_engine_path(argv[0]);
    if (argv) LocalFree(argv);
    App app;
    return app.run(instance, show, engine);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show) {
    (void)previous;
    (void)command_line;
    return wWinMain(instance, nullptr, GetCommandLineW(), show);
}
