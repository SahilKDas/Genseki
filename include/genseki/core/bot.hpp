#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace genseki {

enum class EvaluatorKind : std::uint8_t {
    nnue,
    dense,
    convolutional,
};

struct BotSpec {
    std::string_view letter;
    EvaluatorKind evaluator;
    std::uint8_t search_depth;
    bool enabled;
};

[[nodiscard]] constexpr std::array<BotSpec, 18> greek_bot_specs() {
    return {{
        {"Gamma", EvaluatorKind::nnue, 1, true},
        {"Delta", EvaluatorKind::nnue, 2, true},
        {"Epsilon", EvaluatorKind::dense, 1, true},
        {"Zeta", EvaluatorKind::dense, 2, true},
        {"Eta", EvaluatorKind::convolutional, 1, true},
        {"Theta", EvaluatorKind::convolutional, 2, true},
        {"Kappa", EvaluatorKind::nnue, 3, true},
        {"Lambda", EvaluatorKind::dense, 3, true},
        {"Mu", EvaluatorKind::convolutional, 3, true},
        {"Xi", EvaluatorKind::nnue, 4, true},
        {"Omicron", EvaluatorKind::dense, 4, true},
        {"Pi", EvaluatorKind::convolutional, 4, true},
        {"Sigma", EvaluatorKind::nnue, 5, true},
        {"Tau", EvaluatorKind::dense, 5, true},
        {"Upsilon", EvaluatorKind::convolutional, 5, true},
        {"Chi", EvaluatorKind::nnue, 6, true},
        {"Psi", EvaluatorKind::dense, 6, true},
        {"Omega", EvaluatorKind::convolutional, 6, true},
    }};
}

[[nodiscard]] std::string_view name(EvaluatorKind kind);

}  // namespace genseki
