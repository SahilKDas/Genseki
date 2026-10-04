#pragma once

#include "genseki/core/board.hpp"
#include "genseki/core/search.hpp"

#include <chrono>
#include <filesystem>
#include <istream>
#include <optional>
#include <ostream>
#include <string>
#include <string_view>
#include <vector>

namespace genseki {

class UhpEngine {
public:
    explicit UhpEngine(
        std::filesystem::path model = {},
        unsigned threads = 1,
        std::size_t table_mib = 64,
        std::chrono::milliseconds move_time = std::chrono::milliseconds{230});
    [[nodiscard]] std::vector<std::string> startup() const;
    [[nodiscard]] std::vector<std::string> execute(std::string_view line);
    void run(std::istream& input, std::ostream& output);
    [[nodiscard]] bool exit_requested() const;

private:
    std::optional<Board> board_{};
    SearchEngine search_;
    NnueEvaluator evaluator_{};
    std::optional<SearchResult> last_search_{};
    unsigned threads_ = 1;
    std::size_t table_mib_ = 64;
    std::chrono::milliseconds move_time_{230};
    bool exit_requested_ = false;

    [[nodiscard]] std::vector<std::string> error(std::string message) const;
};

}  // namespace genseki
