#include "genseki/core/search.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <ranges>

namespace genseki {
namespace {

constexpr int infinity = 1'000'000;
constexpr int mate = 900'000;

std::uint64_t mix(std::uint64_t value) {
    value ^= value >> 30;
    value *= 0xbf58476d1ce4e5b9ULL;
    value ^= value >> 27;
    value *= 0x94d049bb133111ebULL;
    return value ^ (value >> 31);
}

unsigned pressure(const Board& board, Color color) {
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

std::size_t piece_slot(Piece piece) {
    constexpr std::array<std::size_t, 5> offsets{0, 1, 3, 5, 8};
    return (piece.color == Color::white ? 0U : 11U)
        + offsets[static_cast<std::size_t>(piece.bug)]
        + (piece.bug == Bug::queen ? 0U : piece.id);
}

std::array<float, 128> encode(const Board& board) {
    std::array<float, 128> vector{};
    int min_q = 0, max_q = 0, min_r = 0, max_r = 0;
    double sum_q = 0.0, sum_r = 0.0;
    unsigned white_top = 0, black_top = 0, white_covered = 0, black_covered = 0;
    unsigned max_height = 0;
    bool first = true;
    for (const auto& stack : board.stacks()) {
        if (first) {
            min_q = max_q = stack.cell.q;
            min_r = max_r = stack.cell.r;
            first = false;
        }
        min_q = std::min(min_q, static_cast<int>(stack.cell.q));
        max_q = std::max(max_q, static_cast<int>(stack.cell.q));
        min_r = std::min(min_r, static_cast<int>(stack.cell.r));
        max_r = std::max(max_r, static_cast<int>(stack.cell.r));
        sum_q += stack.cell.q;
        sum_r += stack.cell.r;
        max_height = std::max(max_height, static_cast<unsigned>(stack.pieces.size()));
        for (std::size_t height = 0; height < stack.pieces.size(); ++height) {
            const auto piece = stack.pieces[height];
            const auto base = piece_slot(piece) * 5;
            vector[base] = 1.0F;
            vector[base + 1] = std::clamp(stack.cell.q / 8.0F, -1.0F, 1.0F);
            vector[base + 2] = std::clamp(stack.cell.r / 8.0F, -1.0F, 1.0F);
            vector[base + 3] = static_cast<float>(height) / 3.0F;
            const bool top = height + 1 == stack.pieces.size();
            vector[base + 4] = top ? 1.0F : 0.0F;
            if (top) {
                (piece.color == Color::white ? white_top : black_top)++;
            } else {
                (piece.color == Color::white ? white_covered : black_covered)++;
            }
        }
    }
    const auto count = board.stacks().size();
    const auto white_pressure = pressure(board, Color::white) / 6.0F;
    const auto black_pressure = pressure(board, Color::black) / 6.0F;
    vector[110] = board.side_to_move() == Color::white ? 1.0F : -1.0F;
    vector[111] = std::min<std::size_t>(board.ply(), 96) / 96.0F;
    vector[112] = ((board.ply() + 1) / 2.0F) / 11.0F;
    vector[113] = (board.ply() / 2.0F) / 11.0F;
    vector[114] = white_pressure;
    vector[115] = black_pressure;
    vector[116] = count / 22.0F;
    vector[117] = max_height / 4.0F;
    vector[118] = white_top / 11.0F;
    vector[119] = black_top / 11.0F;
    vector[120] = white_covered / 11.0F;
    vector[121] = black_covered / 11.0F;
    vector[122] = count ? std::clamp(static_cast<float>(sum_q / count / 8.0), -1.0F, 1.0F) : 0.0F;
    vector[123] = count ? std::clamp(static_cast<float>(sum_r / count / 8.0), -1.0F, 1.0F) : 0.0F;
    vector[124] = std::min(max_q - min_q, 16) / 16.0F;
    vector[125] = std::min(max_r - min_r, 16) / 16.0F;
    vector[126] = 1.0F;
    vector[127] = std::tanh((black_pressure - white_pressure) * 2.0F);
    return vector;
}

template <typename T>
bool read_exact(std::ifstream& input, T* data, std::size_t count = 1) {
    return static_cast<bool>(input.read(
        reinterpret_cast<char*>(data),
        static_cast<std::streamsize>(sizeof(T) * count)));
}

}  // namespace

bool NnueEvaluator::load(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    char magic[8]{};
    if (!read_exact(input, magic, 8) || std::memcmp(magic, "GNNUE01", 7) != 0
        || !read_exact(input, &width_) || width_ == 0 || width_ > 512) {
        width_ = 0;
        return false;
    }
    accumulator_weights_.resize(width_ * 128);
    accumulator_bias_.resize(width_);
    output_weights_.resize(width_);
    if (!read_exact(input, accumulator_weights_.data(), accumulator_weights_.size())
        || !read_exact(input, accumulator_bias_.data(), accumulator_bias_.size())
        || !read_exact(input, output_weights_.data(), output_weights_.size())
        || !read_exact(input, &output_bias_)) {
        width_ = 0;
        return false;
    }
    return true;
}

bool NnueEvaluator::loaded() const { return width_ != 0; }

int NnueEvaluator::evaluate(const Board& board) const {
    if (!loaded()) return 0;
    const auto features = encode(board);
    float output = output_bias_;
    for (std::size_t row = 0; row < width_; ++row) {
        float value = accumulator_bias_[row];
        const auto offset = row * 128;
        for (std::size_t column = 0; column < 128; ++column) {
            value += accumulator_weights_[offset + column] * features[column];
        }
        output += output_weights_[row] * std::clamp(value, 0.0F, 1.0F);
    }
    return static_cast<int>(std::tanh(output) * 10'000.0F);
}

SearchEngine::SearchEngine(std::size_t table_mib) {
    const auto bytes = std::max<std::size_t>(1, table_mib) * 1024 * 1024;
    table_.resize(std::max<std::size_t>(1, bytes / sizeof(Entry)));
}

std::uint64_t SearchEngine::hash(const Board& board, bool include_ply) const {
    std::uint64_t result = board.side_to_move() == Color::white
        ? 0x9e3779b97f4a7c15ULL : 0x243f6a8885a308d3ULL;
    if (include_ply) result ^= mix(board.ply() + 0x517cc1b727220a95ULL);
    for (const auto& stack : board.stacks()) {
        for (std::size_t height = 0; height < stack.pieces.size(); ++height) {
            const auto piece = stack.pieces[height];
            std::uint64_t value = static_cast<std::uint16_t>(stack.cell.q);
            value |= static_cast<std::uint64_t>(static_cast<std::uint16_t>(stack.cell.r)) << 16;
            value |= static_cast<std::uint64_t>(piece.color) << 32;
            value |= static_cast<std::uint64_t>(piece.bug) << 33;
            value |= static_cast<std::uint64_t>(piece.id) << 37;
            value |= static_cast<std::uint64_t>(height) << 45;
            result ^= mix(value + 0x9e3779b97f4a7c15ULL);
        }
    }
    return result;
}

int SearchEngine::static_evaluation(const Board& board) const {
    if (evaluator_ && evaluator_->loaded()) return evaluator_->evaluate(board);
    const int white_pressure = static_cast<int>(pressure(board, Color::white));
    const int black_pressure = static_cast<int>(pressure(board, Color::black));
    int white_top = 0;
    int black_top = 0;
    for (const auto& stack : board.stacks()) {
        if (stack.pieces.back().color == Color::white) ++white_top;
        else ++black_top;
    }
    return black_pressure * 1'000 - white_pressure * 1'100 + (white_top - black_top) * 20;
}

int SearchEngine::move_order_score(Board& board, const Move& move, const Move* tt_move) {
    if (tt_move && move == *tt_move) return mate + 1;
    int score = move.kind == MoveKind::movement ? 100 : 0;
    if (move.piece.bug == Bug::queen) score -= 10;
    auto undo = board.make_move(move);
    if (!undo) return -infinity;
    const auto result = board.result();
    if (result != GameResult::ongoing && result != GameResult::draw) score += mate;
    score += static_cast<int>(pressure(board, other(board.side_to_move()))) * 100;
    board.unmake_move(*undo);
    return score;
}

int SearchEngine::negamax(
    Board& board,
    int depth,
    int alpha,
    int beta,
    std::vector<std::uint64_t>& path,
    std::vector<Move>& pv) {
    ++nodes_;
    if ((nodes_ & 15U) == 0 && std::chrono::steady_clock::now() >= deadline_) {
        stopped_ = true;
        return 0;
    }
    const auto result = board.result();
    if (result != GameResult::ongoing) {
        if (result == GameResult::draw) return 0;
        const bool side_won = (result == GameResult::white_win) == (board.side_to_move() == Color::white);
        return side_won ? mate - static_cast<int>(board.ply()) : -mate + static_cast<int>(board.ply());
    }
    const auto repetition_key = hash(board, false);
    if (std::ranges::count(path, repetition_key) > 1) return 0;
    const auto key = hash(board);
    if (depth <= 0) {
        const auto white_score = static_evaluation(board);
        return board.side_to_move() == Color::white ? white_score : -white_score;
    }

    auto& entry = table_[key % table_.size()];
    const Move* tt_move = entry.key == key && entry.bound != Bound::none ? &entry.best : nullptr;
    if (entry.key == key && entry.depth >= depth) {
        if (entry.bound == Bound::exact) return entry.score;
        if (entry.bound == Bound::lower) alpha = std::max(alpha, entry.score);
        if (entry.bound == Bound::upper) beta = std::min(beta, entry.score);
        if (alpha >= beta) return entry.score;
    }

    auto moves = board.legal_moves();
    std::vector<std::pair<int, Move>> ordered;
    ordered.reserve(moves.size());
    for (const auto& move : moves) {
        ordered.emplace_back(move_order_score(board, move, tt_move), move);
        if (std::chrono::steady_clock::now() >= deadline_) {
            stopped_ = true;
            return 0;
        }
    }
    std::ranges::stable_sort(ordered, std::greater{}, &std::pair<int, Move>::first);
    const int original_alpha = alpha;
    int best_score = -infinity;
    Move best = ordered.front().second;
    std::vector<Move> best_child_pv;
    bool first = true;
    for (const auto& [order_score, move] : ordered) {
        (void)order_score;
        auto undo = board.make_move(move);
        path.push_back(hash(board, false));
        std::vector<Move> child_pv;
        int score;
        if (first) {
            score = -negamax(board, depth - 1, -beta, -alpha, path, child_pv);
            first = false;
        } else {
            score = -negamax(board, depth - 1, -alpha - 1, -alpha, path, child_pv);
            if (!stopped_ && score > alpha && score < beta) {
                child_pv.clear();
                score = -negamax(board, depth - 1, -beta, -alpha, path, child_pv);
            }
        }
        path.pop_back();
        board.unmake_move(*undo);
        if (stopped_) return 0;
        if (score > best_score) {
            best_score = score;
            best = move;
            best_child_pv = std::move(child_pv);
        }
        alpha = std::max(alpha, score);
        if (alpha >= beta) break;
    }
    pv.clear();
    pv.push_back(best);
    pv.insert(pv.end(), best_child_pv.begin(), best_child_pv.end());
    entry = Entry{
        key,
        best,
        best_score,
        static_cast<std::int16_t>(depth),
        best_score <= original_alpha ? Bound::upper
            : (best_score >= beta ? Bound::lower : Bound::exact),
    };
    return best_score;
}

SearchResult SearchEngine::search(
    Board& board,
    const SearchLimits& limits,
    const NnueEvaluator* evaluator) {
    const auto started = std::chrono::steady_clock::now();
    const auto interruption_margin = std::min(limits.time, std::chrono::milliseconds{2});
    deadline_ = started + limits.time - interruption_margin;
    evaluator_ = evaluator;
    nodes_ = 0;
    stopped_ = false;
    const auto legal = board.legal_moves();
    if (legal.empty()) {
        return SearchResult{
            .elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - started),
        };
    }
    SearchResult completed{.move = legal.front()};
    int previous = 0;
    for (unsigned depth = 1; depth <= limits.max_depth; ++depth) {
        std::vector<std::uint64_t> path{hash(board, false)};
        std::vector<Move> pv;
        int alpha = depth > 1 ? previous - 150 : -infinity;
        int beta = depth > 1 ? previous + 150 : infinity;
        int score = negamax(board, static_cast<int>(depth), alpha, beta, path, pv);
        if (!stopped_ && (score <= alpha || score >= beta)) {
            pv.clear();
            path.assign(1, hash(board, false));
            score = negamax(board, static_cast<int>(depth), -infinity, infinity, path, pv);
        }
        if (stopped_) break;
        if (!pv.empty()) {
            completed.move = pv.front();
            completed.score = score;
            completed.depth = depth;
            completed.principal_variation = std::move(pv);
            previous = score;
        }
        if (std::abs(score) >= mate - 512) break;
    }
    completed.nodes = nodes_;
    completed.elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started);
    return completed;
}

}  // namespace genseki
