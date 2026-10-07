# Genseki

Genseki is now the Alpha Hive engine, with a native GUI, UHP interfaces, and
Rho's independent policy/value research. The retired Greek bot league is no
longer part of the active codebase.

## Build and run

A C++26-capable compiler, CMake, Cargo/Rust, and Python for tests are required.

```powershell
cmake -S . -B build -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
.\build\genseki.exe
.\build\genseki_gui.exe
```

`build/genseki.exe` is the Alpha MIT-derived backend itself. With no arguments,
its stdin/stdout interface is UHP. It supports `info`, `newgame`, `play`,
`pass`, `validmoves`, `bestmove`, `undo`, `options`, and `exit`. It also
has `cli`, `play`, `perft`, `uhp-debug`, and profiling modes.

The GUI launches its sibling `genseki.exe` by default. Engine controls use
Alpha with a 230 ms search request. There is no Greek bot selector or Kappa
profile. A custom UHP executable may still be supplied as a GUI argument.

**Review Game** opens a separate English review of a completed game or an
imported Base-Hive replay. Review navigation does not play sounds or advance
the original game's clocks. See [Game Review](docs/GAME_REVIEW.md) for budgets,
evidence limits, export details, and the command-line reviewer.

To run a terminal-controlled gauntlet with a live native spectator:

```powershell
cmake --build build --target genseki_spectator -j1
python -m genseki.gauntlet --engine-b .\path\to\opponent.exe --games 20
```

See [docs/GAUNTLET.md](docs/GAUNTLET.md) for engine arguments, neural options,
limits, saved game records, and reconnecting the viewer.

Alpha derives from attributed MIT-licensed Nokamute and minimax-rs snapshots.
Required licenses are retained under Alpha. See
[Alpha/README.md](Alpha/README.md), [Alpha/STATUS.md](Alpha/STATUS.md), and
[Alpha/THIRD_PARTY_NOTICES.md](Alpha/THIRD_PARTY_NOTICES.md). Timed strength
parity and expansion conformance are not assumed; STATUS records the evidence.

## Rho and rules support

Rho's models, replay data and campaign remain separate. Its default native
service is now `build/genseki_rules.exe`: a rules-only Base-Hive UHP process
with `genseki-position` and `genseki-children` for Rho's encoder and PUCT.
It has no learned evaluator, old bot roster, pressure chooser or search engine.
Use Alpha for `bestmove`. Existing campaign configs naming the former default
rules executable are migrated on resume; Rho checkpoints are not retrained.

```powershell
python -m genseki.rho.status --workspace Rho
python -m genseki.rho.campaign --workspace Rho --resume --dry-run
.\build\genseki_rules.exe --perft 3
```

See [Rho/README.md](Rho/README.md), [docs/WIN32_GUI.md](docs/WIN32_GUI.md),
[docs/HIVE_ENGINE.md](docs/HIVE_ENGINE.md), and the unchanged
[device constraints](constraints_on_SahilKDas_device.md).

## Historical artifacts

The local `history` branch is an independent artifact-only root snapshot. It
contains the retired league's checkpoints, datasets, tournament records and
reports, plus their historical experiment/gate documents. It contains no
source code. These artifacts are not active dependencies or selectable bots.
