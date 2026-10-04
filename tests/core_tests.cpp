#include "genseki/core/board.hpp"
#include "genseki/core/bot.hpp"

#include <cstdlib>
#include <iostream>

namespace {

void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "test failed: " << message << '\n';
        std::exit(1);
    }
}

}  // namespace

int main() {
    const genseki::Board start;
    require(start.ply() == 0, "start ply is zero");
    require(start.legal_moves().size() == 11, "start has one placement cell times eleven pieces");
    require(genseki::greek_bot_specs().size() == 24, "there are 24 greek bot slots");

    auto board = start;
    board.play(board.legal_moves().front());
    require(board.ply() == 1, "playing a move increments ply");
    require(board.stacks().size() == 1, "first placement creates one stack");
    require(board.side_to_move() == genseki::Color::black, "side to move flips");
    return 0;
}
