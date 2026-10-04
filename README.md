# Genseki
Genseki: Make a C++26/Python bot and conquer the Hive (board game) bot ecosystem. This is no joke, I have to hit a generational lock-in.

Genseki is a C++26 engine and Python experiment lab for testing Hive bot
evaluators at scale. The core question is simple:

- Are NNUEs better than dense or convolutional neural evaluators?
- Are NNUEs better than handcrafted evaluation functions?

The bot league contains twenty-four trained Greek-letter identities from Alpha
through Omega. Six bots apiece compare handcrafted, NNUE, dense neural, and
convolutional evaluators across search-depth profiles one through six.

## Engine

- Complete regular Hive rules for Queen, Spider, Beetle, Grasshopper, and Ant.
- One Hive, Freedom to Move, stack-aware Beetles, forced Queen placement,
  forced passes, wins, and simultaneous-surround draws.
- Reversible make/unmake, deterministic move generation, replay validation,
  and reference-checked perft.
- Universal Hive Protocol engine for use with UHP viewers and match tools.
- CUDA training and UHP gauntlet tooling in `genseki/`.
- Native Win32/GDI UHP GUI in `src/gui/win32_gui.cpp`.
- Frozen model artifacts and a reproducibility manifest in `models/frozen/`.
- Completed 1,200-game qualification evidence in `reports/`.

## Commands

```powershell
.\build\genseki.exe --generate-data data\generated\selfplay.tsv 128 96 1195724371
python -m genseki.training data\generated\selfplay.tsv --output models\frozen --epochs 12 --batch-size 512 --device cuda
python -m genseki.gauntlet --engine build\genseki.exe --mzinga path\to\mzingacpp.exe --games 50 --move-ms 250
```

Build and test:

```powershell
cmake -S . -B build -G "MinGW Makefiles"
cmake --build build -j12
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
See [docs/WIN32_GUI.md](docs/WIN32_GUI.md) for the native GUI and
[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for the evaluator results.
