#pragma once

#include "genseki/core/hex.hpp"
#include "genseki/core/piece.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace genseki {

struct Stack {
    Hex cell{};
    std::vector<Piece> pieces{};
    auto operator<=>(const Stack&) const = default;
};

enum class MoveKind : std::uint8_t { placement, movement, pass };

struct Move {
    MoveKind kind = MoveKind::placement;
    std::optional<Hex> from{};
    Hex to{};
    Piece piece{};
    auto operator<=>(const Move&) const = default;
};

enum class GameResult : std::uint8_t { ongoing, white_win, black_win, draw };
enum class MoveError : std::uint8_t { game_over, illegal_move };

struct Undo {
    Move move{};
    Color previous_side = Color::white;
    std::size_t previous_ply = 0;
    std::array<std::uint8_t, 2> previous_turns{};
    std::size_t previous_history_size = 0;
};

[[nodiscard]] std::string move_notation(const Move& move);
[[nodiscard]] std::expected<Move, std::string> parse_move(std::string_view text);
[[nodiscard]] std::string_view name(GameResult result);
[[nodiscard]] std::string_view name(MoveError error);

class Board {
public:
    [[nodiscard]] Color side_to_move() const;
    [[nodiscard]] std::size_t ply() const;
    [[nodiscard]] const std::vector<Stack>& stacks() const;
    [[nodiscard]] const std::vector<Move>& history() const;
    [[nodiscard]] std::vector<Move> legal_moves() const;
    [[nodiscard]] bool is_legal(const Move& move) const;
    [[nodiscard]] bool is_terminal() const;
    [[nodiscard]] GameResult result() const;
    [[nodiscard]] std::string summary() const;
    [[nodiscard]] std::string position_string() const;
    [[nodiscard]] std::string game_string() const;
    [[nodiscard]] std::expected<std::string, std::string> uhp_move_string(const Move& move) const;
    [[nodiscard]] std::expected<Move, std::string> parse_uhp_move(std::string_view text) const;

    [[nodiscard]] std::expected<void, MoveError> play(const Move& move);
    [[nodiscard]] std::expected<Undo, MoveError> make_move(const Move& move);
    void unmake_move(const Undo& undo);
    [[nodiscard]] std::uint64_t perft(unsigned depth);
    [[nodiscard]] bool undo(unsigned count = 1);

    [[nodiscard]] static std::expected<Board, std::string> from_position_string(std::string_view text);
    [[nodiscard]] static std::expected<Board, std::string> from_game_string(std::string_view text);

private:
    Color side_to_move_ = Color::white;
    std::size_t ply_ = 0;
    std::vector<Stack> stacks_{};
    std::array<std::uint8_t, 2> turns_taken_{0, 0};
    std::vector<Move> history_{};

    [[nodiscard]] const Stack* stack_at(Hex cell) const;
    [[nodiscard]] Stack* stack_at(Hex cell);
    [[nodiscard]] bool occupied(Hex cell) const;
    [[nodiscard]] std::size_t height(Hex cell) const;
    [[nodiscard]] std::vector<Hex> placement_cells() const;
    [[nodiscard]] std::vector<Piece> pieces_in_hand(Color color) const;
    [[nodiscard]] bool queen_played(Color color) const;
    [[nodiscard]] std::optional<Hex> queen_cell(Color color) const;
    [[nodiscard]] bool hive_connected_after_lift(Hex cell) const;
    [[nodiscard]] bool touches_hive(Hex cell) const;
    [[nodiscard]] bool can_slide(Hex from, Hex to) const;
    [[nodiscard]] bool beetle_gate_open(Hex from, Hex to, std::size_t source_height) const;
    [[nodiscard]] std::vector<Hex> movement_destinations(Hex from, const Piece& piece) const;
    [[nodiscard]] std::vector<Hex> ground_crawl(Hex start, bool exactly_three) const;

    void apply_unchecked(const Move& move);
    void undo_unchecked(const Undo& undo);
    void normalize_stacks();
};

}  // namespace genseki
