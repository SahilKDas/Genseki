#pragma once

#include <cstdint>
#include <string_view>

namespace genseki {

enum class Color : std::uint8_t {
    white,
    black,
};

enum class Bug : std::uint8_t {
    queen,
    spider,
    beetle,
    grasshopper,
    ant,
};

struct Piece {
    Color color = Color::white;
    Bug bug = Bug::queen;
    std::uint8_t id = 0;

    auto operator<=>(const Piece&) const = default;
};

[[nodiscard]] constexpr Color other(Color color) {
    return color == Color::white ? Color::black : Color::white;
}

[[nodiscard]] constexpr std::string_view name(Bug bug) {
    switch (bug) {
        case Bug::queen:
            return "queen";
        case Bug::spider:
            return "spider";
        case Bug::beetle:
            return "beetle";
        case Bug::grasshopper:
            return "grasshopper";
        case Bug::ant:
            return "ant";
    }
    return "unknown";
}

}  // namespace genseki
