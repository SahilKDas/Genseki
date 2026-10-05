#include "genseki/core/board.hpp"
#include "genseki/core/uhp.hpp"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <chrono>
#include <string>
#include <vector>

namespace {

void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "test failed: " << message << '\n';
        std::exit(1);
    }
}

genseki::Board position(std::string_view value) {
    auto board = genseki::Board::from_position_string(value);
    if (!board) {
        std::cerr << "bad test position: " << board.error() << '\n';
        std::exit(1);
    }
    return *board;
}

bool has_move(
    const genseki::Board& board,
    genseki::Bug bug,
    genseki::Hex from,
    genseki::Hex to) {
    return std::ranges::any_of(board.legal_moves(), [&](const genseki::Move& move) {
        return move.kind == genseki::MoveKind::movement && move.piece.bug == bug
            && move.from == from && move.to == to;
    });
}

void opening_and_queen_deadline() {
    genseki::Board board;
    const auto opening = board.legal_moves();
    require(opening.size() == 4, "opening has one canonical non-queen move per bug");
    require(std::ranges::none_of(opening, [](const genseki::Move& move) {
        return move.piece.bug == genseki::Bug::queen;
    }), "queen cannot be the first piece");

    for (int ply = 0; ply < 6; ++ply) {
        const auto moves = board.legal_moves();
        const auto move = std::ranges::find_if(moves, [](const genseki::Move& candidate) {
            return candidate.kind == genseki::MoveKind::placement
                && candidate.piece.bug != genseki::Bug::queen;
        });
        require(move != moves.end(), "non-queen opening move exists");
        require(board.play(*move).has_value(), "opening move plays");
    }
    const auto forced = board.legal_moves();
    require(!forced.empty(), "fourth turn has moves");
    require(std::ranges::all_of(forced, [](const genseki::Move& move) {
        return move.kind == genseki::MoveKind::placement
            && move.piece.bug == genseki::Bug::queen;
    }), "queen is forced on a player's fourth turn");
}

void piece_movement() {
    auto grasshopper = position(
        "G1|w|8|4|4|-1,0=wQ;-1,1=wA1;0,1=wA2;0,0=wG1;1,0=bQ;2,0=bA1");
    require(has_move(grasshopper, genseki::Bug::grasshopper, {0, 0}, {3, 0}),
        "grasshopper jumps contiguous line");
    require(!has_move(grasshopper, genseki::Bug::grasshopper, {0, 0}, {1, 0}),
        "grasshopper cannot land on jumped piece");

    auto beetle = position(
        "G1|w|8|4|4|-1,0=wQ;-1,1=wA1;0,1=wA2;0,0=wB1;1,0=bQ");
    require(has_move(beetle, genseki::Bug::beetle, {0, 0}, {1, 0}),
        "beetle climbs occupied cell");

    auto open_gap_beetle = position(
        "G1|w|48|24|24|-4,2=bA3;-3,1=wA3;-2,-1=bA2;-2,0=bQ;-2,1=bS1;"
        "-2,2=bA1;-1,1=bB1;-1,3=wA2;0,-2=wB1;0,-1=wQ;0,0=wG1;0,2=wG3;"
        "1,-2=wS1;1,0=wA1;1,1=wG2;2,-2=wS2;3,-3=wB2");
    require(!has_move(open_gap_beetle, genseki::Bug::beetle, {0, -2}, {-1, -2}),
        "ground beetle cannot cross a zero-flank gap");

    auto crawlers = position(
        "G1|w|8|4|4|-1,0=wQ;0,0=wA1;1,0=bQ;1,-1=bG1;0,-1=wS1");
    const auto ant_moves = std::ranges::count_if(crawlers.legal_moves(), [](const genseki::Move& move) {
        return move.kind == genseki::MoveKind::movement && move.piece.bug == genseki::Bug::ant;
    });
    const auto spider_moves = std::ranges::count_if(crawlers.legal_moves(), [](const genseki::Move& move) {
        return move.kind == genseki::MoveKind::movement && move.piece.bug == genseki::Bug::spider;
    });
    require(ant_moves > 0, "ant crawls around hive");
    require(spider_moves > 0, "spider has exact-three-step destinations");
}

