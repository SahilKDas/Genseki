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

}  // namespace

std::vector<std::string> UhpEngine::startup() const {
    return {"id Genseki rules service v0.1.0", "ok"};
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
    if (command == "options") return {"ok"};
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
    if (command == "bestmove") return error("Rules-only service; use genseki (Alpha) for search.");
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
