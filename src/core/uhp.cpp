#include "genseki/core/uhp.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <sstream>

namespace genseki {
namespace {

std::string trim(std::string_view value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string_view::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return std::string{value.substr(first, last - first + 1)};
}

std::pair<std::string, std::string> command_and_args(std::string_view line) {
    const auto cleaned = trim(line);
    const auto space = cleaned.find(' ');
    if (space == std::string::npos) return {cleaned, {}};
    return {cleaned.substr(0, space), trim(std::string_view{cleaned}.substr(space + 1))};
}

unsigned queen_pressure(const Board& board, Color color) {
    std::optional<Hex> queen;
    for (const auto& stack : board.stacks()) {
        for (const auto piece : stack.pieces) {
            if (piece.color == color && piece.bug == Bug::queen) queen = stack.cell;
        }
    }
    if (!queen) return 0;
    return static_cast<unsigned>(std::ranges::count_if(directions, [&](Hex direction) {
        return std::ranges::any_of(board.stacks(), [&](const Stack& stack) {
            return stack.cell == add(*queen, direction);
        });
    }));
}

}  // namespace

UhpEngine::UhpEngine(
    std::filesystem::path model,
    unsigned threads,
    std::size_t table_mib,
    std::chrono::milliseconds move_time)
    : search_(table_mib),
      threads_(std::clamp(threads, 1U, 12U)),
      table_mib_(table_mib),
      move_time_(move_time) {
    if (!model.empty() && !evaluator_.load(model)) {
        throw std::runtime_error("Unable to load NNUE model: " + model.string());
    }
}

std::vector<std::string> UhpEngine::startup() const {
    return {"id Genseki v0.1.0", "ok"};
}

std::vector<std::string> UhpEngine::error(std::string message) const {
    return {"err " + std::move(message), "ok"};
}

bool UhpEngine::exit_requested() const { return exit_requested_; }

std::vector<std::string> UhpEngine::execute(std::string_view line) {
    const auto [command, args] = command_and_args(line);
    if (command == "info") {
        return startup();
    }
    if (command == "exit") {
        exit_requested_ = true;
        return {};
    }
    if (command == "newgame") {
        if (args.empty() || args == "Base") {
            board_ = Board{};
        } else {
            auto loaded = Board::from_game_string(args);
            if (!loaded) return error(loaded.error());
            board_ = std::move(*loaded);
        }
        return {board_->game_string(), "ok"};
    }
    if (command == "options") {
        if (!args.empty()) return error("Genseki options are fixed at launch.");
        return {
            "NumThreads;int;" + std::to_string(threads_) + ";"
                + std::to_string(threads_) + ";1;12",
            "TableSizeMiB;int;" + std::to_string(table_mib_) + ";"
                + std::to_string(table_mib_) + ";1;512",
            "ok",
        };
    }
    if (!board_) {
        return error("No game in progress. Try 'newgame' to start a new game.");
    }
    if (command == "undo") {
        unsigned count = 1;
        if (!args.empty()) {
            const auto [end, ec] = std::from_chars(args.data(), args.data() + args.size(), count);
            if (ec != std::errc{} || end != args.data() + args.size() || count == 0) {
                return error("Unable to undo that many moves.");
            }
        }
        if (!board_->undo(count)) return error("Unable to undo that many moves.");
        return {board_->game_string(), "ok"};
    }
    if (command == "genseki-position") {
        return {board_->position_string(), "ok"};
    }
    if (command == "genseki-searchinfo") {
        if (!last_search_) return error("No completed search.");
        std::ostringstream info;
        info << "depth=" << last_search_->depth
             << " nodes=" << last_search_->nodes
             << " elapsed_ms=" << last_search_->elapsed.count()
             << " score=" << last_search_->score
             << " pv=";
        bool first = true;
        Board replay = *board_;
        for (const auto& move : last_search_->principal_variation) {
            const auto notation = replay.uhp_move_string(move);
            if (!notation) break;
            if (!first) info << '|';
            first = false;
            info << *notation;
            if (!replay.make_move(move)) break;
        }
        return {info.str(), "ok"};
    }
    if (command == "genseki-children") {
        std::vector<std::string> response;
        const auto moves = board_->legal_moves();
        auto limit = static_cast<unsigned>(moves.size());
        if (!args.empty()) {
            const auto [end, ec] = std::from_chars(args.data(), args.data() + args.size(), limit);
            if (ec != std::errc{} || end != args.data() + args.size() || limit == 0) {
                return error("genseki-children requires a positive limit.");
            }
        }
        const auto count = std::min<std::size_t>(moves.size(), limit);
        for (std::size_t sample = 0; sample < count; ++sample) {
            const auto move_index = count == moves.size() || count == 1
                ? sample
                : sample * (moves.size() - 1) / (count - 1);
            const auto& move = moves[move_index];
            auto notation = board_->uhp_move_string(move);
            auto undo = board_->make_move(move);
            response.push_back(*notation + "\t" + board_->position_string());
            board_->unmake_move(*undo);
        }
        response.push_back("ok");
        return response;
    }
    if (command == "genseki-pressuremove") {
        const auto mover = board_->side_to_move();
        const auto moves = board_->legal_moves();
        const auto count = std::min<std::size_t>(moves.size(), 16);
        std::size_t selected = 0;
        int best = -1000000;
        for (std::size_t sample = 0; sample < count; ++sample) {
            const auto i = count == moves.size() || count == 1
                ? sample
                : sample * (moves.size() - 1) / (count - 1);
            auto undo = board_->make_move(moves[i]);
            int score = static_cast<int>(queen_pressure(*board_, other(mover))) * 10
                - static_cast<int>(queen_pressure(*board_, mover)) * 7;
            if (board_->result() == (mover == Color::white
                    ? GameResult::white_win : GameResult::black_win)) {
                score += 100000;
            }
            board_->unmake_move(*undo);
            if (score > best) {
                best = score;
                selected = i;
            }
        }
        auto notation = board_->uhp_move_string(moves[selected]);
        return {*notation, "ok"};
    }
    if (board_->is_terminal()) {
        return error("The game is over. Try 'newgame' to start a new game.");
    }
    if (command == "validmoves") {
        if (!args.empty()) return error("validmoves takes no parameters.");
        std::ostringstream moves;
        bool first = true;
        for (const auto& move : board_->legal_moves()) {
            auto notation = board_->uhp_move_string(move);
            if (!notation) return error(notation.error());
            if (!first) moves << ';';
            first = false;
            moves << *notation;
        }
        return {moves.str(), "ok"};
    }
    if (command == "play" || command == "pass") {
        const auto move_text = command == "pass" ? std::string{"pass"} : args;
        auto move = board_->parse_uhp_move(move_text);
        if (!move) return {"invalidmove " + move.error(), "ok"};
        auto played = board_->play(*move);
        if (!played) return {"invalidmove Unable to play that move at this time.", "ok"};
        return {board_->game_string(), "ok"};
    }
    if (command == "bestmove") {
        const auto [limit, value] = command_and_args(args);
        if ((limit != "depth" && limit != "time") || value.empty()) {
            return error("Expected 'bestmove depth N' or 'bestmove time hh:mm:ss'.");
        }
        unsigned requested_depth = 64;
        auto requested_time = move_time_;
        if (limit == "depth") {
            unsigned depth = 0;
            const auto [end, ec] = std::from_chars(value.data(), value.data() + value.size(), depth);
            if (ec != std::errc{} || end != value.data() + value.size()) {
                return error("MaxDepth must be a non-negative integer.");
            }
            requested_depth = depth;
        } else {
            const auto first = value.find(':');
            const auto second = value.find(':', first == std::string::npos ? first : first + 1);
            if (first == std::string::npos || second == std::string::npos) {
                return error("MaxTime must use hh:mm:ss.");
            }
            unsigned hours = 0;
            unsigned minutes = 0;
            const auto hour_text = std::string_view{value}.substr(0, first);
            const auto minute_text = std::string_view{value}.substr(first + 1, second - first - 1);
            const auto [hour_end, hour_error] = std::from_chars(
                hour_text.data(), hour_text.data() + hour_text.size(), hours);
            const auto [minute_end, minute_error] = std::from_chars(
                minute_text.data(), minute_text.data() + minute_text.size(), minutes);
            double seconds = 0.0;
            try {
                seconds = std::stod(value.substr(second + 1));
            } catch (...) {
                return error("MaxTime must use hh:mm:ss.");
            }
            if (hour_error != std::errc{} || hour_end != hour_text.end()
                || minute_error != std::errc{} || minute_end != minute_text.end()
                || minutes > 59 || seconds < 0.0 || seconds >= 60.0) {
                return error("MaxTime must use hh:mm:ss.");
            }
            requested_time = std::chrono::milliseconds{static_cast<std::int64_t>(
                (hours * 3600.0 + minutes * 60.0 + seconds) * 1000.0)};
        }
        SearchLimits limits{
            .max_depth = requested_depth,
            .time = std::min(requested_time, move_time_),
            .threads = threads_,
            .table_mib = table_mib_,
        };
        last_search_ = search_.search(
            *board_,
            limits,
            evaluator_.loaded() ? &evaluator_ : nullptr);
        auto notation = board_->uhp_move_string(last_search_->move);
        return {*notation, "ok"};
    }
    return error("Invalid command.");
}

void UhpEngine::run(std::istream& input, std::ostream& output) {
    for (const auto& line : startup()) output << line << '\n';
    output.flush();
    std::string line;
    while (!exit_requested_ && std::getline(input, line)) {
        for (const auto& response : execute(line)) output << response << '\n';
        output.flush();
    }
}

}  // namespace genseki
