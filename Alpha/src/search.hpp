#pragma once

struct SearchResult {
    Move move{};
    int score = 0;
    int depth = 0;
    std::uint64_t nodes = 0;
    double seconds = 0;
    std::vector<Move> pv;
};

class Search {
    enum class Bound : std::uint8_t { none, exact, lower, upper };
    struct Entry {
        std::uint64_t key = 0;
        Move move{};
        int score = 0;
        std::int16_t depth = -1;
        Bound bound = Bound::none;
    };

    static constexpr int infinity = 1'000'000;
    static constexpr int mate = 900'000;
    std::vector<Entry> table_;
    std::chrono::steady_clock::time_point deadline_;
    std::atomic<std::uint64_t> nodes_{0};
    std::atomic<bool> stopped_{false};
    static constexpr std::size_t lock_count = 256;
    std::array<std::mutex,lock_count> table_mutexes_;
    int aggression_ = 50;
    bool verbose_ = false;
    std::stop_token stop_token_{};

    static std::uint64_t mix(std::uint64_t x) {
        x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
        x ^= x >> 27; x *= 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }

    std::uint64_t hash(const Board& b, bool include_clock = true) const {
        std::uint64_t key = b.side() ? 0x243f6a8885a308d3ULL : 0x9e3779b97f4a7c15ULL;
        if (include_clock) key ^= mix(b.history.size() + 0x517cc1b727220a95ULL);
        for (const auto& [hex, stack] : b.cells) {
            for (std::size_t level = 0; level < stack.size(); ++level) {
                const auto p = stack[level];
                std::uint64_t value = static_cast<std::uint32_t>(hex.q);
                value ^= static_cast<std::uint64_t>(static_cast<std::uint32_t>(hex.r)) << 16;
                value ^= static_cast<std::uint64_t>(p.color) << 33;
                value ^= static_cast<std::uint64_t>(kind_index(p.kind) + 1) << 35;
                value ^= static_cast<std::uint64_t>(p.number) << 40;
                value ^= static_cast<std::uint64_t>(level) << 44;
                key ^= mix(value + 0x9e3779b97f4a7c15ULL);
            }
        }
        for (char expansion : b.expansions) key ^= mix(static_cast<unsigned char>(expansion) + 0x100);
        if (!b.history.empty()) {
            const auto& move = b.history.back();
            std::uint64_t last = static_cast<std::uint32_t>(move.from.q);
            last ^= static_cast<std::uint64_t>(static_cast<std::uint32_t>(move.from.r)) << 16;
            last ^= static_cast<std::uint64_t>(static_cast<std::uint32_t>(move.to.q)) << 32;
            last ^= static_cast<std::uint64_t>(static_cast<std::uint16_t>(move.to.r)) << 48;
            last ^= static_cast<std::uint64_t>(kind_index(move.piece.kind) + 1) << 56;
            last ^= static_cast<std::uint64_t>(move.piece.color) << 60;
            last ^= static_cast<std::uint64_t>(move.pass) << 61;
            last ^= static_cast<std::uint64_t>(move.placement) << 62;
            key ^= mix(last);
        }
        return key;
    }

    int evaluate(const Board& b, int color) const {
        bool mine = b.queen_surrounded(color), theirs = b.queen_surrounded(1-color);
        if (mine && theirs) return 0;
        if (mine) return -mate + static_cast<int>(b.history.size());
        if (theirs) return mate - static_cast<int>(b.history.size());
        int score = 0;
        const int attack = 80 + aggression_;
        const int defense = 180 - aggression_;
        constexpr std::array<int,8> values{{0,10,16,24,28,22,20,24}};
        for (int c = 0; c < 2; ++c) {
            int sign = c == color ? 1 : -1;
            auto queen = b.locate({c,'Q',0});
            if (queen) {
                const int danger = b.neighbors(*queen);
                score -= sign * (c == color ? defense : attack) * danger * danger;
                const auto& queen_stack=b.cells.at(*queen);
                if(queen_stack.size()>1)score-=sign*110;
            } else {
                score-=sign*std::max(0,b.turn_for(c)-2)*25;
            }
            for (const auto& [hex, stack] : b.cells) {
                for (std::size_t level=0;level<stack.size();++level) {
                    auto p=stack[level];
                    if(p.color!=c)continue;
                    score+=sign*values[kind_index(p.kind)];
                    if(level+1<stack.size())score-=sign*18;
                }
                if (stack.size() > 1 && stack.back().color == c) {
                    score += sign * (45+12*static_cast<int>(stack.size()-1));
                    auto enemy_queen=b.locate({1-c,'Q',0});
                    if(enemy_queen&&*enemy_queen==hex)score+=sign*130;
                }
            }
            int reserves=0;
            for(char kind:kinds) {
                int ix=kind_index(kind);
                if(ix>=5&&!b.expansions.count(kind))continue;
                reserves+=limits[ix]-b.count_on_board(c,kind);
            }
            score-=sign*reserves*2;
        }
        return score;
    }

