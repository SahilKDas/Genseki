#pragma once

#include <compare>
#include <cstdint>

namespace genseki {

struct Hex {
    std::int16_t q = 0;
    std::int16_t r = 0;

    auto operator<=>(const Hex&) const = default;
};

inline constexpr Hex directions[6] = {
    Hex{1, 0},
    Hex{1, -1},
    Hex{0, -1},
    Hex{-1, 0},
    Hex{-1, 1},
    Hex{0, 1},
};

[[nodiscard]] constexpr Hex add(Hex a, Hex b) {
    return Hex{static_cast<std::int16_t>(a.q + b.q), static_cast<std::int16_t>(a.r + b.r)};
}

[[nodiscard]] constexpr bool adjacent(Hex a, Hex b) {
    for (const auto direction : directions) {
        if (add(a, direction) == b) {
            return true;
        }
    }
    return false;
}

}  // namespace genseki
