#include <windows.h>
#include <windowsx.h>
#include <commdlg.h>
#include <shellapi.h>
#include <mmsystem.h>

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
#include <cstring>
#include <future>
#include <fstream>
#include "tiny_raster.hpp"
#include "audio_player.hpp"
#include "svg_icons.hpp"
#include "review_window.hpp"

namespace {

constexpr int kPanelWidth = 360;
constexpr int kToolbarHeight = 94;
constexpr double kRoot3 = 1.7320508075688772;

class BundledNunito {
    HANDLE handle_=nullptr;
public:
    BundledNunito() {
        auto instance=GetModuleHandleW(nullptr);
        auto resource=FindResourceW(instance,MAKEINTRESOURCEW(701),RT_RCDATA);
        if(resource) {
            auto bytes=LockResource(LoadResource(instance,resource));DWORD count=0;
            handle_=AddFontMemResourceEx(bytes,SizeofResource(instance,resource),nullptr,&count);
        }
    }
    ~BundledNunito(){if(handle_)RemoveFontMemResourceEx(handle_);}
    bool ready()const{return handle_!=nullptr;}
};
BundledNunito& nunito(){static BundledNunito font;return font;}

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
    bool connected() const { return in_ && out_ && process_; }

    bool start(const std::filesystem::path& path) {
        SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
        HANDLE child_stdout_read = nullptr;
        HANDLE child_stdout_write = nullptr;
        HANDLE child_stdin_read = nullptr;
        HANDLE child_stdin_write = nullptr;
        const auto cleanup_pipes = [&] {
            for (HANDLE handle : {child_stdout_read, child_stdout_write,
                                  child_stdin_read, child_stdin_write}) {
                if (handle) CloseHandle(handle);
            }
        };
        if (!CreatePipe(&child_stdout_read, &child_stdout_write, &sa, 0)) return false;
        if (!SetHandleInformation(child_stdout_read, HANDLE_FLAG_INHERIT, 0)) { cleanup_pipes(); return false; }
        if (!CreatePipe(&child_stdin_read, &child_stdin_write, &sa, 0)) { cleanup_pipes(); return false; }
        if (!SetHandleInformation(child_stdin_write, HANDLE_FLAG_INHERIT, 0)) { cleanup_pipes(); return false; }

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
        auto startup=read_until_ok();
        if(startup.empty()||startup.back().starts_with("err ")){stop();return false;}
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
            if (WaitForSingleObject(process_, 250) == WAIT_TIMEOUT) {
                TerminateProcess(process_, 1);
                WaitForSingleObject(process_, INFINITE);
            }
            CloseHandle(process_);
            process_ = nullptr;
        }
        if (thread_) {
            CloseHandle(thread_);
            thread_ = nullptr;
        }
    }

    std::vector<std::string> command(std::string text) {
        if (!in_ || !out_) return {"err Engine connection is closed; restart the engine"};
        send_only(text);
        return read_until_ok();
    }

