#include "genseki/core/board.hpp"
#include "genseki/core/uhp.hpp"

#include <charconv>
#include <cstdint>
#include <iostream>
#include <filesystem>
#include <random>
#include <string>
#include <string_view>

namespace {

bool parse_unsigned(std::string_view text, unsigned& value) {
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    return error == std::errc{} && end == text.data() + text.size();
}

int run_perft(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: genseki_rules --perft DEPTH [--divide]\n";
        return 2;
    }
    unsigned depth = 0;
    if (!parse_unsigned(argv[2], depth)) {
        std::cerr << "invalid perft depth\n";
        return 2;
    }
    genseki::Board board;
    if (argc > 3 && std::string_view{argv[3]} == "--divide" && depth > 0) {
        std::uint64_t total = 0;
        for (const auto& move : board.legal_moves()) {
            const auto notation = board.uhp_move_string(move);
            const auto undo = board.make_move(move);
            const auto nodes = board.perft(depth - 1);
            board.unmake_move(*undo);
            total += nodes;
            std::cout << *notation << ": " << nodes << '\n';
        }
        std::cout << "total: " << total << '\n';
    } else {
        std::cout << board.perft(depth) << '\n';
    }
    return 0;
}

int run_stress(int argc, char** argv) {
    unsigned plies = 1000;
    if (argc > 2 && !parse_unsigned(argv[2], plies)) {
        std::cerr << "invalid stress ply count\n";
        return 2;
    }
    std::mt19937 random{0x47454e53U};
    genseki::Board board;
    for (unsigned i = 0; i < plies; ++i) {
        if (board.is_terminal()) board = genseki::Board{};
        const auto before = board.position_string();
        const auto moves = board.legal_moves();
        const auto& move = moves[random() % moves.size()];
        const auto undo = board.make_move(move);
        if (!undo) {
            std::cerr << "generated illegal move at ply " << i << '\n';
            return 1;
        }
        board.unmake_move(*undo);
        if (board.position_string() != before) {
            std::cerr << "make/unmake mismatch at ply " << i << '\n';
            return 1;
        }
        if (!board.play(move)) {
            std::cerr << "play failed at ply " << i << '\n';
            return 1;
        }
    }
    std::cout << "stress ok: " << plies << " plies\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc > 1) {
        const std::string_view command{argv[1]};
        if (command == "--perft") return run_perft(argc, argv);
        if (command == "--stress") return run_stress(argc, argv);
        if (command == "--replay") {
            if (argc < 3) {
                std::cerr << "usage: genseki_rules --replay GAMESTRING\n";
                return 2;
            }
            const auto board = genseki::Board::from_game_string(argv[2]);
            if (!board) {
                std::cerr << board.error() << '\n';
                return 1;
            }
            std::cout << board->game_string() << '\n';
            return 0;
        }
        std::cerr << "Rules service: use --perft, --stress, --replay, or no arguments for UHP. Search is in genseki (Alpha).\n";
        return 2;
    }
    genseki::UhpEngine engine;
    engine.run(std::cin, std::cout);
    return 0;
}
