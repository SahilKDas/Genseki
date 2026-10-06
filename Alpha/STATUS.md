# Port status

## Production default (2026-10-05)

The root build emits this MIT-derived backend itself as `build/genseki.exe`.
The native GUI defaults to that executable and no longer contains the retired
Greek roster. Engine moves use a 230 ms time request. The UHP time parser now
accepts fractional hh:mm:ss seconds and rejects overflowing/out-of-range values.
Rho retains its models/replay and uses a separate, bot-free
`build/genseki_rules.exe` position/child-enumeration service.

Verified: the root Release build completed; all six CTest suites passed,
including an executable-hash/default-UHP test; all 23 Alpha Rust tests and
17 Rho tests passed. Rules-service perft(3) returned 1440 and a 1000-ply
make/unmake stress check passed. GUI compilation is verified; interactive GUI
acceptance has not been run in this consolidation pass.

The retired league's 107 artifact files were copied into local branch `history`,
root commit `0e7d2acc63ae6eaf92c14ba4dd3ba7d7a513693e`, with no source-code files
or parent commits. Every archived blob was compared with its working file
before removal. Current-branch consolidation changes remain uncommitted.

Alpha now has two separately labeled implementations. `alpha_nokamute` is the
independent C++26 experiment. `alpha_nokamute_mit` is an attributed derivative
of Nokamute `c9ab65e0d9f496fd8735096ae37babc8bb50a57c` and minimax-rs
`be1867b38bd80a7ccdf2188f025525997a87437f`, both under MIT licenses.

## Verified implementation

- Independent axial board with reversible make/unmake and Base/M/L/P rules.
- Search/perft modules behind the board's legal-move contract.
- Iterative-deepening PVS, aspiration windows, repetition detection, legal PV,
  deterministic 64-bit keys, and a fixed-memory striped transposition table.
- Bounded 1-12 thread root splitting and cancellable background pondering.
- Queen pressure/coverage, material, buried-piece, beetle-control, reserve,
  queen-timing, and aggression-dependent evaluation terms.
- Effective `Aggression`, `BackgroundPondering`, `NumThreads`,
  `RandomOpening`, `TableSizeMiB`, and `Verbose` options.
- UHP newgame/play/pass/validmoves/undo/bestmove/info/options plus Alpha's
  perft and search-info diagnostics. Fractional time controls are accepted.
- Standalone `cli`, `play`, `perft`, and `uhp-debug` modes.

The MIT backend additionally retains the upstream board representation,
BasicEvaluator constants and mobility/cut-vertex features, noisy-move
quiescence policy, counter-moves and history, iterative/parallel minimax,
aspiration and transposition behavior, optional null-move/quiet-search modes,
time management, pondering, and constrained random-opening policy. Its local
changes also include profiling tools, cached queen-neighbor arrays, optional
performance build/cutoff settings and direct native deadline checks. Evaluation
weights and default pruning/order policies remain unchanged. See PERFORMANCE.md.

## Verification evidence

On 2026-10-04, GCC 14.1 and Rust 1.98.1 built both Release targets. All four
CTest suites passed: C++ smoke, public-contract and standalone-mode tests, plus
the MIT backend UHP test. All 23 vendored Nokamute Rust unit tests also passed.
Opening Base perft is 1, 4, 96, 1,440, 21,600, and 516,240 through depth 5;
depth 5 took about 134 ms on this machine. A 250 ms opening search completed
depth 6 with 77,016 nodes on one thread and 236,443 nodes on 12 threads.

Eight deterministic Base differential games matched the local Nokamute binary
through 40 plies. Base+MLP still has a reproducible terminal-state divergence;
the replay is in `CONTRACTS.md`, so expansion conformance is not established.

The clean mirrored 20-game Base strength run used 10 opening seeds, reversed
colors, 12 threads, 100 MiB tables, a 150 ms common internal search request,
a strict 250 ms response deadline, and a 160-ply cap. Alpha scored 1.5/20
(7.5%): 0 wins, 3 draws, and 17 losses. Maximum response times were 190.834 ms
for Alpha and 214.189 ms for Nokamute; no timeout decided a game. Evidence is
stored in `reports/nokamute-20-250ms-strength/`.

