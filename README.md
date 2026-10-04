# Genseki
Genseki: Make a C++26/Python bot and conquer the Hive (board game) bot ecosystem. This is no joke, I have to hit a generational lock-in.

Genseki is a C++26 engine and Python experiment lab for testing Hive bot
evaluators at scale. The core question is simple:

- Are NNUEs better than dense or convolutional neural evaluators?
- Are NNUEs better than handcrafted evaluation functions?

The bot league reserves up to twenty-four Greek-letter identities from Alpha
through Omega. The first active wave compares handcrafted, NNUE, dense neural,
and convolutional evaluators at shallow search depths.

## Engine

- Complete regular Hive rules for Queen, Spider, Beetle, Grasshopper, and Ant.
- One Hive, Freedom to Move, stack-aware Beetles, forced Queen placement,
  forced passes, wins, and simultaneous-surround draws.
- Reversible make/unmake, deterministic move generation, replay validation,
  and reference-checked perft.
- Universal Hive Protocol engine for use with UHP viewers and match tools.
- `genseki/`: Python experiment manifest tooling.
- `docs/EXPERIMENTS.md`: evaluator comparison plan.

## Commands

```powershell
python -m genseki.experiments
python -m genseki.experiments --out reports/manifest.json --pairings reports/pairings.csv
python -m genseki.report data/samples/arena_results.csv
```

Build and test:

```powershell
cmake -S . -B build -G "MinGW Makefiles"
cmake --build build -j 3
ctest --test-dir build --output-on-failure
```

Run `build/genseki.exe` with no arguments to start its stdin/stdout UHP
engine. It identifies itself immediately and supports every base-game UHP
command: `info`, `newgame`, `play`, `pass`, `validmoves`,
`bestmove`, `undo`, `options`, and `exit`.

```powershell
.\build\genseki.exe --perft 5
.\build\genseki.exe --perft 3 --divide
.\build\genseki.exe --stress 2000
.\build\genseki.exe --replay "Base;InProgress;White[2];wS1;bS1 wS1-"
```

See [docs/HIVE_ENGINE.md](docs/HIVE_ENGINE.md) for the rules, notation,
invariants, UHP behavior, and verified perft counts.