    int order_score(Board& b, const Move& move, const Move* tt_move) {
        if (tt_move && move == *tt_move) return mate + 1;
        if (move.pass) return -100;
        int score = move.placement ? 0 : 100;
        if (b.occupied(move.to)) score += 300;
        b.apply(move);
        const auto state = b.state();
        if ((state == "WhiteWins" && move.piece.color == 0)
            || (state == "BlackWins" && move.piece.color == 1)) score += mate;
        auto queen = b.locate({1 - move.piece.color, 'Q', 0});
        if (queen) score += b.neighbors(*queen) * 50;
        b.undo();
        return score;
    }

    int pvs(Board& b, int depth, int alpha, int beta,
            std::vector<std::uint64_t>& path, std::vector<Move>& pv) {
        nodes_.fetch_add(1, std::memory_order_relaxed);
        if (stop_token_.stop_requested() || std::chrono::steady_clock::now() >= deadline_) {
            stopped_ = true;
            return 0;
        }
        const auto state = b.state();
        if (state == "WhiteWins" || state == "BlackWins" || state == "Draw")
            return evaluate(b, b.side());
        const auto repetition = hash(b, false);
        if (std::count(path.begin(), path.end(), repetition) > 1) return 0;
        if (depth <= 0) return evaluate(b, b.side());

        const auto key = hash(b);
        Entry cached;
        {
            const auto index=key % table_.size();
            std::scoped_lock lock(table_mutexes_[index % lock_count]);
            cached = table_[index];
        }
        std::optional<Move> tt_move;
        if (cached.key == key && cached.bound != Bound::none) tt_move = cached.move;
        if (cached.key == key && cached.depth >= depth) {
            if (cached.bound == Bound::exact) return cached.score;
            if (cached.bound == Bound::lower) alpha = std::max(alpha, cached.score);
            if (cached.bound == Bound::upper) beta = std::min(beta, cached.score);
            if (alpha >= beta) return cached.score;
        }

        auto moves = b.legal_moves();
        std::vector<std::pair<int, Move>> ordered;
        ordered.reserve(moves.size());
        for (const auto& move : moves) {
            ordered.emplace_back(order_score(b, move, tt_move ? &*tt_move : nullptr), move);
            if (std::chrono::steady_clock::now() >= deadline_) {
                stopped_ = true;
                return 0;
            }
        }
        std::stable_sort(ordered.begin(), ordered.end(),
            [](const auto& a, const auto& z) { return a.first > z.first; });

        const int original_alpha = alpha;
        int best_score = -infinity;
        Move best = ordered.front().second;
        std::vector<Move> best_child;
        bool first = true;
        for (const auto& [order, move] : ordered) {
            (void)order;
            b.apply(move);
            path.push_back(hash(b, false));
            std::vector<Move> child;
            int score;
            if (first) {
                score = -pvs(b, depth - 1, -beta, -alpha, path, child);
                first = false;
            } else {
                score = -pvs(b, depth - 1, -alpha - 1, -alpha, path, child);
                if (!stopped_ && score > alpha && score < beta) {
                    child.clear();
                    score = -pvs(b, depth - 1, -beta, -alpha, path, child);
                }
            }
            path.pop_back();
            b.undo();
            if (stopped_) return 0;
            if (score > best_score) {
                best_score = score;
                best = move;
                best_child = std::move(child);
            }
            alpha = std::max(alpha, score);
            if (alpha >= beta) break;
        }
        pv = {best};
        pv.insert(pv.end(), best_child.begin(), best_child.end());
        {
            const auto index=key % table_.size();
            std::scoped_lock lock(table_mutexes_[index % lock_count]);
            auto& destination = table_[index];
            if (destination.key != key || destination.depth <= depth)
                destination = {key, best, best_score, static_cast<std::int16_t>(depth),
                    best_score <= original_alpha ? Bound::upper
                        : best_score >= beta ? Bound::lower : Bound::exact};
        }
        return best_score;
    }

public:
    explicit Search(std::size_t table_mib = 64, int aggression = 50, bool verbose = false)
        : aggression_(aggression), verbose_(verbose) {
        const auto bytes = std::max<std::size_t>(1, table_mib) * 1024 * 1024;
        table_.resize(std::max<std::size_t>(1, bytes / sizeof(Entry)));
    }