void connectivity_and_results() {
    auto pinned = position("G1|w|8|4|4|-1,0=bQ;0,0=wA1;1,0=wQ");
    require(std::ranges::none_of(pinned.legal_moves(), [](const genseki::Move& move) {
        return move.kind == genseki::MoveKind::movement && move.from == genseki::Hex{0, 0};
    }), "articulation piece cannot split the hive");

    auto black_loses = position(
        "G1|w|12|6|6|0,0=bQ;1,0=wQ;1,-1=wA1;0,-1=wA2;-1,0=wA3;-1,1=wB1;0,1=wB2");
    require(black_loses.result() == genseki::GameResult::white_win, "surrounded black queen loses");
    require(black_loses.legal_moves().empty(), "terminal board has no moves");

    auto draw = position(
        "G1|w|12|6|6|0,0=bQ;1,0=wQ;1,-1=wA1;0,-1=wA2;-1,0=wA3;-1,1=wB1;0,1=wB2;"
        "2,0=bA1;2,-1=bA2;1,1=bA3;0,2=bB1;1,2=bB2;2,1=bG1");
    require(draw.result() == genseki::GameResult::draw, "simultaneous surround is a draw");
}

void state_integrity_and_perft() {
    genseki::Board board;
    require(board.perft(0) == 1, "perft zero is one");
    require(board.perft(1) == board.legal_moves().size(), "perft one equals legal moves");
    require(board.perft(1) == 4, "base opening perft one is four");
    require(board.perft(2) == 96, "base opening perft two matches reference");
    require(board.perft(3) == 1440, "base opening perft three matches reference");

    const auto move = board.legal_moves().front();
    const auto before = board.position_string();
    auto undo = board.make_move(move);
    require(undo.has_value(), "generated move can be made");
    board.unmake_move(*undo);
    require(board.position_string() == before, "make/unmake restores exact position");

    auto round_trip = genseki::Board::from_position_string(before);
    require(round_trip && round_trip->position_string() == before, "position serialization round trips");
}

void uhp_protocol() {
    genseki::UhpEngine engine;
    require(engine.startup() == std::vector<std::string>({"id Genseki rules service v0.1.0", "ok"}),
        "UHP startup identifies engine");
    require(engine.execute("newgame") == std::vector<std::string>({"Base;NotStarted;White[1]", "ok"}),
        "UHP newgame returns game string");
    require(engine.execute("validmoves")
        == std::vector<std::string>({"wS1;wB1;wG1;wA1", "ok"}),
        "UHP opening validmoves uses standard notation");
    require(engine.execute("genseki-children").size() == 5,
        "unbounded child command returns every legal move plus ok");
    require(engine.execute("play wS1")
        == std::vector<std::string>({"Base;InProgress;Black[1];wS1", "ok"}),
        "UHP play updates game string");
    require(engine.execute("undo")
        == std::vector<std::string>({"Base;NotStarted;White[1]", "ok"}),
        "UHP undo restores game");
    require(engine.execute("bestmove depth 1").front().starts_with("err "),
        "rules service does not contain a retired evaluator");

    auto loaded = genseki::Board::from_game_string(
        "Base;InProgress;White[2];wS1;bS1 wS1-");
    require(loaded && loaded->ply() == 2, "UHP game string replays");
    require(loaded->game_string() == "Base;InProgress;White[2];wS1;bS1 wS1-",
        "UHP game string round trips");
}

}  // namespace

int main() {
    opening_and_queen_deadline();
    piece_movement();
    connectivity_and_results();
    state_integrity_and_perft();
    uhp_protocol();
    return 0;
}
