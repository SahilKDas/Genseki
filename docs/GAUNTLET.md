# Live gauntlets

Run from the Genseki root. Build the spectator once:

```powershell
cmake -S . -B build -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build build --target genseki_spectator -j1
```

The spectator target uses the main GUI's native renderer and assets. It does
not depend on rebuilding Alpha. The runner also needs `build/genseki_rules.exe`
and the two UHP engines being compared.

## Start and watch

```powershell
python -m genseki.gauntlet --engine-a .\build\genseki.exe --engine-b ._\path\to\opponent.exe --name-a Genseki --name-b Nokamute --games 20
```

This opens a visible spectator window automatically. It shows the current
board, reserves, move history, White/Black engine names, game number, and
cumulative A/B points. Colors alternate; each pair uses the same opening seed.
The board can be panned and zoomed. Rules, motion, and sound controls remain
available. Spectating cannot play moves, undo, or change engine settings.

Use `--move-delay-ms 500` to slow presentation between moves. This delay is
outside the measured search time. Closing the window leaves the gauntlet
running; Ctrl+C in the terminal stops the run and closes its engine processes.
The spectator stays on the final position when the run ends.

The default limits are 230 ms internal requests, 250 ms external deadlines,
one thread per engine, 16 MiB tables, 160 plies per game, and a two-hour stage.
These can be set with `--internal-ms`, `--external-ms`, `--threads`,
`--table-mib`, `--cap`, and `--hours`. Threads cannot exceed twelve and stages
cannot exceed two hours. The Windows launcher refuses competing training or
gauntlet jobs and checks the GUI/controller limits, RAM, and temporary storage.
Background search runs at Idle priority. Engines must expose `NumThreads` or
`Threads`; unsupported option configuration fails explicitly.

## Engine arguments and neural models

Arguments are separate tokens, without shell interpretation:

```powershell
python -m genseki.gauntlet --engine-a .\build-nu\nu.exe --a-arg=--model --a-arg ._\models\candidate.nnue --engine-b .\build\genseki.exe --name-a Nu --name-b Gen1
```

For engines with UHP model selection, repeat `--a-option` or `--b-option`:

```powershell
python -m genseki.gauntlet --engine-b .\build\genseki.exe --a-option "ModelPath ._\models\candidate.nnue" --a-option "Evaluator neural" --name-a Gen2 --name-b Gen1
```

Thread counts, pondering, random opening settings, and table limits are applied
after custom options. This is a development viewer, not the sealed Gen 2
qualification or a promotion mechanism.

## Evidence and reconnecting

Each run gets a new directory under `reports/work/gauntlet-*`, or the new path
given by `--output`. Existing output directories are never overwritten.
`report.json` records settings, executable hashes, scores, and completion state;
`game-0001.json`, etc. retain each completed game's moves and search timings.
Natural results, capped draws, and timeouts have separate termination values.
Protocol/rules divergence rejects the run. A stopped or rejected run preserves
completed games and the last displayed position; it does not score an unfinished
game or resume automatically.

`live.txt` is an atomically replaced snapshot. A second spectator can attach,
provided the two-GUI device limit is respected:

```powershell
.\build\genseki_spectator.exe --spectate ._\path\to\run\live.txt
```

Use `--no-gui` for a headless gauntlet. This runner currently plays Base Hive.

## Checks

```powershell
python -B tests/gauntlet_tests.py
.\build\genseki_spectator.exe --check-spectator ._\path\to\run\live.txt
```
