# Win32 GUI

`genseki_gui` is a native Windows/GDI front end for Genseki. It treats the
engine as an external Universal Hive Protocol process and does not link to or
modify the rules engine.

Build:

```powershell
cmake -S . -B build
cmake --build build --target genseki_gui -j2
```

Run from the build directory, or pass an engine path:

```powershell
.\build\genseki_gui.exe
```

The GUI talks to the engine with `info`, `newgame`, `validmoves`, `play`,
`pass`, `bestmove`, `undo`, `options`, and `exit`. Board state is mirrored from
UHP game strings returned by the engine. Expansion insects are intentionally
not present.

Controls:

- Left click a reserve piece, then a highlighted destination to place it.
- Left click a top board piece, then a highlighted destination to move it.
- Drag the board with the left mouse button when no piece is selected.
- Mouse wheel zooms around the cursor.
- Toolbar buttons start a new game, undo, load a UHP game string, and request
  engine moves for the selected side mode.

The side panel shows reserves, side to move, result, clocks, engine status,
legal move count, move history, and Alpha's engine label. The retired Greek
roster (including Kappa) is no longer selectable. Both engine-move controls
request 230 ms searches from Alpha, with the last completed depth retained.

Building the GUI also builds its sibling `genseki.exe`, which is the Alpha
MIT-derived backend. A custom UHP engine path can still be passed explicitly.
