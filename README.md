# Genseki
Genseki: Make a C++26/Python bot and conquer the Hive (board game) bot ecosystem. This is no joke, I have to hit a generational lock-in.

Genseki is a C++26 engine and Python experiment lab for testing Hive bot
evaluators at scale. The core question is simple:

- Are NNUEs better than dense or convolutional neural evaluators?
- Are NNUEs better than handcrafted evaluation functions?

The bot league reserves up to twenty-four Greek-letter identities from Alpha
through Omega. The first active wave compares handcrafted, NNUE, dense neural,
and convolutional evaluators at shallow search depths.

## Current Scaffold

- `include/` and `src/`: C++26 Hive board and bot registry foundation.
- `genseki/`: Python experiment manifest tooling.
- `docs/EXPERIMENTS.md`: evaluator comparison plan.

## Commands

```powershell
python -m genseki.experiments
python -m genseki.experiments --out reports/manifest.json --pairings reports/pairings.csv
python -m genseki.report data/samples/arena_results.csv
```

When a C++26 compiler is available:

```powershell
cmake -S . -B build
cmake --build build
ctest --test-dir build
```
