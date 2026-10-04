#include "genseki/core/board.hpp"
#include "genseki/core/bot.hpp"
#include "genseki/core/selfplay.hpp"
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
        std::cerr << "usage: genseki --perft DEPTH [--divide]\n";
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
        if (command == "--generate-data") {
            if (argc < 4) {
                std::cerr << "usage: genseki --generate-data PATH GAMES [MAX_PLIES] [SEED]\n";
                return 2;
            }
            unsigned games = 0;
            unsigned max_plies = 96;
            unsigned seed = 0x47454e53U;
            if (!parse_unsigned(argv[3], games)
                || (argc > 4 && !parse_unsigned(argv[4], max_plies))
                || (argc > 5 && !parse_unsigned(argv[5], seed))) {
                std::cerr << "invalid dataset arguments\n";
                return 2;
            }
            try {
                const auto stats = genseki::generate_training_data(argv[2], games, max_plies, seed);
                std::cout << genseki::to_json(stats) << '\n';
                return 0;
            } catch (const std::exception& error) {
                std::cerr << error.what() << '\n';
                return 1;
            }
        }
        if (command == "--replay") {
            if (argc < 3) {
                std::cerr << "usage: genseki --replay GAMESTRING\n";
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
        if (command == "--about") {
            std::cout << "Genseki Hive bot lab\n";
            for (const auto spec : genseki::greek_bot_specs()) {
                if (spec.enabled) {
                    std::cout << spec.letter << " evaluator=" << genseki::name(spec.evaluator)
                              << " depth=" << static_cast<int>(spec.search_depth) << '\n';
                }
            }
            return 0;
        }
        std::filesystem::path model;
        unsigned threads = 1;
        unsigned table_mib = 64;
        unsigned move_ms = 230;
        for (int i = 1; i < argc; ++i) {
            const std::string_view option{argv[i]};
            if (option == "--model" && i + 1 < argc) model = argv[++i];
            else if (option == "--threads" && i + 1 < argc && parse_unsigned(argv[++i], threads)) {}
            else if (option == "--table-mib" && i + 1 < argc && parse_unsigned(argv[++i], table_mib)) {}
            else if (option == "--move-ms" && i + 1 < argc && parse_unsigned(argv[++i], move_ms)) {}
            else {
                std::cerr << "unknown or invalid option\n";
                return 2;
            }
        }
        if (threads == 0 || threads > 12 || table_mib == 0 || move_ms == 0) {
            std::cerr << "engine option out of range\n";
            return 2;
        }
        genseki::UhpEngine engine{
            model, threads, table_mib, std::chrono::milliseconds{move_ms}};
        engine.run(std::cin, std::cout);
        return 0;
    }
    genseki::UhpEngine engine;
    engine.run(std::cin, std::cout);
    return 0;
}
