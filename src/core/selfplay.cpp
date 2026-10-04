#include "genseki/core/selfplay.hpp"

#include "genseki/core/board.hpp"

#include <algorithm>
#include <cmath>
#include <format>
#include <fstream>
#include <random>
#include <stdexcept>
#include <vector>

namespace genseki {
namespace {

unsigned queen_neighbors(const Board& board, Color color) {
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

double white_score(const Board& board) {
    switch (board.result()) {
        case GameResult::white_win: return 1.0;
        case GameResult::black_win: return -1.0;
        case GameResult::draw: return 0.0;
        case GameResult::ongoing: break;
    }
    const auto pressure = static_cast<int>(queen_neighbors(board, Color::black))
        - static_cast<int>(queen_neighbors(board, Color::white));
    return std::tanh(static_cast<double>(pressure) / 2.5);
}

Move select_move(Board& board, std::mt19937& random) {
    const auto moves = board.legal_moves();
    if (moves.size() == 1) return moves.front();
    if (random() % 100 < 18) return moves[random() % moves.size()];

    const auto mover = board.side_to_move();
    double best = -1e9;
    std::vector<std::size_t> choices;
    for (std::size_t i = 0; i < moves.size(); ++i) {
        auto undo = board.make_move(moves[i]);
        double value = white_score(board) * (mover == Color::white ? 1.0 : -1.0);
        value += static_cast<double>(random() % 1000) * 1e-7;
        board.unmake_move(*undo);
        if (value > best + 1e-9) {
            best = value;
            choices = {i};
        } else if (std::abs(value - best) <= 1e-9) {
            choices.push_back(i);
        }
    }
    return moves[choices[random() % choices.size()]];
}

}  // namespace

DatasetStats generate_training_data(
    const std::filesystem::path& output,
    unsigned games,
    unsigned max_plies,
    std::uint32_t seed) {
    if (games == 0 || max_plies == 0) throw std::invalid_argument("games and max_plies must be positive");
    std::filesystem::create_directories(output.parent_path());
    std::ofstream stream{output, std::ios::trunc};
    if (!stream) throw std::runtime_error("unable to open training data output");
    stream << "game\tply\tlabel\tfinish\tposition\n";

    DatasetStats stats{.games = games};
    std::mt19937 random{seed};
    for (unsigned game = 0; game < games; ++game) {
        Board board;
        std::vector<std::pair<unsigned, std::string>> positions;
        positions.emplace_back(0, board.position_string());
        while (!board.is_terminal() && board.ply() < max_plies) {
            const auto move = select_move(board, random);
            if (!board.play(move)) throw std::runtime_error("self-play generated an illegal move");
            if (board.ply() >= 6 && (board.ply() % 2 == game % 2)) {
                positions.emplace_back(static_cast<unsigned>(board.ply()), board.position_string());
            }
        }
        const bool terminal = board.is_terminal();
        stats.terminal_games += terminal ? 1U : 0U;
        stats.adjudicated_games += terminal ? 0U : 1U;
        const auto label = white_score(board);
        for (const auto& [ply, position] : positions) {
            stream << game << '\t' << ply << '\t' << std::format("{:.6f}", label) << '\t'
                   << (terminal ? "terminal" : "adjudicated") << '\t' << position << '\n';
            ++stats.positions;
        }
    }
    return stats;
}

std::string to_json(const DatasetStats& stats) {
    return std::format(
        "{{\"games\":{},\"terminal_games\":{},\"adjudicated_games\":{},\"positions\":{}}}",
        stats.games,
        stats.terminal_games,
        stats.adjudicated_games,
        stats.positions);
}

}  // namespace genseki
