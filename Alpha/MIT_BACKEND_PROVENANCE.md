# MIT strength backend provenance

`alpha_nokamute_mit` is an attributed derivative build, not clean-room code.
It vendors Nokamute 1.0.3 commit `c9ab65e0d9f496fd8735096ae37babc8bb50a57c`
and minimax-rs commit `be1867b38bd80a7ccdf2188f025525997a87437f`.

Behavioral code retained from those snapshots includes the evaluator and its
constants, board representation, move generation and ordering contracts,
quiescence/noisy-move policy, iterative and parallel search, aspiration and
transposition behavior, counter-moves and history, optional pruning modes,
time management, pondering, and random-opening policy.

Local modifications are deliberately limited to:

- package and executable name `alpha_nokamute_mit`;
- the displayed version string `1.0.3+mit.c9ab65e`;
- replacing the remote minimax Git dependency with the pinned vendored path;
- removing an unused benchmark manifest entry from the runtime-only snapshot;
- assigning a distinct library target name to avoid Windows PDB collisions;
- Alpha build/test integration.
- Alpha profiling modes, optional performance build profile and parallel cutoff;
- cached queen-neighbor arrays with unchanged evaluation terms;
- direct native monotonic deadline checks alongside timer cancellation flags;
- a test-only allocation experiment (production history ordering is unchanged).
- fractional seconds and checked arithmetic in UHP hh:mm:ss time limits for
  the production GUI's 230 ms searches.

See `PERFORMANCE.md` for measured/rejected experiments. The derivative now has
local performance and timing changes; it should not be called byte-identical or
behaviorally identical under timed search to the pinned upstream executable.

The independent experimental C++ engine remains `alpha_nokamute`. See
`THIRD_PARTY_NOTICES.md` for required notices.
