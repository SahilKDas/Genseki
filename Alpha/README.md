# Alpha Hive engines

This directory contains two deliberately distinct engines:

The root Genseki build now installs the MIT-derived flagship as
`build/genseki.exe`; the GUI defaults to that executable. The retired neural
league and its engine search paths have been removed from the active codebase.
Rho uses the separate root `genseki_rules.exe` position/children service.

- `alpha_nokamute` is the independently written experimental C++26 engine.
- `alpha_nokamute_mit` is the strength backend derived from MIT-licensed
  Nokamute commit `c9ab65e0d9f496fd8735096ae37babc8bb50a57c` and
  minimax-rs commit `be1867b38bd80a7ccdf2188f025525997a87437f`.

The MIT backend retains Nokamute's evaluator, board representation, complete
search stack, move ordering, quiescence policy, parallelism, pondering, time
management, and random-opening policy. It is explicitly not clean-room code.
See `MIT_BACKEND_PROVENANCE.md` and `THIRD_PARTY_NOTICES.md`.

From this directory, build both engines with `cmake -S . -B build` and
`cmake --build build --config Release`. Run `build/alpha_nokamute.exe uhp`
for the experimental C++ engine. The exact MIT backend is emitted at
`build/rust-target/release/alpha_nokamute_mit.exe`; run it with `uhp`, `cli`,
`play`, `perft`, or `uhp-debug`.

Additional isolated modes are `cli`, `perft DEPTH [GAMESTRING] [--divide]`,
`play [MAX_PLIES] [SECONDS] [GAME_TYPE]`, and
`uhp-debug [GAMESTRING] [DEPTH]`. The play mode is Alpha self-play;
uhp-debug checks legal-notation and make/unmake invariants before perft.

Implemented: Base and M/L/P game types, UHP
newgame/play/validmoves/undo/bestmove/info/options/perft, Hive placement and
one-hive movement rules, standard piece movement, game-state detection, and
iterative PVS with aspiration windows, Zobrist keys, repetition detection, a
bounded striped transposition table, deadline-safe root parallelism (1-12
threads), cancellable background pondering, and principal variations. Search and
perft use reversible make/unmake on the independently designed axial board.
The C++ evaluator accounts for queen pressure/coverage, material, buried
pieces, beetle control, reserves, and queen timing, but does not match
Nokamute's strength. The MIT backend scored 10.5/20 against the local Nokamute
binary in the mirrored gate; see `STATUS.md` for the complete conditions.

Run `ctest --test-dir build --output-on-failure` for Alpha's local smoke and
contract tests. `tests/differential.py` accepts the C++ executable and a
separately built executable of the pinned upstream revision; it compares
canonical valid-move strings and game states.