private:
    void send_only(const std::string& text) {
        std::string line = text + "\n";
        DWORD written = 0;
        WriteFile(in_, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
    }

    std::optional<std::string> read_line(ULONGLONG deadline) {
        std::string line;
        char ch = 0;
        DWORD read = 0;
        for (;;) {
            if(GetTickCount64()>=deadline)return std::nullopt;
            DWORD available=0;if(!PeekNamedPipe(out_,nullptr,0,nullptr,&available,nullptr))return std::nullopt;
            if(!available){Sleep(1);continue;}
            if(!ReadFile(out_,&ch,1,&read,nullptr)||read!=1)return std::nullopt;
            if (ch == '\n') break;
            if (ch != '\r') line += ch;
            if(line.size()>1024*1024)return std::nullopt;
        }
        return line;
    }

    std::vector<std::string> read_until_ok() {
        std::vector<std::string> lines;
        std::size_t bytes=0;
        const auto deadline=GetTickCount64()+5000;
        for (;;) {
            auto line = read_line(deadline);
            if(!line){
                lines.push_back("err Engine response deadline or pipe failure; restart the engine");
                stop();
                break;
            }
            bytes+=line->size()+1;
            if (bytes>1024*1024 || lines.size()>=256) {
                stop();
                return {"err Engine output limit exceeded; restart the engine"};
            }
            if (*line == "ok") break;
            if(!line->empty())lines.push_back(*line);
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
        constexpr std::array<int, 5> total{1, 2, 2, 3, 3};
        std::vector<Piece> out;
        for (int bug = 0; bug < 5; ++bug) {
            for (int i = 0; i < total[bug]; ++i) {
                Piece piece{color, static_cast<Bug>(bug), i};
                if (!find_piece(piece)) out.push_back(piece);
            }
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

using SpectatorFrame = std::array<std::string,7>;

std::optional<SpectatorFrame> read_spectator_frame(const std::filesystem::path& path) {
    std::error_code error;
    const auto bytes=std::filesystem::file_size(path,error);
    if(error||bytes>1024*1024)return std::nullopt;
    std::ifstream input(path,std::ios::binary);
    SpectatorFrame lines;
    for(auto& line:lines) {
        if(!std::getline(input,line))return std::nullopt;
        if(!line.empty()&&line.back()=='\r')line.pop_back();
    }
    if(lines[0]!="GENSEKI_SPECTATOR_V1")return std::nullopt;
    return lines;
}

class App {
public:
    static int gui_layout_smoke(HINSTANCE instance) {
        App app;
        app.hwnd_=CreateWindowExW(0,L"STATIC",L"GUI layout test",WS_OVERLAPPEDWINDOW,
                                 0,0,1220,780,nullptr,nullptr,instance,nullptr);
        if (!app.hwnd_) return 40;
        HFONT font=CreateFontW(-16,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Nunito");
        HDC dc=GetDC(app.hwnd_);
        if (!font || !dc) {
            if (font) DeleteObject(font);
            if (dc) ReleaseDC(app.hwnd_,dc);
            DestroyWindow(app.hwnd_);return 40;
        }
        const auto old_font=SelectObject(dc,font);
        int result=0;
        for (int width : {1000,1220,1600}) {
            RECT requested{0,0,width,720};
            AdjustWindowRectEx(&requested,WS_OVERLAPPEDWINDOW,FALSE,0);
            SetWindowPos(app.hwnd_,nullptr,0,0,requested.right-requested.left,
                         requested.bottom-requested.top,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
            app.layout();
            for (std::size_t i=0;i<app.buttons_.size();++i) {
                const auto& button=app.buttons_[i];
                SIZE text{};
                GetTextExtentPoint32W(dc,button.text.c_str(),int(button.text.size()),&text);
                if (button.rect.left<0 || button.rect.right>width || button.rect.bottom>app.toolbar_.bottom
                    || text.cx>button.rect.right-button.rect.left-8) result=41;
                for (std::size_t j=i+1;j<app.buttons_.size();++j) {
                    RECT overlap{};
                    if (IntersectRect(&overlap,&button.rect,&app.buttons_[j].rect)) result=42;
                }
            }
        }
        SelectObject(dc,old_font);DeleteObject(font);ReleaseDC(app.hwnd_,dc);
        DestroyWindow(app.hwnd_);
        return result;
    }

    static int gui_state_smoke(const std::filesystem::path& replay_file) {
        App app;
        if (app.button_enabled(102) || app.button_enabled(114)) return 30;
        const auto check_inventory = [](const MirrorBoard& board) {
            constexpr std::array<int, 5> totals{1,2,2,3,3};
            for (Color color : {Color::white, Color::black}) {
                const auto reserve = board.reserve(color);
                for (int bug=0;bug<5;++bug) for (int id=0;id<totals[bug];++id) {
                    const Piece piece{color,static_cast<Bug>(bug),id};
                    const auto count=std::count(reserve.begin(),reserve.end(),piece);
                    if (count != (board.find_piece(piece)?0:1)) return false;
                }
            }
            return true;
        };
        std::wstring error;
        const std::string opening="Base;InProgress;White[3];wA1;bA1 wA1-;wS1 -wA1;bS1 bA1-";
        if (!genseki::review::prepare(opening) || !app.board_.load_game_string(opening,error)) return 31;
        if (!check_inventory(app.board_) || !app.button_enabled(102) || app.button_enabled(114)) return 32;
        app.imported_game_=true;
        if (!app.button_enabled(114)) return 33;
        app.thinking_=true;
        if (app.button_enabled(101) || app.button_enabled(102) || app.button_enabled(114)
            || !app.button_enabled(111) || !app.button_enabled(112) || !app.button_enabled(113)) return 34;
        app.thinking_=false;
        app.dialog_open_=true;
        if (app.button_enabled(101) || app.button_enabled(103) || app.button_enabled(114)) return 39;
        app.dialog_open_=false;
        std::ifstream input(replay_file);
        std::string replay(std::istreambuf_iterator<char>(input),{});
        while (!replay.empty() && (replay.back()=='\n' || replay.back()=='\r')) replay.pop_back();
        if (!input || !genseki::review::prepare(replay) || !app.board_.load_game_string(replay,error)) return 35;
        app.imported_game_=false;
        if (!check_inventory(app.board_) || !app.button_enabled(114)) return 36;
        app.hwnd_=CreateWindowExW(0,L"STATIC",L"History wheel test",WS_OVERLAPPEDWINDOW,
                                 0,0,400,300,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        if (!app.hwnd_) return 37;
        app.history_rect_={0,0,200,60};
        POINT pointer{20,20};ClientToScreen(app.hwnd_,&pointer);
        const double original_size=app.size_;
        app.on_wheel(pointer.x,pointer.y,WHEEL_DELTA);
        const int expected=std::min(3,std::max(0,int(app.board_.history().size())-3));
        bool scroll_ok=app.history_offset_==expected && app.size_==original_size;
        app.on_wheel(pointer.x,pointer.y,-WHEEL_DELTA);
        scroll_ok=scroll_ok && app.history_offset_==0 && app.size_==original_size;
        DestroyWindow(app.hwnd_);
        if (!scroll_ok) return 38;
        return 0;
    }

    static int review_flow_smoke(HINSTANCE instance,const std::filesystem::path& engine,const std::filesystem::path& replay_file,const std::filesystem::path& output){
        App app;app.instance_=instance;app.engine_path_=engine;app.review_testing_hidden_=true;
        app.hwnd_=CreateWindowExW(0,L"STATIC",L"Review flow test",WS_OVERLAPPEDWINDOW,0,0,900,640,nullptr,nullptr,instance,nullptr);
        if(!app.hwnd_||!app.engine_.start(engine))return 20;
        for(auto option:{"options set BackgroundPondering False","options set RandomOpening False","options set NumThreads 1","options set TableSizeMiB 32"})(void)app.engine_.command(option);
        std::ifstream input(replay_file);std::string game(std::istreambuf_iterator<char>(input),{});
        while(!game.empty()&&(game.back()=='\n'||game.back()=='\r'))game.pop_back();
        if(!app.import_replay(game))return 21;
        const auto original=app.board_.game_string();
        app.on_command(114);
        if(!app.review_window_||!app.review_window_->active())return 22;
        int result=app.review_window_->acceptance(output/"completed");
        app.update_clock();app.maybe_engine_move();
        if(result==0&&(app.board_.game_string()!=original||app.white_elapsed_!=std::chrono::seconds(0)||app.black_elapsed_!=std::chrono::seconds(0)||!app.audio_cues_.empty()))result=23;
        app.review_window_.reset();
        if(result==0){
            if(app.import_replay("Base;InProgress;White[2];wS1;bS1 missing")||app.board_.game_string()!=original)return 26;
            if(!app.import_replay("Base;InProgress;White[3];wS1;bS1 wS1-;wQ -wS1;bQ bS1-"))return 24;
            const auto partial=app.board_.game_string();app.on_command(114);
            auto white=app.white_elapsed_,black=app.black_elapsed_;
            result=app.review_window_->acceptance(output/"cancelled",true);
            app.update_clock();app.maybe_engine_move();
            if(result==0&&(!app.review_window_->report().partial_game||app.board_.game_string()!=partial||app.white_elapsed_!=white||app.black_elapsed_!=black||!app.audio_cues_.empty()))result=25;
            app.review_window_.reset();
        }
        app.engine_.stop();DestroyWindow(app.hwnd_);app.hwnd_=nullptr;return result;
    }
    static int review_isolation_smoke(HINSTANCE instance) {
        App app;std::wstring error;
        if(!app.board_.load_game_string("Base;InProgress;White[3];wS1;bS1 wS1-;wQ -wS1;bQ bS1-",error))return 1;
        const auto original=app.board_.game_string();
        app.white_elapsed_=std::chrono::seconds(3);app.black_elapsed_=std::chrono::seconds(4);
        app.last_tick_=std::chrono::steady_clock::now()-std::chrono::seconds(10);
        app.review_window_=std::make_unique<genseki::review::ReviewWindow>();
        if(!app.review_window_->open(instance,nullptr,original,{},true))return 2;
        app.update_clock();app.maybe_engine_move();
        if(app.white_elapsed_!=std::chrono::seconds(3)||app.black_elapsed_!=std::chrono::seconds(4))return 3;
        if(app.board_.game_string()!=original||app.thinking_||app.reply_.valid()||!app.audio_cues_.empty())return 4;
        app.review_window_.reset();return 0;
    }
    int run(HINSTANCE instance, int show, std::filesystem::path engine_path,
            std::filesystem::path spectator_path = {}) {
        instance_ = instance;
        engine_path_ = std::move(engine_path);
        spectator_path_ = std::move(spectator_path);
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
            case WM_GETMINMAXINFO: {
                auto limits=reinterpret_cast<MINMAXINFO*>(lparam);
                limits->ptMinTrackSize={1000,760};
                return 0;
            }
            case WM_CREATE:
                on_create();
                return 0;
            case WM_SIZE:
                layout();
                InvalidateRect(hwnd_, nullptr, TRUE);
                return 0;
            case WM_ERASEBKGND:
                return 1;
            case WM_MOUSELEAVE:
                hover_={-1,-1};InvalidateRect(hwnd_,nullptr,FALSE);return 0;
            case WM_TIMER:
                if (!spectator_path_.empty()) poll_spectator();
                else maybe_engine_move();
                {
                    auto second=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
                    if(animation_||!audio_cues_.empty()||easing_||thinking_||second!=paint_second_)InvalidateRect(hwnd_, nullptr, FALSE);
                    paint_second_=second;
                }
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
                review_window_.reset();
                if(reply_.valid())reply_.wait();
                engine_.stop();
                audio_.stop();
                release_buffer();
                if(font_)DeleteObject(font_);
                if(reserve_font_)DeleteObject(reserve_font_);
                PostQuitMessage(0);
                return 0;
        }
        return DefWindowProcW(hwnd_, message, wparam, lparam);
    }

    void on_create() {
        if(!nunito().ready())MessageBoxW(hwnd_,L"Bundled Nunito font could not be loaded.",L"Genseki",MB_ICONERROR);
        if(!tiny_raster().ready())MessageBoxW(hwnd_,L"tiny-skia renderer could not be loaded.",L"Genseki",MB_ICONERROR);
        font_=CreateFontW(-16,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
                         OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Nunito");
        reserve_font_=CreateFontW(-12,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
                         OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Nunito");
        if(!icons_.load(instance_))MessageBoxW(hwnd_,L"Unable to load insect artwork.",L"Genseki",MB_ICONERROR);
        if (!spectator_path_.empty()) {
            status_ = L"Waiting for gauntlet";
            white_mode_ = black_mode_ = Mode::engine;
            sound_ = false;
            poll_spectator();
        } else if (!engine_.start(engine_path_)) {
            status_ = L"Engine launch failed: " + engine_path_.wstring();
        } else {
            status_ = L"Engine ready";
            send_newgame("Base");
            send_options();
        }
        SetTimer(hwnd_, 1, 16, nullptr);
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
        if (!spectator_path_.empty()) {
            add_button(111, x, 12, 64, L"Rules");
            add_button(112, x+72, 12, 94, motion_?L"Motion: on":L"Motion: off");
            add_button(113, x+174, 12, 94, sound_?L"Sound: on":L"Sound: off");
            if(board_.history().empty()){origin_x_=(board_rect_.left+board_rect_.right)/2.0;origin_y_=(board_rect_.top+board_rect_.bottom)/2.0;}
            return;
        }
        add_button(101, x, 12, 86, L"New game"); x += 94;
        add_button(102, x, 12, 64, L"Undo"); x += 72;
        add_button(108, x, 12, 104, L"Play White"); x += 112;
        add_button(109, x, 12, 104, L"Play Black"); x += 112;
        add_button(110, x, 12, 104, L"Two players"); x += 112;
        add_button(107, x, 12, 72, L"Watch"); x += 80;
        add_button(103, x, 12, 64, L"Load"); x += 72;
        add_button(111, x, 12, 64, L"Rules");
        x+=72;add_button(112,x,12,94,motion_?L"Motion: on":L"Motion: off");
        x+=102;add_button(113,x,12,94,sound_?L"Sound: on":L"Sound: off");
        add_button(114,8,54,114,L"Review Game");
        int second_row=130;
        for(auto& button:buttons_)if(button.rect.right>rc.right-8&&button.id!=114){
            auto width=button.rect.right-button.rect.left;button.rect={second_row,54,second_row+width,80};second_row+=width+8;
        }
        if(board_.history().empty()){origin_x_=(board_rect_.left+board_rect_.right)/2.0;origin_y_=(board_rect_.top+board_rect_.bottom)/2.0;}
    }

    void add_button(int id, int x, int y, int width, std::wstring text) {
        buttons_.push_back(Button{id, {x, y, x + width, y + 26}, std::move(text)});
    }

    void poll_spectator() {
        const auto now = std::chrono::steady_clock::now();
        if(now-spectator_poll_<std::chrono::milliseconds(100))return;
        spectator_poll_=now;
        const auto frame=read_spectator_frame(spectator_path_);
        if(!frame)return;
        const auto& lines=*frame;
        // Each snapshot is replaced atomically by the runner. No engine is
        // launched here, and spectator controls cannot submit moves.
        if(lines[6]!=spectator_game_) {
            MirrorBoard candidate;std::wstring error;
            if(!candidate.load_game_string(lines[6],error)){status_=L"Invalid spectator position: "+error;return;}
            consume_engine_response({lines[6]});
            spectator_game_=lines[6];
        }
        SetWindowTextW(hwnd_,widen(lines[1]).c_str());
        status_=widen(lines[2]);
        spectator_white_=widen(lines[3]);
        spectator_black_=widen(lines[4]);
        spectator_score_=widen(lines[5]);
        InvalidateRect(hwnd_,nullptr,FALSE);
    }

    void send_options() {
        const auto lines = engine_.command("options");
        for (const auto& line : lines) {
            if (line.starts_with("err ")) status_ = widen(line);
        }
    }

    void send_newgame(const std::string& game) {
        if (!engine_.connected() && !engine_.start(engine_path_)) {
            status_=L"Could not start Alpha. The current game has been kept.";
            InvalidateRect(hwnd_,nullptr,FALSE);
            return;
        }
        imported_game_=game!="Base";
        history_offset_=0;
        history_wheel_delta_=0;
        audio_cues_.clear();
        animation_.reset();
        selected_.reset();
        legal_.clear();
        auto lines = engine_.command("newgame " + game);
        consume_engine_response(lines);
        animation_.reset();
        audio_cues_.clear();
        audio_.silence();
        refresh_legal();
        white_elapsed_ = black_elapsed_ = std::chrono::seconds{0};
        last_tick_ = std::chrono::steady_clock::now();
        if(board_.history().empty()) {
            auto opening=std::find_if(legal_.begin(),legal_.end(),[](const Move& move){return move.kind==MoveKind::placement&&move.piece.bug==Bug::ant;});
            if(opening!=legal_.end())selected_=*opening;
        }
    }

    void consume_engine_response(const std::vector<std::string>& lines) {
        for (const auto& line : lines) {
            if (line.starts_with("err ")) status_ = widen(line);
            else if (line.starts_with("invalidmove ")) status_ = widen(line);
            else if (line.starts_with("Base")) {
                update_clock();
                const auto previous=board_.history().size();
                const auto previous_reserves=reserve_hits_;
                std::wstring error;
                if (!board_.load_game_string(line, error)) status_ = error;
                else {
                    status_ = L"Position loaded";
                    if (history_offset_>0 && board_.history().size()>previous)
                        history_offset_+=int(board_.history().size()-previous);
                    if(board_.history().size()==previous+1&&!board_.history().empty()) {
                        auto move=board_.history().back();
                        if(move.kind!=MoveKind::pass) {
                            POINT origin=hex_to_point(move.to);
                            for(const auto& hit:previous_reserves)if(hit.second==move.piece)origin={(hit.first.left+hit.first.right)/2,(hit.first.top+hit.first.bottom)/2};
                            animation_=Animation{move,origin,std::chrono::steady_clock::now()};
                            animation_->terminal=board_.result()!=L"InProgress"&&board_.result()!=L"NotStarted";
                            if(!motion_)animation_.reset();
                            unsigned effect=602;
                            if(board_.result()!=L"InProgress"&&board_.result()!=L"NotStarted")effect=604;
                            if(sound_&&effect) {
                                auto due=std::chrono::steady_clock::now();
                                if(animation_)due=animation_->started+std::chrono::milliseconds(animation_->terminal?1400:850);
                                if(audio_cues_.size()<16)audio_cues_.push_back({effect,due});
                            }
                        }
                    }else if(board_.history().size()!=previous)animation_.reset();
                }
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

    void update_clock() {
        const auto now = std::chrono::steady_clock::now();
        if(review_window_&&review_window_->active()){last_tick_=now;return;}
        const auto delta = now - last_tick_;
        if (board_.result() == L"InProgress") {
            if (board_.side() == Color::white) white_elapsed_ += delta;
            else black_elapsed_ += delta;
        }
        last_tick_ = now;
    }

    void maybe_engine_move() {
        update_clock();
        if (dialog_open_) return;
        if(review_window_&&review_window_->active())return;
        if(reply_.valid()) {
            if(reply_.wait_for(std::chrono::seconds(0))!=std::future_status::ready)return;
            try {auto lines=reply_.get();if(!lines.empty()&&!lines.front().starts_with("err "))play_move(widen(lines.front()));else consume_engine_response(lines);}
            catch(const std::exception&){status_=L"Engine request failed";}
            thinking_=false;
            return;
        }
        if(animation_&&std::chrono::duration<double>(std::chrono::steady_clock::now()-animation_->started).count()<.32)return;
        const Mode mode = board_.side() == Color::white ? white_mode_ : black_mode_;
        if (mode == Mode::engine && !thinking_ && engine_.connected()
            && (board_.result() == L"InProgress" || board_.result() == L"NotStarted")) {
            thinking_ = true;
            status_ = L"Engine thinking (" + bot_name() + L")";
            reply_=std::async(std::launch::async,[this]{return engine_.command("bestmove time 00:00:00.230");});
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
                if (button_enabled(button.id)) SendMessageW(hwnd_, WM_COMMAND, button.id, 0);
                return;
            }
        }
        if (review_window_ && review_window_->active()) return;
        if(!spectator_path_.empty()) {
            if(x<panel_rect_.left&&y>=board_rect_.top){
                dragging_=true;last_mouse_={x,y};SetCapture(hwnd_);
            }
            return;
        }
        if (x >= panel_rect_.left) {
            handle_panel_click(x, y);
            return;
        }
        if(y<board_rect_.top)return;
        if((board_.side()==Color::white?white_mode_:black_mode_)==Mode::engine)return;
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
        if((board_.side()==Color::white?white_mode_:black_mode_)==Mode::engine)return;
        for (const auto& hit : reserve_hits_) {
            if (PtInRect(&hit.first, {x, y})) {
                if(hit.second.color!=board_.side()||std::none_of(legal_.begin(),legal_.end(),[&](const Move& m){return m.piece==hit.second&&m.kind==MoveKind::placement;}))return;
                selected_ = Move{MoveKind::placement, std::nullopt, {}, hit.second, {}};
                status_ = L"Selected reserve " + piece_label(hit.second);
                InvalidateRect(hwnd_, nullptr, TRUE);
                return;
            }
        }
    }

    void on_mouse_move(int x, int y, bool left_down) {
        hover_={x,y};
        InvalidateRect(hwnd_,nullptr,FALSE);
        TRACKMOUSEEVENT tracking{sizeof(tracking),TME_LEAVE,hwnd_,0};TrackMouseEvent(&tracking);
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
        if (PtInRect(&history_rect_,client)) {
            const int visible=std::max(1,int(history_rect_.bottom-history_rect_.top)/20);
            const int maximum=std::max(0,int(board_.history().size())-visible);
            history_wheel_delta_+=delta;
            const int steps=history_wheel_delta_/WHEEL_DELTA;
            history_wheel_delta_%=WHEEL_DELTA;
            history_offset_=std::clamp(history_offset_+steps*3,0,maximum);
            InvalidateRect(hwnd_,nullptr,FALSE);
            return;
        }
        if (!PtInRect(&board_rect_,client) || !delta) return;
        const double old = size_;
        size_ = std::clamp(size_ * (delta > 0 ? 1.12 : 0.89), 18.0, 88.0);
        const double scale = size_ / old;
        origin_x_ = client.x - (client.x - origin_x_) * scale;
        origin_y_ = client.y - (client.y - origin_y_) * scale;
        InvalidateRect(hwnd_, nullptr, FALSE);
    }

    bool button_enabled(int id) const {
        if (dialog_open_) return false;
        if (!spectator_path_.empty()) return id == 111 || id == 112 || id == 113;
        if (review_window_ && review_window_->active()) return false;
        if (thinking_) return id == 111 || id == 112 || id == 113;
        if (id == 102) return !board_.history().empty();
        if (id == 114) return !board_.history().empty() &&
            (imported_game_ || (board_.result() != L"InProgress" && board_.result() != L"NotStarted"));
        return true;
    }

    void on_command(int id) {
        if (!button_enabled(id)) return;
        if(id==114){
            if(board_.history().empty()||(!imported_game_&&(board_.result()==L"InProgress"||board_.result()==L"NotStarted"))){status_=L"Finish the game or load a replay to review it.";InvalidateRect(hwnd_,nullptr,FALSE);return;}
            update_clock();animation_.reset();audio_cues_.clear();audio_.silence();
            review_window_=std::make_unique<genseki::review::ReviewWindow>();
            if(!review_window_->open(instance_,hwnd_,board_.game_string(),engine_path_,false,review_testing_hidden_))status_=L"Could not open game review.";
            return;
        }
        if(id==112){motion_=!motion_;if(!motion_){animation_.reset();for(auto& cue:audio_cues_)cue.due=std::chrono::steady_clock::now();}layout();}
        if(id==113){sound_=!sound_;if(!sound_){audio_cues_.clear();audio_.silence();}layout();}
        if (id == 101) send_newgame("Base");
        if (id == 102) {
            audio_cues_.clear();
            selected_.reset();
            const bool versus_bot=white_mode_!=black_mode_;
            const bool human_turn=(board_.side()==Color::white?white_mode_:black_mode_)==Mode::human;
            const unsigned count=versus_bot&&human_turn&&board_.history().size()>=2?2:1;
            consume_engine_response(engine_.command("undo "+std::to_string(count)));
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
        if(id==108){white_mode_=Mode::human;black_mode_=Mode::engine;}
        if(id==109){white_mode_=Mode::engine;black_mode_=Mode::human;}
        if(id==110){white_mode_=black_mode_=Mode::human;}
        if(id==111)MessageBoxW(hwnd_,
            L"GOAL\nSurround the opposing Queen on all six sides. Your own pieces can count toward the surround.\n\n"
            L"PLACEMENT\nPlace your Queen by your fourth turn. After the opening, new pieces may touch your color only.\n\n"
            L"MOVEMENT\nYou may move after placing your Queen. The hive must stay connected, and ground pieces must slide through open gaps.\n\n"
            L"Queen: one space.\nSpider: exactly three sliding steps.\nBeetle: one space, including on top of pieces.\nGrasshopper: jump straight over a line of pieces.\nAnt: slide any distance around the hive.\n\n"
            L"Covered pieces cannot move. A simultaneous Queen surround is a draw.",L"Hive rules",MB_OK);
        InvalidateRect(hwnd_, nullptr, TRUE);
    }

    void maybe_engine_once() {
        auto lines = engine_.command("bestmove time 00:00:00.230");
        if (!lines.empty() && !lines.front().starts_with("err ")) play_move(widen(lines.front()));
        else consume_engine_response(lines);
    }

    void load_game_dialog() {
        // A modal dialog pumps WM_TIMER: do not start a competing engine request.
        dialog_open_=true;
        const int result = MessageBoxW(hwnd_, L"Load the Hive game from clipboard text?", L"Load game", MB_OKCANCEL);
        dialog_open_=false;
        if (result != IDOK) return;
        std::wstring replay;
        if (OpenClipboard(hwnd_)) {
            HANDLE data = GetClipboardData(CF_UNICODETEXT);
            if (data) {
                auto bytes=GlobalSize(data);
                if(bytes>=sizeof(wchar_t)&&bytes<=524288){
                    auto* text = static_cast<const wchar_t*>(GlobalLock(data));
                    if(text){auto end=std::find(text,text+bytes/sizeof(wchar_t),L'\0');
                        if(end!=text+bytes/sizeof(wchar_t))replay.assign(text,end);
                        GlobalUnlock(data);
                    }
                }
            }
            CloseClipboard();
        }
        if(replay.empty()){status_=L"The clipboard has no valid replay, or it exceeds the size limit.";InvalidateRect(hwnd_,nullptr,FALSE);return;}
        (void)import_replay(narrow(replay));
    }

    bool import_replay(std::string_view replay){
        auto valid=genseki::review::prepare(replay);
        if(!valid){status_=widen(valid.error());return false;}
        send_newgame(valid->replay);
        auto loaded=genseki::Board::from_game_string(board_.game_string());
        return loaded&&loaded->game_string()==valid->replay;
    }

    void paint() {
        PAINTSTRUCT ps{};
        HDC target = BeginPaint(hwnd_, &ps);
        RECT rc{};GetClientRect(hwnd_,&rc);
        if(rc.right<=0||rc.bottom<=0){EndPaint(hwnd_,&ps);return;}
        if(!buffer_||buffer_width_!=rc.right||buffer_height_!=rc.bottom) {
            release_buffer();buffer_=CreateCompatibleDC(target);
            bitmap_=CreateCompatibleBitmap(target,rc.right,rc.bottom);
            buffer_old_=SelectObject(buffer_,bitmap_);buffer_width_=rc.right;buffer_height_=rc.bottom;
        }
        HDC hdc=buffer_;
        easing_=false;
        auto old_font=SelectObject(hdc,font_);
        HBRUSH bg = CreateSolidBrush(RGB(25,19,17));
        FillRect(hdc, &rc, bg);
        DeleteObject(bg);
        paint_toolbar(hdc);
        paint_board(hdc);
        paint_panel(hdc);
        SelectObject(hdc,old_font);
        BitBlt(target,0,0,rc.right,rc.bottom,hdc,0,0,SRCCOPY);EndPaint(hwnd_, &ps);
        const auto now=std::chrono::steady_clock::now();
        std::erase_if(audio_cues_,[&](const AudioCue& cue){if(cue.due>now)return false;if(sound_)audio_.play(cue.id);return true;});
    }

    void release_buffer() {
        if(buffer_){SelectObject(buffer_,buffer_old_);DeleteObject(bitmap_);DeleteDC(buffer_);}
        buffer_=nullptr;bitmap_=nullptr;
    }

    double hover_amount(int key,const RECT& rect) {
        if(!motion_)return PtInRect(&rect,hover_)?1.:0.;
        auto& value=hover_values_[key];double target=PtInRect(&rect,hover_)?1.:0.;
        auto now=std::chrono::steady_clock::now();
        double dt=std::clamp(std::chrono::duration<double>(now-value.second).count(),0.,.05);
        value.first+=(target-value.first)*(1.-std::exp(-dt*18));value.second=now;
        if(std::abs(target-value.first)>.005)easing_=true;
        return value.first;
    }

    void paint_toolbar(HDC hdc) {
        HBRUSH brush = CreateSolidBrush(RGB(47,32,26));
        FillRect(hdc, &toolbar_, brush);
        DeleteObject(brush);
        SetBkMode(hdc, TRANSPARENT);
        SetTextColor(hdc,RGB(246,225,199));
        for (const auto& button : buttons_) {
            const bool active=(button.id==108&&white_mode_==Mode::human&&black_mode_==Mode::engine)
                ||(button.id==109&&white_mode_==Mode::engine&&black_mode_==Mode::human)
                ||(button.id==110&&white_mode_==Mode::human&&black_mode_==Mode::human)
                ||(button.id==107&&white_mode_==Mode::engine&&black_mode_==Mode::engine);
            const bool enabled=button_enabled(button.id);
            SetTextColor(hdc,enabled?RGB(246,225,199):RGB(132,113,99));
            double hover=enabled?hover_amount(button.id,button.rect):0.;
            HBRUSH fill=CreateSolidBrush(!enabled?RGB(42,32,27):active?RGB(int(142+hover*26),int(70+hover*17),int(37+hover*10)):RGB(int(66+hover*29),int(44+hover*18),int(33+hover*10)));
            auto old=SelectObject(hdc,fill);
            RECT visual=button.rect;
            int expansion=int(std::lround(hover*2));InflateRect(&visual,expansion,expansion);
            HPEN border=CreatePen(PS_SOLID,1,!enabled?RGB(68,53,44):RGB(int(125+hover*50),int(83+hover*42),int(51+hover*30)));
            auto old_pen=SelectObject(hdc,border);
            RoundRect(hdc,visual.left,visual.top,visual.right,visual.bottom,6,6);
            SelectObject(hdc,old_pen);DeleteObject(border);
            SelectObject(hdc,old);DeleteObject(fill);
            DrawTextW(hdc, button.text.c_str(), -1, const_cast<RECT*>(&button.rect), DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
    }

    std::wstring mode_name(Mode mode) const { return mode == Mode::human ? L"Human" : L"Engine"; }

    std::wstring bot_name() const {
        return L"Alpha";
    }

    void paint_board(HDC hdc) {
        HBRUSH board_bg = CreateSolidBrush(RGB(31,23,20));
        FillRect(hdc, &board_rect_, board_bg);
        DeleteObject(board_bg);
        HRGN clip = CreateRectRgn(board_rect_.left, board_rect_.top, board_rect_.right, board_rect_.bottom);
        SelectClipRgn(hdc, clip);
        paint_legal(hdc);
        double age=animation_?std::chrono::duration<double>(std::chrono::steady_clock::now()-animation_->started).count():10.;
        for (const auto& stack : board_.stacks()) {
            if(animation_&&age<.32&&stack.cell==animation_->move.to&&stack.pieces.back()==animation_->move.piece) {
                if(stack.pieces.size()>1){auto below=stack;below.pieces.pop_back();paint_stack(hdc,below);}
            }else paint_stack(hdc, stack);
        }
        if(animation_&&age<(animation_->terminal?1.4:.85)) {
            auto destination=hex_to_point(animation_->move.to);
            if(age<.32) {
                double t=std::clamp(age/.32,0.,1.);double ease=1-std::pow(1-t,3);
                POINT source=animation_->move.from?hex_to_point(*animation_->move.from):animation_->reserve;
                POINT center{LONG(source.x+(destination.x-source.x)*ease),LONG(source.y+(destination.y-source.y)*ease-std::sin(t*3.141592653589793)*16)};
                paint_tile(hdc,animation_->move.piece,center,size_*(.92+.08*ease),false);
            }
            auto& raster=tiny_raster();void* canvas=raster.create(160,160);
            if(canvas) {
                double life=std::clamp((age-.24)/(animation_->terminal?1.16:.61),0.,1.);
                if(age>=.24)raster.ellipse(canvas,80,80,float(22+25*life),float(22+25*life),RGB(177,85,37),false,1.5f,unsigned(130*(1-life)));
                for(int i=0;i<(animation_->terminal?36:18)&&age>=.24;++i) {
                    double angle=i*2.399963,spread=(18+i%5*5)*life;
                    raster.ellipse(canvas,float(80+std::cos(angle)*spread),float(80+std::sin(angle)*spread+12*life*life),float(2*(1-life)+.4),float(2*(1-life)+.4),i%2?RGB(178,72,36):RGB(224,155,63),true,1,unsigned(200*(1-life)));
                }
                raster.present(hdc,canvas,destination.x-80,destination.y-80,160,160);raster.release(canvas);
            }
        }else if(animation_)animation_.reset();
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
        HBRUSH brush = CreateSolidBrush(RGB(191, 127, 64));
        HPEN pen = CreatePen(PS_SOLID, 1, RGB(131, 76, 42));
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
        const Piece top = stack.pieces.back();
        RECT hit{center.x-LONG(size_*.8),center.y-LONG(size_*.8),center.x+LONG(size_*.8),center.y+LONG(size_*.8)};
        double hover=hover_amount(1000+int(top.color)*100+int(top.bug)*10+top.id,hit);
        paint_tile(hdc,top,center,size_*(1.+.045*hover),selected_&&selected_->from==stack.cell);
        if (stack.pieces.size() > 1) {
            RECT badge{center.x + 16, center.y + 12, center.x + 44, center.y + 30};
            const auto height = L"x" + std::to_wstring(stack.pieces.size());
            SetTextColor(hdc, RGB(250,224,185));
            DrawTextW(hdc, height.c_str(), -1, &badge, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
    }

    void paint_tile(HDC hdc,Piece piece,POINT center,double size,bool selected) {
        POINT shadow{center.x,center.y+3};soft_hex(hdc,shadow,size*.82,RGB(17,12,10),RGB(17,12,10),1);
        soft_hex(hdc,center,size*.82,piece.color==Color::white?RGB(255,247,230):RGB(81,50,40),selected?RGB(190,76,39):RGB(133,94,63),selected?3.f:1.3f);
        RECT insect{center.x-LONG(size*.5),center.y-LONG(size*.5),center.x+LONG(size*.5),center.y+LONG(size*.5)};
        icons_.draw(hdc,unsigned(piece.bug),insect,piece.color==Color::white?RGB(92,53,33):RGB(255,235,200));
    }

    void paint_panel(HDC hdc) {
        HBRUSH panel = CreateSolidBrush(RGB(43,30,25));
        FillRect(hdc, &panel_rect_, panel);
        DeleteObject(panel);
        SetBkMode(hdc, TRANSPARENT);
        int y = panel_rect_.top + 10;
        SetTextColor(hdc,RGB(246,225,199));
        draw_line(hdc, 10, y, color_name(board_.side()) + L" to play"); y += 24;
        draw_line(hdc, 10, y, board_.result()==L"NotStarted"?L"New game":board_.result()); y += 22;
        if(spectator_path_.empty())draw_line(hdc, 10, y, L"Clock W/B: " + clock_text(white_elapsed_) + L" / " + clock_text(black_elapsed_));
        else draw_line(hdc,10,y,L"Live gauntlet spectator");
        y += 22;
        draw_line(hdc, 10, y, L"Status: " + status_); y += 22;
        if(!spectator_path_.empty()) {
            draw_line(hdc,10,y,L"White: "+spectator_white_);y+=22;
            draw_line(hdc,10,y,L"Black: "+spectator_black_);y+=22;
            draw_line(hdc,10,y,spectator_score_);y+=24;
        } else {draw_line(hdc, 10, y, L"Engine: " + bot_name()); y += 42;}
        y = draw_reserve(hdc, y, Color::white);
        y = draw_reserve(hdc, y, Color::black);
        if(spectator_path_.empty()){draw_line(hdc, 10, y, L"Legal moves: " + std::to_wstring(legal_.size())); y += 24;}
        draw_line(hdc, 10, y, L"Move history"); y += 22;
        history_rect_={panel_rect_.left + 10, y, panel_rect_.right - 10,
                       std::max<LONG>(y,panel_rect_.bottom - 10)};
        RECT hist=history_rect_;
        std::wstring text;
        const int visible=std::max(1,int(hist.bottom-hist.top)/20);
        const int total=int(board_.history().size());
        history_offset_=std::clamp(history_offset_,0,std::max(0,total-visible));
        const int first=std::max(0,total-visible-history_offset_);
        for (int index=first;index<std::min(total,first+visible);++index) {
            RECT row{hist.left,hist.top+(index-first)*20,hist.right,
                     std::min(hist.bottom,hist.top+(index-first+1)*20)};
            text=std::to_wstring(index+1)+L". "+board_.history()[index].uhp;
            DrawTextW(hdc,text.c_str(),-1,&row,DT_LEFT|DT_VCENTER|DT_SINGLELINE|DT_END_ELLIPSIS|DT_NOPREFIX);
        }
    }

    std::wstring clock_text(std::chrono::steady_clock::duration elapsed) const {
        const auto total = std::chrono::duration_cast<std::chrono::seconds>(elapsed).count();
        wchar_t buffer[32]{};
        swprintf_s(buffer, L"%02lld:%02lld", total / 60, total % 60);
        return buffer;
    }

    void draw_line(HDC hdc, int x, int y, const std::wstring& text) {
        RECT line{panel_rect_.left + x, y, panel_rect_.right - 10, y + 20};
        DrawTextW(hdc, text.c_str(), -1, &line, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    }

    int draw_reserve(HDC hdc, int y, Color color) {
        draw_line(hdc, 10, y, color_name(color) + L" reserve");
        y += 24;
        auto pieces = board_.reserve(color);
        int x = panel_rect_.left + 10;
        if (color == Color::white) reserve_hits_.clear();
        int bottom = y;
        for (const auto& piece : pieces) {
            RECT rc{x, y, x + 108, y + 38};
            const bool legal=piece.color==board_.side()&&std::any_of(legal_.begin(),legal_.end(),[&](const Move& m){return m.piece==piece&&m.kind==MoveKind::placement;});
            const bool selected=selected_&&selected_->piece==piece&&!selected_->from;
            double hover=hover_amount(2000+int(piece.color)*100+int(piece.bug)*10+piece.id,rc);
            HBRUSH brush = CreateSolidBrush(selected?RGB(231,178,111):piece.color==Color::white?RGB(255,int(248-hover*12),int(232-hover*26)):RGB(int(81+hover*22),int(50+hover*12),40));
            FillRect(hdc, &rc, brush);
            auto old=SelectObject(hdc,brush);
            Rectangle(hdc, rc.left, rc.top, rc.right, rc.bottom);
            SelectObject(hdc,old);DeleteObject(brush);
            COLORREF foreground=!legal?(piece.color==Color::white?RGB(128,106,84):RGB(185,151,121)):selected||piece.color==Color::white?RGB(83,49,31):RGB(255,235,200);
            RECT icon{rc.left+4,rc.top+4,rc.left+32,rc.bottom-4};icons_.draw(hdc,unsigned(piece.bug),icon,foreground);
            SetTextColor(hdc,foreground);
            auto label = bug_name(piece.bug);
            if(piece.bug!=Bug::queen)label+=L" "+std::to_wstring(piece.id+1);
            RECT text{rc.left+35,rc.top,rc.right-3,rc.bottom};
            auto old_font=SelectObject(hdc,reserve_font_);
            DrawTextW(hdc,label.c_str(),-1,&text,DT_LEFT|DT_VCENTER|DT_SINGLELINE|DT_END_ELLIPSIS);
            SelectObject(hdc,old_font);
            reserve_hits_.push_back({rc, piece});
            bottom = rc.bottom;
            x += 114;
            if (x + 108 > panel_rect_.right - 8) {
                x = panel_rect_.left + 10;
                y += 44;
            }
        }
        SetTextColor(hdc, RGB(246,225,199));
        return bottom + 14;
    }

    HINSTANCE instance_ = nullptr;
    struct Animation {Move move;POINT reserve;std::chrono::steady_clock::time_point started;bool terminal=false;};
    std::optional<Animation> animation_;
    struct AudioCue {unsigned id;std::chrono::steady_clock::time_point due;};
    std::vector<AudioCue> audio_cues_;
    POINT hover_{-1,-1};
    std::map<int,std::pair<double,std::chrono::steady_clock::time_point>> hover_values_;
    std::future<std::vector<std::string>> reply_;
    HDC buffer_=nullptr;
    HBITMAP bitmap_=nullptr;
    HGDIOBJ buffer_old_=nullptr;
    int buffer_width_=0,buffer_height_=0;
    long long paint_second_=0;
    SvgIcons icons_;
    HFONT font_=nullptr;
    HFONT reserve_font_=nullptr;
    HWND hwnd_ = nullptr;
    std::filesystem::path engine_path_{L"genseki.exe"};
    std::filesystem::path spectator_path_;
    std::string spectator_game_;
    std::wstring spectator_white_,spectator_black_,spectator_score_;
    std::chrono::steady_clock::time_point spectator_poll_{};
    EngineProcess engine_{};
    std::unique_ptr<genseki::review::ReviewWindow> review_window_;
    bool imported_game_=false;
    bool review_testing_hidden_=false;
    MirrorBoard board_{};
    RECT toolbar_{};
    RECT board_rect_{};
    RECT panel_rect_{};
    std::vector<Button> buttons_{};
    std::vector<Move> legal_{};
    std::vector<std::pair<RECT, Piece>> reserve_hits_{};
    std::optional<Move> selected_{};
    std::wstring status_ = L"Starting";
    Mode white_mode_ = Mode::human;
    Mode black_mode_ = Mode::human;
    bool thinking_ = false;
    bool dialog_open_=false;
    bool motion_=true,sound_=true;
    AudioPlayer audio_;
    bool easing_=false;
    bool dragging_ = false;
    RECT history_rect_{};
    int history_offset_=0;
    int history_wheel_delta_=0;
    POINT last_mouse_{};
    double size_ = 38.0;
    double origin_x_ = 390.0;
    double origin_y_ = 330.0;
    std::chrono::steady_clock::duration white_elapsed_{};
    std::chrono::steady_clock::duration black_elapsed_{};
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
    const HRESULT com=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    (void)command_line;
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if(argv&&argc==2&&std::wstring_view(argv[1])==L"--check-gui-layout"){
        const int result=nunito().ready()?App::gui_layout_smoke(instance):43;
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return result;
    }
    if(argv&&argc==3&&std::wstring_view(argv[1])==L"--check-gui-state"){
        const int result=App::gui_state_smoke(argv[2]);
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return result;
    }
    if(argv&&argc==5&&std::wstring_view(argv[1])==L"--check-review-flow"){
        bool ready=nunito().ready()&&tiny_raster().ready();
        int result=ready?App::review_flow_smoke(instance,argv[2],argv[3],argv[4]):10;
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return result;
    }
    if(argv&&argc==2&&std::wstring_view(argv[1])==L"--check-review-isolation"){
        int result=App::review_isolation_smoke(instance);
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return result;
    }
    if(argv&&(argc==3||argc==4)&&std::wstring_view(argv[1])==L"--check-review"){
        bool ready=nunito().ready()&&tiny_raster().ready();
        int result=10;
        if(ready&&argc==3)result=genseki::review::ReviewWindow::smoke(instance,argv[2]);
        else if(ready){
            std::ifstream input{std::filesystem::path(argv[3])};
            std::string replay(std::istreambuf_iterator<char>(input),{});
            while(!replay.empty()&&(replay.back()=='\n'||replay.back()=='\r'))replay.pop_back();
            if(input)result=genseki::review::ReviewWindow::smoke(instance,argv[2],replay);
        }
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return result;
    }
    if(argv&&argc>1&&std::wstring_view(argv[1])==L"--check-spectator") {
        bool valid=false;
        if(argc==3) {
            auto frame=read_spectator_frame(argv[2]);
            if(frame){MirrorBoard board;std::wstring error;valid=board.load_game_string((*frame)[6],error);}
        }
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return valid?0:1;
    }
    if(argv&&argc>1&&std::wstring_view(argv[1])==L"--check-font") {
        bool valid=nunito().ready();HDC dc=CreateCompatibleDC(nullptr);
        HFONT font=CreateFontW(-16,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Nunito");
        auto old=SelectObject(dc,font);wchar_t face[128]{};GetTextFaceW(dc,128,face);
        valid=valid&&std::wstring_view(face).starts_with(L"Nunito");
        SelectObject(dc,old);DeleteObject(font);DeleteDC(dc);LocalFree(argv);
        if(SUCCEEDED(com))CoUninitialize();return valid?0:1;
    }
    if(argv&&argc>1&&std::wstring_view(argv[1])==L"--check-sounds") {
        bool valid=true;
        for(unsigned id : {602u,604u}) {
            auto resource=FindResourceW(instance,MAKEINTRESOURCEW(id),L"WAVE");
            if(!resource||SizeofResource(instance,resource)<44){valid=false;continue;}
            auto data=static_cast<const char*>(LockResource(LoadResource(instance,resource)));
            if(!data||std::memcmp(data,"RIFF",4)||std::memcmp(data+8,"WAVE",4))valid=false;
        }
        LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return valid?0:1;
    }
    if(argv&&argc>1&&std::wstring_view(argv[1])==L"--check-icons") {
        SvgIcons icons;bool valid=tiny_raster().ready()&&icons.load(instance);
        HDC dc=CreateCompatibleDC(nullptr);
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth=64;info.bmiHeader.biHeight=-64;
        info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
        void* pixels=nullptr;HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&pixels,nullptr,0);
        auto old=SelectObject(dc,bitmap);
        if(!bitmap||!pixels)valid=false;
        if(valid)for(unsigned insect=0;insect<5;++insect) {
            RECT rect{0,0,64,64};FillRect(dc,&rect,static_cast<HBRUSH>(GetStockObject(WHITE_BRUSH)));
            icons.draw(dc,insect,rect,RGB(0,0,0));GdiFlush();
            unsigned painted=0;auto data=static_cast<std::uint32_t*>(pixels);
            for(unsigned p=0;p<4096;++p)if((data[p]&0xffffff)!=0xffffff)++painted;
            if(painted<100||painted>3000)valid=false;
        }
        SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);LocalFree(argv);
        if(SUCCEEDED(com))CoUninitialize();return valid?0:1;
    }
    std::filesystem::path spectator;
    if(argv&&argc>1&&std::wstring_view(argv[1])==L"--spectate") {
        if(argc!=3){LocalFree(argv);if(SUCCEEDED(com))CoUninitialize();return 2;}
        spectator=argv[2];
    }
    std::filesystem::path engine = !spectator.empty()?std::filesystem::path{}:
        (argc > 1 ? std::filesystem::path(argv[1]) : default_engine_path(argv[0]));
    if (argv) LocalFree(argv);
    App app;
    int result=app.run(instance, show, engine, spectator);
    if(SUCCEEDED(com))CoUninitialize();
    return result;
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show) {
    (void)previous;
    (void)command_line;
    return wWinMain(instance, nullptr, GetCommandLineW(), show);
}
