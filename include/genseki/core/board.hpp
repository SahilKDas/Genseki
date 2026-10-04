#pragma once

#include "genseki/core/hex.hpp"
#include "genseki/core/piece.hpp"

#include <array>
#include <optional>
#include <string>
#include <vector>

namespace genseki {

struct Stack {
    Hex cell{};
    std::vector<Piece> pieces{};
};

struct Move {
    std::optional<Hex> from{};
    Hex to{};
    Piece piece{};
};

class Board {
public:
    [[nodiscard]] Color side_to_move() const;
    [[nodiscard]] std::size_t ply() const;
    [[nodiscard]] const std::vector<Stack>& stacks() const;
    [[nodiscard]] std::vector<Move> legal_moves() const;
    [[nodiscard]] bool is_terminal() const;
    [[nodiscard]] std::optional<Color> winner() const;
    [[nodiscard]] std::string summary() const;

    void play(const Move& move);

private:
    Color side_to_move_ = Color::white;
    std::size_t ply_ = 0;
    std::vector<Stack> stacks_{};
    std::array<std::uint8_t, 2> queens_played_{0, 0};

    [[nodiscard]] const Stack* stack_at(Hex cell) const;
    [[nodiscard]] Stack* stack_at(Hex cell);
    [[nodiscard]] bool occupied(Hex cell) const;
    [[nodiscard]] std::vector<Hex> placement_cells() const;
    [[nodiscard]] std::vector<Piece> pieces_in_hand(Color color) const;
};

}  // namespace genseki
