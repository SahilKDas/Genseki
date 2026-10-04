#include "genseki/core/bot.hpp"

namespace genseki {

std::string_view name(EvaluatorKind kind) {
    switch (kind) {
        case EvaluatorKind::nnue:
            return "nnue";
        case EvaluatorKind::dense:
            return "dense";
        case EvaluatorKind::convolutional:
            return "convolutional";
    }
    return "unknown";
}

}  // namespace genseki
