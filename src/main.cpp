#include "genseki/core/board.hpp"
#include "genseki/core/bot.hpp"

#include <iostream>

int main() {
    const genseki::Board board;
    std::cout << "Genseki Hive bot lab\n";
    std::cout << board.summary() << '\n';
    std::cout << "Greek bot slot._\n";
    for (const auto spec : genseki::greek_bot_specs()) {
        if (spec.enabled) {
            std::cout << "  " << spec.letter << " evaluator=" << genseki::name(spec.evaluator)
                      << " depth=" << static_cast<int>(spec.search_depth) << '\n';
        }
    }
    return 0;
}
