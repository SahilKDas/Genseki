#include "genseki/core/board.hpp"

#include <algorithm>
#include <format>
#include <ranges>

namespace genseki {

Color Board::side_to_move() const {
    return side_to_move_;
}

std::size_t Board::ply() const {
    return ply_;
}

const std::vector<Stack>& Board::stacks() const {
    return stacks_;
}

const Stack* Board::stack_at(Hex cell) const {
    const auto it = std::ranges::find_if(stacks_, [cell](const Stack& stack) {
        return stack.cell == cell;
    });
    return it == stacks_.end() ? nullptr : &*it;
}

Stack* Board::stack_at(Hex cell) {
    const auto it = std::ranges::find_if(stacks_, [cell](const Stack& stack) {
        return stack.cell == cell;
    });
    return it == stacks_.end() ? nullptr : &*it;
}

bool Board::occupied(Hex cell) const {
    return stack_at(cell) != nullptr;
}

std::vector<Piece> Board::pieces_in_hand(Color color) const {
    std::array<std::uint8_t, 5> used{};
    for (const auto& stack : stacks_) {
        for (const auto& piece : stack.pieces) {
            if (piece.color == color) {
                ++used[static_cast<std::size_t>(piece.bug)];
            }
        }
    }

    const std::array<std::uint8_t, 5> inventory{1, 2, 2, 3, 3};
    std::vector<Piece> pieces;
    for (std::size_t bug_index = 0; bug_index < inventory.size(); ++bug_index) {
        for (std::uint8_t id = used[bug_index]; id < inventory[bug_index]; ++id) {
            pieces.push_back(Piece{
                .color = color,
                .bug = static_cast<Bug>(bug_index),
                .id = id,
            });
        }
    }
    return pieces;
}

std::vector<Hex> Board::placement_cells() const {
    if (stacks_.empty()) {
        return {Hex{0, 0}};
    }

    std::vector<Hex> cells;
    for (const auto& stack : stacks_) {
        for (const auto dir : directions) {
            const Hex candidate = add(stack.cell, dir);
            if (occupied(candidate)) {
                continue;
            }
            if (std::ranges::find(cells, candidate) == cells.end()) {
                cells.push_back(candidate);
            }
        }
    }
    return cells;
}

std::vector<Move> Board::legal_moves() const {
    std::vector<Move> moves;
    for (const auto& piece : pieces_in_hand(side_to_move_)) {
        for (const auto cell : placement_cells()) {
            moves.push_back(Move{
                .from = std::nullopt,
                .to = cell,
                .piece = piece,
            });
        }
    }
    return moves;
}

void Board::play(const Move& move) {
    auto* target = stack_at(move.to);
    if (target == nullptr) {
        stacks_.push_back(Stack{.cell = move.to, .pieces = {move.piece}});
    } else {
        target->pieces.push_back(move.piece);
    }
    if (move.piece.bug == Bug::queen) {
        queens_played_[static_cast<std::size_t>(move.piece.color)] = 1;
    }
    side_to_move_ = other(side_to_move_);
    ++ply_;
}

bool Board::is_terminal() const {
    return winner().has_value();
}

std::optional<Color> Board::winner() const {
    // Placeholder until full Hive adjacency and queen-surround logic lands.
    return std::nullopt;
}

std::string Board::summary() const {
    return std::format(
        "ply={} side={} stacks={} legal_moves={}",
        ply_,
        side_to_move_ == Color::white ? "white" : "black",
        stacks_.size(),
        legal_moves().size());
}

}  // namespace genseki
