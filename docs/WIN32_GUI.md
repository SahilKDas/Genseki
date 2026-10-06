# Win32 GUI

`genseki_gui` is a native Windows front end with tiny-skia 0.12.0 vector
rasterization, Win32 window management and GDI text. It treats the
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

## Rendering And Motion

The dark maple palette, embedded insect SVGs and antialiased hexes use a
pinned Rust tiny-skia DLL (`genseki_raster.dll`). Ship that sibling DLL with
the executable. CMake also copies dependency and audio notices to
`build/gui-licenses`; preserve them in distributions.

Frames are composed in a reusable double buffer; background erasure is
suppressed. Vector sprites are cached with a 256-entry limit. Engine searches
run off the UI thread, while engine state updates remain on the UI thread.
Pipe responses have a five-second limit. Timer ticks request animation frames
at roughly 16 ms intervals, but this is not a measured 60 FPS guarantee.
Idle painting drops to clock updates after easing settles.

Nunito is embedded and registered privately with Windows, without a system
installation. Its SIL Open Font License accompanies distributions. Hovered
buttons brighten and expand by at most two pixels per edge, using eased
transitions and stable hit areas; neighboring controls do not move.

Hover easing, 320 ms tile movement, landing rings and bounded particle bursts
are presentation only: UHP state remains authoritative. Beetles cover pieces,
not capture them; no Hive piece disappears from the rules state. Motion can
be disabled. Sound can be muted independently.

Sound effects come from Aqibahmed12/Chess-Master at revision
`a15d4248fb4bd3487b8af0839a0d26a4fa8e5958`. Every piece move and deployment uses
capture.wav; terminal results use game_over.wav instead, without overlapping
the move cue for that same move. Earlier sounds may continue underneath it.
Passes are silent. One dedicated audio worker submits up to eight independent
WinMM voices, so subsequent cues do not terminate earlier cues. Queue size is
bounded at sixteen; excess bursts are dropped rather than cutting an existing
voice. Muting cancels queued and active voices; closing joins the worker.
Playback is asynchronous and non-looping, triggered only by newly received completed
moves, never by repainting. Move and check cues are not embedded in the GUI.
The upstream license is retained in `src/gui/assets/sounds/NOTICE.md`.

Automated checks validate all five SVG rasters, the embedded WAV headers,
and tiny-skia premultiplied color conversion. Live-window visual motion and
audible playback acceptance remain separate manual checks.
