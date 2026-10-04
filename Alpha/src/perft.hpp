#pragma once

#include <cstdint>
#include <map>

inline std::uint64_t perft(Board& board, unsigned depth) {
    if (depth == 0) return 1;
    std::uint64_t nodes = 0;
    for (const auto& move : board.legal_moves()) {
        board.apply(move);
        nodes += perft(board, depth - 1);
        board.undo();
    }
    return nodes;
}

inline std::map<std::string, std::uint64_t> perft_divide(Board& board, unsigned depth) {
    std::map<std::string, std::uint64_t> result;
    if (depth == 0) return result;
    for (const auto& move : board.legal_moves()) {
        const auto notation = board.move_string(move);
        board.apply(move);
        result[notation] = perft(board, depth - 1);
        board.undo();
    }
    return result;
}