Under the same 20-game format, the exact MIT backend scored 10.5/20 (52.5%):
9 wins, 3 draws, and 8 losses against the local Nokamute binary. This is parity
evidence, not proof of deterministic identity: parallel search and time limits
permit move variation. Maximum observed response times were 198.305 ms for the
MIT backend and 198.013 ms for the reference binary. The manifest and every game trace are stored in
`reports/nokamute-mit-20-250ms/`.

A subsequent mini 10-game run used five mirrored openings, 450 ms internal
requests, and strict 500 ms response deadlines. The MIT backend scored 4/10
(40%): 4 wins and 6 losses. One timeout was charged to each engine, so this is
protocol-stress evidence rather than a clean strength estimate. Completed
responses peaked at 481.755 ms for Alpha and 485.945 ms for the reference.
Evidence is in `reports/nokamute-mit-10-500ms/`.

The second 10-game batch used the next five mirrored seeds with identical
settings. Alpha scored 7/10 (70%): 7 wins and 3 losses. One opponent timeout
occurred; completed responses peaked at 493.749 ms for Alpha and 491.292 ms
for the reference. Across both 500 ms batches Alpha scored 11/20, with three
timeout-decided games in total (one Alpha timeout and two reference timeouts),
so the combined result is encouraging but not a clean strength estimate.
Batch-two evidence is in `reports/nokamute-mit-10-500ms-batch2/`.

Earlier exact-230 ms attempts exposed Windows scheduling overruns in both
engines and are retained under `reports/` as protocol-stress evidence. Their
timeout scores are not strength evidence.

## Alpha performance pass (2026-10-04)

All four CTest suites and 23 Rust tests passed with the retained portable build.
All 13 dependency unit/integration/documentation tests also passed, including
the experimental stable-ordering equivalence test and search comparisons.
Nine frozen positions, 25 alternating paired measurements each at depth 4 and
one worker, gave a summed-median baseline/candidate ratio of 1.0182. This is a
small sampled throughput result, not a demonstrated strength improvement.
All 18 timed replies (one/two workers, 230 ms requests) were legal; maximum
observed response was 230.2924 ms. No hard deadline guarantee follows from this.

The component/split-depth suite checked nine positions with two workers and
three repeats per cutoff. Root scores matched across cutoffs 1, 2 and 3 on every
sample. Summed median search times were 127098, 118571 and 128082 microseconds;
default cutoff remains 1 pending broader validation. LTO/native and reusable
sorting experiments were not promoted. PGO execution is unverified because a
matching llvm-profdata was unavailable on PATH.

Evidence: reports/performance-retained.json and reports/profile-suite.json.
See PERFORMANCE.md for all six tracks, rejected experiments, reproduction and
the separate intelligence roadmap. No new strength or qualification claim is
made, and no Rho work was modified.

## Remaining work

### Gen 2 challenger (2026-10-06)

The current production Alpha is designated **Gen 1** and remains the default.
An isolated native neural challenger, calibrated Nu adapter, and Alpha-specific
bootstrap model are implemented. Neither earned promotion: historical Gen 1
screens scored 1.5/20 and 0/20 respectively, before the neural identity-sensitive
TT fix; those screens are not evidence for the repaired search. No sealed
qualification was run.
The trained model's Nokamute screen stopped after 18 games under resource pressure;
its seven points were opponent timeouts, not natural wins. Completed games and
failure evidence are retained for a matching resume when no competing heavy job
is active. See `GEN2.md` and `reports/gen2/` for exact verification scope, gates,
resource-contamination notes, and remaining limitations. No Iota content was used.

Latest Nu reliability-v8 checkpoint: calibrated on 249 development-only rows
at scale 0.1779741166522808; model and calibration frozen together. Fourteen
preflight replies were legal and within 250 ms. Fresh repaired-search Gen 1
screen completed at 1/20 (zero wins, one natural draw, one capped draw, three
challenger timeout losses). It failed advancement. Pinned Nokamute screen is
incomplete at 5/8: one natural win, three natural losses, four opponent timeout
wins. Repeated RAM-floor stops left it resumable, not qualified. Both screens
used one thread, a 32 MiB evaluator/table ceiling and 230/250 ms time control;
Gen 1 and Nokamute are related baselines, not independent engine families.

- Resolve Base+MLP behavior against the exact pinned revision.
- Improve the independent C++ evaluator/search if that implementation remains
  a research target; its clean gauntlet decisively failed.
- Validate a broader UHP conformance corpus, long pondering sessions, and
  malformed-input edge cases.
- Nokamute's WASM/browser product surface is not implemented.
