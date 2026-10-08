#pragma once

#include "genseki/core/board.hpp"
#include <chrono>
#include <expected>
#include <filesystem>
#include <functional>
#include <optional>
#include <stop_token>
#include <string>
#include <vector>

namespace genseki::review {

struct Fact {
    std::string kind;
    std::string english;
    std::vector<Hex> cells;
    std::string witness;
};

struct SearchAnswer {
    std::string move;
    int score = 0; // Side to move, not a probability or a calibrated rating.
    std::optional<unsigned> completed_depth;
    std::optional<std::uint64_t> nodes;
    std::optional<double> elapsed_ms;
};

struct Entry {
    unsigned ply = 0;
    Move move;
    std::string notation;
    std::string before_game, after_game;
    std::vector<Fact> facts;
    std::string explanation;
    std::string status = "unanalysed";
    bool tactical_complete = false;
    std::optional<std::string> immediate_win, winning_reply;
    std::optional<SearchAnswer> preferred;
    std::optional<int> played_score, preferred_score;
    std::vector<std::string> variation;
    std::vector<Fact> alternative_facts;
};

struct Settings {
    std::filesystem::path engine;
    unsigned search_ms = 2000;
    unsigned tactical_ms = 200;
    unsigned game_ms = 600000;
};

struct Report {
    std::string replay;
    std::string game_sha256, engine_sha256;
    std::string status = "ready";
    std::string message;
    bool partial_game = false;
    unsigned completed = 0;
    Settings settings;
    std::vector<Entry> moves;
};

using Guard = std::function<bool()>;
using Search = std::function<std::expected<SearchAnswer, std::string>(
    const Board&, unsigned, std::stop_token)>;
using Publish = std::function<void(const Report&)>;

[[nodiscard]] std::expected<Report, std::string> prepare(std::string_view replay, std::stop_token stop = {});
[[nodiscard]] Entry describe(const Board& before, const Move& move);
void inspect_tactics(Entry& entry, const Board& before,
    std::chrono::steady_clock::time_point deadline, std::stop_token stop = {});
[[nodiscard]] std::string explain(const Entry& entry);
// Acceptance audit: rebuild rule facts and match every rendered claim to them.
[[nodiscard]] std::expected<void,std::string> validate_evidence(const Entry& entry,
    const Board& before, std::chrono::steady_clock::time_point deadline);
struct ProcessUsage { unsigned id=0; std::wstring executable; std::uint64_t cpu_ticks=0; bool project_process=true; };
[[nodiscard]] bool process_slots_available(const std::vector<ProcessUsage>& processes,
    unsigned self, unsigned owned_engine=0);
[[nodiscard]] std::string json(const Report& report);
[[nodiscard]] std::string sha256(std::string_view value);
[[nodiscard]] std::string file_sha256(const std::filesystem::path& path);
[[nodiscard]] bool resources_available(unsigned owned_engine=0);
[[nodiscard]] bool claim_job();
void release_job();

// Each caller owns a separate report and Alpha process. No live board is touched.
[[nodiscard]] Report analyse(Report report, const Settings& settings,
    std::stop_token stop = {}, Publish publish = {}, Search search = {}, Guard guard = {});
[[nodiscard]] std::expected<void, std::string> save(const Report& report,
    const std::filesystem::path& path);

} // namespace genseki::review
