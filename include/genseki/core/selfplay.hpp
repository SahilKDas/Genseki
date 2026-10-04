#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

namespace genseki {

struct DatasetStats {
    unsigned games = 0;
    unsigned terminal_games = 0;
    unsigned adjudicated_games = 0;
    std::uint64_t positions = 0;
};

[[nodiscard]] DatasetStats generate_training_data(
    const std::filesystem::path& output,
    unsigned games,
    unsigned max_plies,
    std::uint32_t seed);

[[nodiscard]] std::string to_json(const DatasetStats& stats);

}  // namespace genseki
