# Iota Verified Status

Evidence collected October 6, 2026. Independent prototype, not a qualified
competitive champion. The complete requested research campaign is unfinished.

## Verified

- Standalone GNU 14.1.0 Release build produces build/iota.exe.
- Native CTest passes: initial perft 1/4/96/1440, reversible state/hash checks,
  deterministic 80-ply stress, position round trips, destination coverage,
  constant-network shallow minimax, forced TT bucket collisions, repeatability,
  zero-budget legal fallback and PV replay.
- Python reference tests pass for all four CNN/GNN configurations: exported
  value/policy agreement on two opening positions, truncated-model rejection,
  legal 250 ms search responses in both modes, four-lane inference equality,
  graph permutation invariance and invalid thread option rejection.
- 22-piece chain under twelve symmetries has identical canonical identities
  and no omitted CNN/GNN legal destinations. Perft divide sums correctly.
- Collected 160 smoke positions from 20 capped, 12-ply Alpha teacher games at
  50 ms. Splits: 128 training, 16 validation, 16 diagnostic test positions.
  All value targets are absent: these runs exercised policy training only.
- All four configurations trained on CUDA for two optimizer updates, effective
  batch two, seed 1701. GNN32 then resumed for one additional update. This is
  a pipeline smoke test, not a fair architecture strength comparison.
- Observed peak CUDA allocation: CNN32 26,955,264 bytes; CNN64 45,081,600;
  GNN64 20,610,048; resumed GNN32 17,759,232. These observations do not predict
  the memory requirements of the full campaign.
- GNN32 inference benchmark completed 1,800 samples: twelve opening positions,
  thirty repeats, five thread settings. Median end-to-end inference command
  latency: 1 thread 0.363 ms, 2 threads 0.886 ms, 4 threads 1.243 ms,
  8 threads 2.779 ms, 12 threads 5.490 ms. This is not full-search latency,
  a CPU-load test, or a representative tactical suite. Default remains one.
- Initial two-game probe produced Alpha timeout points only; retained as
  timing evidence, never promoted as strength evidence.
- Corrected probe: equal 230 ms internal allowances, 250 ms external deadlines,
  two mirrored games, Base Hive. Iota lost 0/2, both natural results.
  Audit found Alpha actually used 12 threads while Iota used one: the runner
  missed Alpha's NumThreads option. Neither probe is thread-matched evidence.
  Maximum recorded move times were 233.455 and 231.230 ms. No result divergence.
- Qualification has NOT run. No candidate or architecture has been promoted.

## Implemented But Not Fully Validated

- Audit corrections: verified NumThreads pinning, full match-state agreement,
  exact-state match repetition, checked UHP framing/options get, nonfinite
  export rejection, encoder index validation, training failure checkpoints,
  corpus/benchmark failure evidence, normalized heavy-job process paths, and
  MCTS cancellation path restoration. Native CTest and Python regression suite
  passed after the initial corrections; no new strength match was run.

- Independent C++ PVS and PUCT, native model format/operators, rules adapter,
  effective inference threads, resource guards, resumable training, bounded
  corpus/campaign orchestration, performance ladder and mirrored match runner.
- Qualification runner freezes hashes, exclusively consumes an attempt before
  generating random final seeds, checks legal-move sets, records natural/capped/
  repetition/timeout outcomes, and requires at least 50/100 points.
- Python training retains final and best-validation native exports. Training
  resumes only for matching corpus/configuration; collection counters survive
  through committed corpus/manifests.

## Still Required From The Plan

- Real 10k/50k/200k corpora; 2,000 updates for each model with three seeds.
- A substantial collected corpus of teacher multi-alternative rankings and
  numerical search targets. The original Alpha collector still emits one-hot
  policy; the new frozen-Iota collector is implemented, not yet campaign-tested.
- Outcome-supervised training from naturally completed games, not smoke caps.
- Completed symmetry-control training trials; disjoint-graph training batches.
- MCTS leaf batching, reservations/cancellation rollback, subtree reuse and
  self-play root noise. Current MCTS is serial and rebuilds its tree per search.
- Mandatory-defense extensions established by legal replies. Immediate wins
  are implemented; complete threat-search defenses are not.
- More efficient CNN inference, incremental encoding and reusable buffers;
  the large CNN often completes no alpha-beta depth within the smoke budget.
- Comprehensive tactical/repetition/covered-Queen/stack suites, varied-network
  exhaustive minimax tests, full UHP conformance,
  full-search timing ladders and controlled CPU-load tests.
- Complete replay-validation/self-play CLI, automated eight-combination match
  selection, confidence intervals and incumbent promotion management.
- Mirrored 20-game development matches for all eight combinations, finalist
  100-game development runs, and only then sealed 100-game qualification.

## Evidence Locations

- work/smoke-corpus.jsonl and its manifest.
- work/cnn32.*, cnn64.*, gnn32.*, gnn64.*: smoke models/checkpoints/reports.
- work/gnn32-bench.json: partial first benchmark; retained.
- work/gnn32-bench-v2.json: completed inference ladder.
- work/smoke-match.json: initial timing-only probe.
- work/smoke-match-reserved.json: corrected natural-loss probe.

