#pragma once

#include "genseki/core/board.hpp"

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
    UhpEngine() = default;
    [[nodiscard]] std::vector<std::string> startup() const;
    [[nodiscard]] std::vector<std::string> execute(std::string_view line);
    void run(std::istream& input, std::ostream& output);
    [[nodiscard]] bool exit_requested() const;

private:
    std::optional<Board> board_{};
    bool exit_requested_ = false;

    [[nodiscard]] std::vector<std::string> error(std::string message) const;
};

}  // namespace genseki