    SearchResult best(Board board, int max_depth, double seconds, int threads = 1,
                      std::stop_token stop_token = {}) {
        const auto started = std::chrono::steady_clock::now();
        // Leave room for Windows scheduler granularity, worker joins, and UHP I/O.
        const double reserve=std::min(0.015,std::max(0.0,seconds)*0.10);
        deadline_ = started + std::chrono::milliseconds(
            static_cast<int>(std::max(0.001, seconds-reserve) * 1000));
        nodes_.store(0);
        stopped_.store(false);
        stop_token_=stop_token;
        threads = std::clamp(threads, 1, 12);
        auto legal = board.legal_moves();
        if (legal.empty()) throw std::runtime_error("the game is already over");
        SearchResult result{};
        result.move = legal.front();
        int previous = 0;
        for (int depth = 1; depth <= max_depth; ++depth) {
            std::vector<Move> pv;
            int score = -infinity;
            if (threads == 1 || legal.size() == 1) {
                std::vector<std::uint64_t> path{hash(board, false)};
                int alpha = depth > 1 ? previous - 150 : -infinity;
                int beta = depth > 1 ? previous + 150 : infinity;
                score = pvs(board, depth, alpha, beta, path, pv);
                if (!stopped_ && (score <= alpha || score >= beta)) {
                    path.assign(1, hash(board, false));
                    pv.clear();
                    score = pvs(board, depth, -infinity, infinity, path, pv);
                }
            } else {
                std::atomic<std::size_t> next{0};
                std::vector<int> scores(legal.size(), -infinity);
                std::vector<std::vector<Move>> lines(legal.size());
                const int workers = std::min<int>(threads, static_cast<int>(legal.size()));
                std::vector<std::jthread> pool;
                for (int worker = 0; worker < workers; ++worker) {
                    pool.emplace_back([&] {
                        while (!stopped_) {
                            const auto index = next.fetch_add(1);
                            if (index >= legal.size()) break;
                            Board child = board;
                            child.apply(legal[index]);
                            std::vector<std::uint64_t> path{
                                hash(board, false), hash(child, false)};
                            std::vector<Move> child_pv;
                            scores[index] = -pvs(child, depth - 1, -infinity, infinity,
                                                 path, child_pv);
                            lines[index] = {legal[index]};
                            lines[index].insert(lines[index].end(), child_pv.begin(), child_pv.end());
                        }
                    });
                }
                pool.clear();
                if (!stopped_) {
                    const auto best = static_cast<std::size_t>(std::distance(
                        scores.begin(), std::max_element(scores.begin(), scores.end())));
                    score = scores[best];
                    pv = std::move(lines[best]);
                }
            }
            if (stopped_) break;
            if (!pv.empty()) {
                result.move = pv.front();
                result.score = score;
                result.depth = depth;
                result.pv = std::move(pv);
                previous = score;
            }
            if (verbose_) std::cerr << "info depth " << depth << " score " << score
                                    << " nodes " << nodes_ << '\n';
            if (std::abs(score) >= mate - 512) break;
        }
        result.nodes = nodes_.load();
        result.seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
        return result;
    }
};
