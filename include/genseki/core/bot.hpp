#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace genseki {

enum class EvaluatorKind : std::uint8_t {
    handcrafted,
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

[[nodiscard]] constexpr std::array<BotSpec, 24> greek_bot_specs() {
    return {{
        {"Alpha", EvaluatorKind::handcrafted, 1, true},
        {"Beta", EvaluatorKind::handcrafted, 2, true},
        {"Gamma", EvaluatorKind::nnue, 1, true},
        {"Delta", EvaluatorKind::nnue, 2, true},
        {"Epsilon", EvaluatorKind::dense, 1, true},
        {"Zeta", EvaluatorKind::dense, 2, true},
        {"Eta", EvaluatorKind::convolutional, 1, true},
        {"Theta", EvaluatorKind::convolutional, 2, true},
        {"Iota", EvaluatorKind::handcrafted, 3, false},
        {"Kappa", EvaluatorKind::nnue, 3, false},
        {"Lambda", EvaluatorKind::dense, 3, false},
        {"Mu", EvaluatorKind::convolutional, 3, false},
        {"Nu", EvaluatorKind::handcrafted, 4, false},
        {"Xi", EvaluatorKind::nnue, 4, false},
        {"Omicron", EvaluatorKind::dense, 4, false},
        {"Pi", EvaluatorKind::convolutional, 4, false},
        {"Rho", EvaluatorKind::handcrafted, 5, false},
        {"Sigma", EvaluatorKind::nnue, 5, false},
        {"Tau", EvaluatorKind::dense, 5, false},
        {"Upsilon", EvaluatorKind::convolutional, 5, false},
        {"Phi", EvaluatorKind::handcrafted, 6, false},
        {"Chi", EvaluatorKind::nnue, 6, false},
        {"Psi", EvaluatorKind::dense, 6, false},
        {"Omega", EvaluatorKind::convolutional, 6, false},
    }};
}

[[nodiscard]] std::string_view name(EvaluatorKind kind);

}  // namespace genseki