No Alpha/Nu/Rho/GUI source was edited by this implementation. Iota remains
ignored, so committing the root checkout will not include this work unless
its tracking policy is explicitly changed later.

## Hive-Native Upgrade, October 6

Implemented inside Iota only:

- v2 stone/frontier GNN, including buried stones, ordered stacks and five
  relation types. Legal movement connections come from the rules engine.
- v2 D6-tied hex CNN and v3 untied CNN control with identical input domain,
  action descriptors and operator normalization. Legacy v1 remains loadable.
- All-twelve-symmetry augmentation with explicit target-index permutation.
- MCTS visit-target diagnostics, bounded exact one-reply tactical labels,
  partial child-search ranking collection and side-to-move search targets.
- Pairwise ranking/tactical losses, frozen teacher policy/value distillation,
  tactical-position sampling, disk-indexed corpus and stricter split checks.
- Teacher/student orchestration, best checkpoint/export pairs and native
  full-search benchmark reporting, including nodes/depth and deadline misses.
- Loaded-position diagnostic play/undo restoration and forced-pass endpoints.
  Handcrafted position snapshots cannot emit valid opening replay strings;
  diagnostic play uses move indices instead of fabricated UHP game strings.

Verified evidence in work/upgrade-v2/verification-resumed.json: native CTest and
19 Python tests passed. Tests cover covered Queens, typed links, twelve
symmetries and policy remapping, native/reference prediction agreement,
large-model exports, node permutations, cross-architecture distillation
gradients, probability masks, split leakage, exact wins and mandatory
defenses against legal reply enumeration, forced pass, and the matched
tied/untied operator control. This is a correctness suite, not a strength gate.

Initial heavy Iota work was deferred while an independent Alpha arena was
active. Once it ended, a bounded three-minute CUDA pipeline pilot completed:
50 optimizer updates each for a 64/6 GNN teacher and 32/4 GNN student, batch
four, seed 1701, on the existing 160-position policy-only smoke corpus.
Teacher/student parameter counts were 153,428/27,508, with peak allocated
CUDA memory 20,403,200/18,549,248 bytes. This is not a strength training corpus.

Completed native timing pilots used twelve smoke positions, three repeats,
one thread, and both PVS and MCTS: 36 inference samples and 72 timed searches
per model. Teacher/student median inference command latency was 1.5835/0.9075
ms; average completed PVS depth was 1.3611/2.1944. All returned moves were legal,
with zero observed 250 ms deadline misses (maxima 230.9351/231.2306 ms).
Different value heads and small opening-biased samples prevent treating deeper
search as playing-strength evidence. Evidence: work/upgrade-v2/pilot/.

A one-minute collector pilot accepted 20 search-backed examples, with no
rejected rows, split 16/2/2. It exercised full legal root visit distributions,
two partial child-search alternatives, exact tactical labels and split-aware
bounded collection. Evidence: work/upgrade-v2/search-pilot.*. Targets remain
teacher estimates, not natural outcomes; no naturally completed games were
added. The CNN symmetry-control training trial has not been run.

The subsequent ranked-student integration run initially stopped at zero
updates when free RAM crossed the 0.5 GiB floor; no automatic resource-stop
retry occurred. After the user restored RAM headroom (about 5.3 GiB free),
the same checkpoint/configuration resumed and completed all ten updates.
Peak allocated CUDA memory was 18,537,984 bytes; held-out combined objective
was 3.1548053 on two smoke validation positions. These are pipeline metrics,
not playing-strength evidence. Model SHA256:
cf72434dd632bd88502e0e6ac1b029c9e0dcd56df90cae20a1a1daf52de892fd.
Evidence: work/upgrade-v2/ranked-student.*. The additional regression for
masking untrained teacher value heads now passes in the 19-test suite.
The pilot correctly recorded teacher_value_mode=none: an outcome-untrained
teacher value head was not distilled into the student's objective.

The Nu mini-gauntlet was no longer running when checked.
The guard now recognizes both Nu arena jobs and Alpha gen2 arena/training jobs.
No other agent's job was stopped. No candidate is promoted or claimed stronger.

## Verified Development Strength

The ranked-student checkpoint was tested against frozen Alpha in two mirrored
20-game development matches, one per independent search mode. Both engines
used one thread, a 250 ms external deadline and a 160-ply cap; Iota used a
230 ms internal budget. Opening seeds were 95011 through 95020.

- Alpha-beta: 0/20 points, 19 natural losses and one Iota timeout.
- MCTS: 1.5/20 points, 18 natural losses, one repetition-adjudicated draw
  and one Alpha timeout.
- Neither mode won a naturally completed game. Neither candidate passed.

These are development results, not the sealed 100-game qualification.
The checkpoint had only ten updates on twenty search-backed pilot examples;
this measures that checkpoint, not a definitive CNN-versus-GNN comparison.
Reports with complete replays and artifact hashes are retained in
reports/strength-v2/. No strength promotion is justified.

Initial probes were rejected because the verifier compared notation strings
instead of replayed positions: Alpha can return equivalent reference aliases.
The verifier now replays differing aliases and compares exact board states,
while still checking result, side and turn headers. A regression covers both
equivalent aliases and mismatched turn headers. Rejected probes are retained
separately and do not count toward either match.
