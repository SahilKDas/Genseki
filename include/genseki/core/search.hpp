#pragma once

#include "genseki/core/board.hpp"

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <vector>

namespace genseki {

struct SearchLimits {
    unsigned max_depth = 64;
    std::chrono::milliseconds time{230};
    unsigned threads = 1;
    std::size_t table_mib = 64;
};

struct SearchResult {
    Move move{};
    int score = 0;
    unsigned depth = 0;
    std::uint64_t nodes = 0;
    std::chrono::milliseconds elapsed{0};
    std::vector<Move> principal_variation{};
};

class NnueEvaluator {
public:
    [[nodiscard]] bool load(const std::filesystem::path& path);
    [[nodiscard]] bool loaded() const;
    [[nodiscard]] int evaluate(const Board& board) const;

private:
    std::uint32_t width_ = 0;
    std::vector<float> accumulator_weights_{};
    std::vector<float> accumulator_bias_{};
    std::vector<float> output_weights_{};
    float output_bias_ = 0.0F;
};

class SearchEngine {
public:
    explicit SearchEngine(std::size_t table_mib = 64);
    [[nodiscard]] SearchResult search(
        Board& board,
        const SearchLimits& limits,
        const NnueEvaluator* evaluator = nullptr);

private:
    enum class Bound : std::uint8_t { none, exact, lower, upper };
    struct Entry {
        std::uint64_t key = 0;
        Move best{};
        int score = 0;
        std::int16_t depth = -1;
        Bound bound = Bound::none;
    };

    std::vector<Entry> table_{};
    std::chrono::steady_clock::time_point deadline_{};
    const NnueEvaluator* evaluator_ = nullptr;
    std::uint64_t nodes_ = 0;
    bool stopped_ = false;

    [[nodiscard]] int negamax(
        Board& board,
        int depth,
        int alpha,
        int beta,
        std::vector<std::uint64_t>& path,
        std::vector<Move>& pv);
    [[nodiscard]] int static_evaluation(const Board& board) const;
    [[nodiscard]] std::uint64_t hash(const Board& board, bool include_ply = true) const;
    [[nodiscard]] int move_order_score(Board& board, const Move& move, const Move* tt_move);
};

}  // namespace genseki
