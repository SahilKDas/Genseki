#include "genseki/core/board.hpp"

#include <algorithm>
#include <charconv>
#include <cctype>
#include <format>
#include <limits>
#include <queue>
#include <ranges>
#include <set>
#include <sstream>

namespace genseki {
namespace {

constexpr std::array<std::uint8_t, 5> inventory{1, 2, 2, 3, 3};

std::size_t index(Color color) {
    return static_cast<std::size_t>(color);
}

char color_char(Color color) {
    return color == Color::white ? 'w' : 'b';
}

char bug_char(Bug bug) {
    constexpr char chars[] = {'Q', 'S', 'B', 'G', 'A'};
    return chars[static_cast<std::size_t>(bug)];
}

std::optional<Bug> parse_bug(char value) {
    switch (static_cast<char>(std::toupper(static_cast<unsigned char>(value)))) {
        case 'Q': return Bug::queen;
        case 'S': return Bug::spider;
        case 'B': return Bug::beetle;
        case 'G': return Bug::grasshopper;
        case 'A': return Bug::ant;
        default: return std::nullopt;
    }
}

std::string piece_name(Piece piece) {
    std::string result{color_char(piece.color), bug_char(piece.bug)};
    if (piece.bug != Bug::queen) {
        result += static_cast<char>('1' + piece.id);
    }
    return result;
}

std::expected<Piece, std::string> parse_piece(std::string_view text) {
    if (text.size() < 2 || (text[0] != 'w' && text[0] != 'b')) {
        return std::unexpected("invalid piece name");
    }
    const auto bug = parse_bug(text[1]);
    if (!bug) {
        return std::unexpected("invalid bug name");
    }
    std::uint8_t id = 0;
    if (*bug == Bug::queen) {
        if (text.size() != 2) {
            return std::unexpected("queen has no number");
        }
    } else {
        if (text.size() != 3 || text[2] < '1' || text[2] > '3') {
            return std::unexpected("piece number is missing or invalid");
        }
        id = static_cast<std::uint8_t>(text[2] - '1');
        if (id >= inventory[static_cast<std::size_t>(*bug)]) {
            return std::unexpected("piece number exceeds inventory");
        }
    }
    return Piece{.color = text[0] == 'w' ? Color::white : Color::black, .bug = *bug, .id = id};
}

std::vector<std::string_view> split(std::string_view text, char delimiter) {
    std::vector<std::string_view> result;
    std::size_t start = 0;
    while (start <= text.size()) {
        const auto end = text.find(delimiter, start);
        result.push_back(text.substr(start, end == std::string_view::npos ? text.size() - start : end - start));
        if (end == std::string_view::npos) {
            break;
        }
        start = end + 1;
    }
    return result;
}

template <typename Integer>
bool parse_integer(std::string_view text, Integer& value) {
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    return error == std::errc{} && end == text.data() + text.size();
}

bool contains(const std::vector<Hex>& cells, Hex cell) {
    return std::ranges::find(cells, cell) != cells.end();
}

}  // namespace

std::string_view name(GameResult result) {
    switch (result) {
        case GameResult::ongoing: return "ongoing";
        case GameResult::white_win: return "white-win";
        case GameResult::black_win: return "black-win";
        case GameResult::draw: return "draw";
    }
    return "unknown";
}

std::string_view name(MoveError error) {
    return error == MoveError::game_over ? "game-over" : "illegal-move";
}

std::string move_notation(const Move& move) {
    if (move.kind == MoveKind::pass) {
        return "pass";
    }
    if (move.kind == MoveKind::placement) {
        return std::format("{}@{},{}", piece_name(move.piece), move.to.q, move.to.r);
    }
    return std::format(
        "{}:{},{}>{},{}",
        piece_name(move.piece),
        move.from->q,
        move.from->r,
        move.to.q,
        move.to.r);
}

std::expected<Move, std::string> parse_move(std::string_view text) {
    if (text == "pass") {
        return Move{.kind = MoveKind::pass};
    }
    const auto marker = text.find_first_of("@:");
    if (marker == std::string_view::npos) {
        return std::unexpected("move is missing '@' or ':'");
    }
    auto piece = parse_piece(text.substr(0, marker));
    if (!piece) {
        return std::unexpected(piece.error());
    }
    auto parse_hex = [](std::string_view value) -> std::expected<Hex, std::string> {
        const auto comma = value.find(',');
        if (comma == std::string_view::npos) {
            return std::unexpected("coordinate is missing comma");
        }
        int q = 0;
        int r = 0;
        if (!parse_integer(value.substr(0, comma), q) || !parse_integer(value.substr(comma + 1), r)) {
            return std::unexpected("invalid coordinate");
        }
        return Hex{static_cast<std::int16_t>(q), static_cast<std::int16_t>(r)};
    };
    if (text[marker] == '@') {
        auto to = parse_hex(text.substr(marker + 1));
        if (!to) {
            return std::unexpected(to.error());
        }
        return Move{.kind = MoveKind::placement, .to = *to, .piece = *piece};
    }
    const auto arrow = text.find('>', marker + 1);
    if (arrow == std::string_view::npos) {
        return std::unexpected("movement is missing '>'");
    }
    auto from = parse_hex(text.substr(marker + 1, arrow - marker - 1));
    auto to = parse_hex(text.substr(arrow + 1));
    if (!from || !to) {
        return std::unexpected("invalid movement coordinate");
    }
    return Move{.kind = MoveKind::movement, .from = *from, .to = *to, .piece = *piece};
}

Color Board::side_to_move() const { return side_to_move_; }
std::size_t Board::ply() const { return ply_; }
const std::vector<Stack>& Board::stacks() const { return stacks_; }
const std::vector<Move>& Board::history() const { return history_; }

const Stack* Board::stack_at(Hex cell) const {
    const auto it = std::ranges::find_if(stacks_, [cell](const Stack& stack) { return stack.cell == cell; });
    return it == stacks_.end() ? nullptr : &*it;
}

Stack* Board::stack_at(Hex cell) {
    const auto it = std::ranges::find_if(stacks_, [cell](const Stack& stack) { return stack.cell == cell; });
    return it == stacks_.end() ? nullptr : &*it;
}

bool Board::occupied(Hex cell) const { return stack_at(cell) != nullptr; }
std::size_t Board::height(Hex cell) const {
    const auto* stack = stack_at(cell);
    return stack == nullptr ? 0 : stack->pieces.size();
}

void Board::normalize_stacks() {
    std::ranges::sort(stacks_, {}, &Stack::cell);
}

bool Board::queen_played(Color color) const {
    return queen_cell(color).has_value();
}

std::optional<Hex> Board::queen_cell(Color color) const {
    for (const auto& stack : stacks_) {
        if (std::ranges::any_of(stack.pieces, [color](Piece piece) {
                return piece.color == color && piece.bug == Bug::queen;
            })) {
            return stack.cell;
        }
    }
    return std::nullopt;
}

std::vector<Piece> Board::pieces_in_hand(Color color) const {
    std::array<std::array<bool, 3>, 5> used{};
    for (const auto& stack : stacks_) {
        for (const auto piece : stack.pieces) {
            if (piece.color == color) {
                used[static_cast<std::size_t>(piece.bug)][piece.id] = true;
            }
        }
    }
    std::vector<Piece> pieces;
    for (std::size_t bug = 0; bug < inventory.size(); ++bug) {
        for (std::uint8_t id = 0; id < inventory[bug]; ++id) {
            if (!used[bug][id]) {
                pieces.push_back(Piece{color, static_cast<Bug>(bug), id});
                break;
            }
        }
    }
    return pieces;
}

std::vector<Hex> Board::placement_cells() const {
    if (stacks_.empty()) {
        return {Hex{0, 0}};
    }
    std::vector<Hex> candidates;
    for (const auto& stack : stacks_) {
        for (const auto direction : directions) {
            const auto cell = add(stack.cell, direction);
            if (!occupied(cell) && !contains(candidates, cell)) {
                candidates.push_back(cell);
            }
        }
    }
    if (stacks_.size() == 1) {
        std::ranges::sort(candidates);
        return candidates;
    }
    std::erase_if(candidates, [this](Hex cell) {
        bool friendly = false;
        bool enemy = false;
        for (const auto direction : directions) {
            if (const auto* neighbor = stack_at(add(cell, direction)); neighbor != nullptr) {
                const auto color = neighbor->pieces.back().color;
                friendly |= color == side_to_move_;
                enemy |= color != side_to_move_;
            }
        }
        return !friendly || enemy;
    });
    std::ranges::sort(candidates);
    return candidates;
}

bool Board::hive_connected_after_lift(Hex cell) const {
    const auto* source = stack_at(cell);
    if (source == nullptr || source->pieces.size() > 1 || stacks_.size() <= 2) {
        return true;
    }
    std::set<Hex> remaining;
    for (const auto& stack : stacks_) {
        if (stack.cell != cell) {
            remaining.insert(stack.cell);
        }
    }
    std::set<Hex> reached;
    std::queue<Hex> pending;
    pending.push(*remaining.begin());
    reached.insert(*remaining.begin());
    while (!pending.empty()) {
        const auto current = pending.front();
        pending.pop();
        for (const auto direction : directions) {
            const auto next = add(current, direction);
            if (remaining.contains(next) && reached.insert(next).second) {
                pending.push(next);
            }
        }
    }
    return reached.size() == remaining.size();
}

bool Board::touches_hive(Hex cell) const {
    return std::ranges::any_of(directions, [this, cell](Hex direction) { return occupied(add(cell, direction)); });
}

bool Board::can_slide(Hex from, Hex to) const {
    if (!adjacent(from, to) || occupied(to) || !touches_hive(to)) {
        return false;
    }
    unsigned blockers = 0;
    for (const auto direction : directions) {
        const auto candidate = add(from, direction);
        if (candidate != to && adjacent(candidate, to) && occupied(candidate)) {
            ++blockers;
        }
    }
    return blockers == 1;
}

bool Board::beetle_gate_open(Hex from, Hex to, std::size_t source_height) const {
    const auto clearance = std::max(source_height, height(to) + 1);
    unsigned blockers = 0;
    for (const auto direction : directions) {
        const auto candidate = add(from, direction);
        if (candidate != to && adjacent(candidate, to) && height(candidate) >= clearance) {
            ++blockers;
        }
    }
    return blockers < 2;
}

std::vector<Hex> Board::ground_crawl(Hex start, bool exactly_three) const {
    std::set<Hex> results;
    if (exactly_three) {
        std::vector<Hex> path{start};
        const auto visit = [&](const auto& self, Hex current, unsigned depth) -> void {
            if (depth == 3) {
                results.insert(current);
                return;
            }
            for (const auto direction : directions) {
                const auto next = add(current, direction);
                if (!contains(path, next) && can_slide(current, next)) {
                    path.push_back(next);
                    self(self, next, depth + 1);
                    path.pop_back();
                }
            }
        };
        visit(visit, start, 0);
    } else {
        std::queue<Hex> pending;
        std::set<Hex> visited{start};
        pending.push(start);
        while (!pending.empty()) {
            const auto current = pending.front();
            pending.pop();
            for (const auto direction : directions) {
                const auto next = add(current, direction);
                if (!visited.contains(next) && can_slide(current, next)) {
                    visited.insert(next);
                    results.insert(next);
                    pending.push(next);
                }
            }
        }
    }
    return {results.begin(), results.end()};
}

std::vector<Hex> Board::movement_destinations(Hex from, const Piece& piece) const {
    Board lifted = *this;
    const auto source_height = lifted.height(from);
    auto* source = lifted.stack_at(from);
    source->pieces.pop_back();
    if (source->pieces.empty()) {
        std::erase_if(lifted.stacks_, [from](const Stack& stack) { return stack.cell == from; });
    }

    std::vector<Hex> destinations;
    switch (piece.bug) {
        case Bug::queen:
            for (const auto direction : directions) {
                const auto to = add(from, direction);
                if (lifted.can_slide(from, to)) {
                    destinations.push_back(to);
                }
            }
            break;
        case Bug::spider:
            destinations = lifted.ground_crawl(from, true);
            break;
        case Bug::beetle:
            for (const auto direction : directions) {
                const auto to = add(from, direction);
                const auto ground_slide = source_height == 1 && !lifted.occupied(to);
                const auto gate_open = ground_slide
                    ? lifted.can_slide(from, to)
                    : lifted.beetle_gate_open(from, to, source_height);
                if (gate_open && (lifted.occupied(to) || lifted.touches_hive(to))) {
                    destinations.push_back(to);
                }
            }
            break;
        case Bug::grasshopper:
            for (const auto direction : directions) {
                auto to = add(from, direction);
                if (!lifted.occupied(to)) {
                    continue;
                }
                do {
                    to = add(to, direction);
                } while (lifted.occupied(to));
                destinations.push_back(to);
            }
            break;
        case Bug::ant:
            destinations = lifted.ground_crawl(from, false);
            break;
    }
    std::ranges::sort(destinations);
    destinations.erase(std::unique(destinations.begin(), destinations.end()), destinations.end());
    return destinations;
}

std::vector<Move> Board::legal_moves() const {
    if (is_terminal()) {
        return {};
    }
    std::vector<Move> moves;
    const bool queen_required = !queen_played(side_to_move_) && turns_taken_[index(side_to_move_)] >= 3;
    for (const auto piece : pieces_in_hand(side_to_move_)) {
        if (piece.bug == Bug::queen && turns_taken_[index(side_to_move_)] == 0) {
            continue;
        }
        if (queen_required && piece.bug != Bug::queen) {
            continue;
        }
        for (const auto cell : placement_cells()) {
            moves.push_back(Move{MoveKind::placement, std::nullopt, cell, piece});
        }
    }
    if (queen_played(side_to_move_)) {
        for (const auto& stack : stacks_) {
            const auto piece = stack.pieces.back();
            if (piece.color != side_to_move_ || !hive_connected_after_lift(stack.cell)) {
                continue;
            }
            for (const auto destination : movement_destinations(stack.cell, piece)) {
                moves.push_back(Move{MoveKind::movement, stack.cell, destination, piece});
            }
        }
    }
    std::ranges::sort(moves);
    if (moves.empty()) {
        moves.push_back(Move{.kind = MoveKind::pass});
    }
    return moves;
}

bool Board::is_legal(const Move& move) const {
    const auto moves = legal_moves();
    return std::ranges::find(moves, move) != moves.end();
}

GameResult Board::result() const {
    const auto surrounded = [this](Color color) {
        const auto queen = queen_cell(color);
        return queen && std::ranges::all_of(directions, [this, queen](Hex direction) {
            return occupied(add(*queen, direction));
        });
    };
    const bool white = surrounded(Color::white);
    const bool black = surrounded(Color::black);
    if (white && black) return GameResult::draw;
    if (white) return GameResult::black_win;
    if (black) return GameResult::white_win;
    return GameResult::ongoing;
}

bool Board::is_terminal() const { return result() != GameResult::ongoing; }

void Board::apply_unchecked(const Move& move) {
    if (move.kind == MoveKind::movement) {
        auto* source = stack_at(*move.from);
        source->pieces.pop_back();
        if (source->pieces.empty()) {
            std::erase_if(stacks_, [move](const Stack& stack) { return stack.cell == *move.from; });
        }
    }
    if (move.kind != MoveKind::pass) {
        if (auto* target = stack_at(move.to); target != nullptr) {
            target->pieces.push_back(move.piece);
        } else {
            stacks_.push_back(Stack{move.to, {move.piece}});
        }
    }
    ++turns_taken_[index(side_to_move_)];
    side_to_move_ = other(side_to_move_);
    ++ply_;
    history_.push_back(move);
    normalize_stacks();
}

std::expected<Undo, MoveError> Board::make_move(const Move& move) {
    if (is_terminal()) {
        return std::unexpected(MoveError::game_over);
    }
    if (!is_legal(move)) {
        return std::unexpected(MoveError::illegal_move);
    }
    Undo undo{move, side_to_move_, ply_, turns_taken_, history_.size()};
    apply_unchecked(move);
    return undo;
}

std::expected<void, MoveError> Board::play(const Move& move) {
    auto applied = make_move(move);
    if (!applied) {
        return std::unexpected(applied.error());
    }
    return {};
}

void Board::undo_unchecked(const Undo& undo) {
    const auto& move = undo.move;
    if (move.kind != MoveKind::pass) {
        auto* target = stack_at(move.to);
        target->pieces.pop_back();
        if (target->pieces.empty()) {
            std::erase_if(stacks_, [move](const Stack& stack) { return stack.cell == move.to; });
        }
    }
    if (move.kind == MoveKind::movement) {
        if (auto* source = stack_at(*move.from); source != nullptr) {
            source->pieces.push_back(move.piece);
        } else {
            stacks_.push_back(Stack{*move.from, {move.piece}});
        }
    }
    side_to_move_ = undo.previous_side;
    ply_ = undo.previous_ply;
    turns_taken_ = undo.previous_turns;
    history_.resize(undo.previous_history_size);
    normalize_stacks();
}

void Board::unmake_move(const Undo& undo) { undo_unchecked(undo); }

bool Board::undo(unsigned count) {
    if (count == 0 || count > history_.size()) {
        return false;
    }
    const auto keep = history_.size() - count;
    const std::vector<Move> replay(history_.begin(), history_.begin() + static_cast<std::ptrdiff_t>(keep));
    *this = Board{};
    for (const auto& move : replay) {
        apply_unchecked(move);
    }
    return true;
}

std::uint64_t Board::perft(unsigned depth) {
    if (depth == 0) {
        return 1;
    }
    std::uint64_t nodes = 0;
    const auto moves = legal_moves();
    for (const auto& move : moves) {
        auto undo = make_move(move);
        nodes += perft(depth - 1);
        unmake_move(*undo);
    }
    return nodes;
}

std::string Board::summary() const {
    return std::format(
        "ply={} side={} stacks={} legal_moves={} result={}",
        ply_,
        side_to_move_ == Color::white ? "white" : "black",
        stacks_.size(),
        legal_moves().size(),
        name(result()));
}

std::string Board::position_string() const {
    std::ostringstream out;
    out << "G1|" << color_char(side_to_move_) << '|' << ply_ << '|'
        << static_cast<unsigned>(turns_taken_[0]) << '|' << static_cast<unsigned>(turns_taken_[1]) << '|';
    bool first_stack = true;
    for (const auto& stack : stacks_) {
        if (!first_stack) out << ';';
        first_stack = false;
        out << stack.cell.q << ',' << stack.cell.r << '=';
        for (std::size_t i = 0; i < stack.pieces.size(); ++i) {
            if (i != 0) out << ',';
            out << piece_name(stack.pieces[i]);
        }
    }
    return out.str();
}

std::expected<Board, std::string> Board::from_position_string(std::string_view text) {
    const auto fields = split(text, '|');
    if (fields.size() != 6 || fields[0] != "G1" || (fields[1] != "w" && fields[1] != "b")) {
        return std::unexpected("invalid Genseki position header");
    }
    Board board;
    board.side_to_move_ = fields[1] == "w" ? Color::white : Color::black;
    unsigned white_turns = 0;
    unsigned black_turns = 0;
    if (!parse_integer(fields[2], board.ply_) || !parse_integer(fields[3], white_turns)
        || !parse_integer(fields[4], black_turns)
        || white_turns > std::numeric_limits<std::uint8_t>::max()
        || black_turns > std::numeric_limits<std::uint8_t>::max()) {
        return std::unexpected("invalid position counters");
    }
    board.turns_taken_ = {
        static_cast<std::uint8_t>(white_turns),
        static_cast<std::uint8_t>(black_turns),
    };
    if (!fields[5].empty()) {
        for (const auto stack_text : split(fields[5], ';')) {
            const auto equals = stack_text.find('=');
            const auto comma = stack_text.find(',');
            if (equals == std::string_view::npos || comma == std::string_view::npos || comma > equals) {
                return std::unexpected("invalid stack");
            }
            int q = 0;
            int r = 0;
            if (!parse_integer(stack_text.substr(0, comma), q)
                || !parse_integer(stack_text.substr(comma + 1, equals - comma - 1), r)) {
                return std::unexpected("invalid stack coordinate");
            }
            Stack stack{Hex{static_cast<std::int16_t>(q), static_cast<std::int16_t>(r)}, {}};
            for (const auto piece_text : split(stack_text.substr(equals + 1), ',')) {
                auto piece = parse_piece(piece_text);
                if (!piece) return std::unexpected(piece.error());
                stack.pieces.push_back(*piece);
            }
            if (stack.pieces.empty() || board.stack_at(stack.cell) != nullptr) {
                return std::unexpected("empty or duplicate stack");
            }
            board.stacks_.push_back(std::move(stack));
        }
    }
    board.normalize_stacks();
    return board;
}

std::expected<std::string, std::string> Board::uhp_move_string(const Move& move) const {
    if (move.kind == MoveKind::pass) return std::string{"pass"};
    if (!is_legal(move)) return std::unexpected("move is not legal");
    const auto moving = piece_name(move.piece);
    if (stacks_.empty()) return moving;

    Board lifted = *this;
    if (move.kind == MoveKind::movement) {
        auto* source = lifted.stack_at(*move.from);
        source->pieces.pop_back();
        if (source->pieces.empty()) {
            std::erase_if(lifted.stacks_, [move](const Stack& stack) { return stack.cell == *move.from; });
        }
    }
    if (const auto* target = lifted.stack_at(move.to); target != nullptr) {
        return moving + " " + piece_name(target->pieces.back());
    }
    for (const auto& stack : lifted.stacks_) {
        if (!adjacent(stack.cell, move.to)) continue;
        const auto reference = piece_name(stack.pieces.back());
        const auto delta = Hex{
            static_cast<std::int16_t>(move.to.q - stack.cell.q),
            static_cast<std::int16_t>(move.to.r - stack.cell.r),
        };
        if (delta == Hex{1, 0}) return moving + " " + reference + "-";
        if (delta == Hex{1, -1}) return moving + " " + reference + "/";
        if (delta == Hex{0, -1}) return moving + " \\" + reference;
        if (delta == Hex{-1, 0}) return moving + " -" + reference;
        if (delta == Hex{-1, 1}) return moving + " /" + reference;
        if (delta == Hex{0, 1}) return moving + " " + reference + "\\";
    }
    return std::unexpected("move destination has no UHP reference piece");
}

std::expected<Move, std::string> Board::parse_uhp_move(std::string_view text) const {
    if (text == "pass") return Move{.kind = MoveKind::pass};
    const auto space = text.find(' ');
    const auto moving_text = text.substr(0, space);
    auto moving = parse_piece(moving_text);
    if (!moving) return std::unexpected(moving.error());

    std::optional<Hex> source;
    for (const auto& stack : stacks_) {
        const auto it = std::ranges::find(stack.pieces, *moving);
        if (it != stack.pieces.end()) {
            source = stack.cell;
            if (it != stack.pieces.end() - 1) return std::unexpected("piece is covered");
            break;
        }
    }
    if (space == std::string_view::npos) {
        const Move move{
            source ? MoveKind::movement : MoveKind::placement,
            source,
            Hex{0, 0},
            *moving,
        };
        return is_legal(move) ? std::expected<Move, std::string>{move}
                              : std::unexpected("move is not legal");
    }

    auto reference_text = text.substr(space + 1);
    if (reference_text.empty()) return std::unexpected("missing reference piece");
    char before = 0;
    char after = 0;
    if (reference_text.front() == '-' || reference_text.front() == '/' || reference_text.front() == '\\') {
        before = reference_text.front();
        reference_text.remove_prefix(1);
    }
    if (!reference_text.empty()
        && (reference_text.back() == '-' || reference_text.back() == '/' || reference_text.back() == '\\')) {
        after = reference_text.back();
        reference_text.remove_suffix(1);
    }
    if (before != 0 && after != 0) return std::unexpected("too many separators");
    auto reference = parse_piece(reference_text);
    if (!reference) return std::unexpected(reference.error());
    std::optional<Hex> target;
    for (const auto& stack : stacks_) {
        if (std::ranges::find(stack.pieces, *reference) != stack.pieces.end()) {
            target = stack.cell;
            break;
        }
    }
    if (!target) return std::unexpected("reference piece is not in play");
    Hex destination = *target;
    if (before == '-') destination = add(*target, Hex{-1, 0});
    if (before == '/') destination = add(*target, Hex{-1, 1});
    if (before == '\\') destination = add(*target, Hex{0, -1});
    if (after == '-') destination = add(*target, Hex{1, 0});
    if (after == '/') destination = add(*target, Hex{1, -1});
    if (after == '\\') destination = add(*target, Hex{0, 1});
    const Move move{
        source ? MoveKind::movement : MoveKind::placement,
        source,
        destination,
        *moving,
    };
    return is_legal(move) ? std::expected<Move, std::string>{move}
                          : std::unexpected("move is not legal");
}

std::string Board::game_string() const {
    std::ostringstream out;
    out << "Base;";
    switch (result()) {
        case GameResult::ongoing: out << (ply_ == 0 ? "NotStarted" : "InProgress"); break;
        case GameResult::white_win: out << "WhiteWins"; break;
        case GameResult::black_win: out << "BlackWins"; break;
        case GameResult::draw: out << "Draw"; break;
    }
    out << ';' << (side_to_move_ == Color::white ? "White" : "Black")
        << '[' << static_cast<unsigned>(turns_taken_[index(side_to_move_)]) + 1 << ']';

    Board replay;
    for (const auto& move : history_) {
        auto notation = replay.uhp_move_string(move);
        out << ';' << *notation;
        replay.apply_unchecked(move);
    }
    return out.str();
}

std::expected<Board, std::string> Board::from_game_string(std::string_view text) {
    const auto fields = split(text, ';');
    if (fields.empty() || fields[0] != "Base") {
        return std::unexpected("only the UHP Base game type is supported");
    }
    if (fields.size() != 1 && fields.size() < 3) {
        return std::unexpected("invalid UHP game string");
    }
    Board board;
    for (std::size_t i = 3; i < fields.size(); ++i) {
        auto move = board.parse_uhp_move(fields[i]);
        if (!move) return std::unexpected(std::format("invalid move {}: {}", i - 2, move.error()));
        auto played = board.play(*move);
        if (!played) return std::unexpected(std::format("illegal move {}", i - 2));
    }
    if (fields.size() >= 3) {
        const auto canonical_game = board.game_string();
        const auto canonical = split(canonical_game, ';');
        if (fields[1] != canonical[1] || fields[2] != canonical[2]) {
            return std::unexpected(std::format(
                "game state or turn does not match move history (received {};{}, derived {};{})",
                fields[1],
                fields[2],
                canonical[1],
                canonical[2]));
        }
    }
    return board;
}

}  // namespace genseki
