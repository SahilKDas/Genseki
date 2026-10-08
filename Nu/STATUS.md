# Nu Verified Status

Initial evidence was collected 2026-10-05. Later verified work is recorded below;
build and compatibility checks are not strength qualification.

## Combined Schema 5 And 6

Both developers' Nu implementations are integrated in the main checkout.
Fast/residual schema 5 and canonical-symmetry schema 6 remain separate contracts;
the untrained default stays schema 3. All 11 standalone Nu suites and all 15
selected root integration suites passed. The combined root executable matched
the frozen trained schema-5 evaluator on 379 positions and schema 6 on 384;
each also matched 12 depth-one searches including move, score, nodes and PV.
Legacy schemas 1--4 matched 384 positions and 12 searches per schema with seed
weights. No new training, match, qualification, or production promotion occurred.
See `COMBINED_INTEGRATION.md` for hashes, reports, full backups and commit scope.

## Verified

- Standalone MinGW Release build and all four CTest cases pass. Root CMake
  integration builds Nu and its tests without replacing default Alpha.
- Rules opening perft depths 0..3: 1, 4, 96, 1440.
- Twelve deterministic random games per width, up to 100 plies each:
  full-refresh accumulator checks after every make/unmake; complete unwind
  restores the starting serialization. SIMD dot products equal scalar values.
- Single-thread depth-2 repeatability, four-thread score equivalence, zero-budget
  legal fallback, UHP play/undo, option rejection, invalid move rejection,
  pondering cancellation, and invalid model rejection pass.
- Additional 20-game CLI stress checks serialization round trips and accumulator
  equivalence at each make/unmake. Replay validation and perft divide are available.
- Actual GPU training: 2194 positions from 20 games; 7 naturally terminal,
  13 capped. Training/validation: 1714/480 positions, disjoint by source game.
  Eight epochs, batch 128, 112 updates for **each** architecture.
- 64-wide validation MSE 0.07548018; peak CUDA allocated 11,765,760 bytes.
- 128-wide validation MSE 0.08053603; peak CUDA allocated 23,181,824 bytes.
- Native integer inference matches Python exported-weight inference exactly
  over 400 positions per width. Maximum float deviation: 3.8178 cp (64),
  5.3218 cp (128). These are observed sample maxima, not universal bounds.
- Mirrored 20-game 250 ms development runs against independent, unmodified
  Nokamute 1.0.3, revision c9ab65e0d9f496fd8735096ae37babc8bb50a57c:
  64-wide 5/20; 128-wide 6/20. All points came from opponent timeouts;
  every naturally finished game was a Nu loss. No rules/protocol divergence
  occurred in those runs. Single search thread, pondering/random opening off,
  16 MiB tables, 230 ms internal allowance, 160-ply cap.
- Those matches preceded the final aspiration/SIMD/PV diagnostic changes;
  they do not establish the strength of the final build.

Artifacts and complete game records: Nu/work/. The upstream reference checkout
is isolated in .tmp/nu-nokamute; its generated Cargo.lock pins dependencies
because the source revision did not include a tracked lockfile.

## Subsequent Verified Development

- Independent search now uses root PVS, incremental position/history hashing,
  trusted generated-move application, killer/history ordering, and contextual
  TT score reuse. Brute-force depth-2 comparison and mate-in-one tests pass.
- Six fixed depth-2 positions with the unchanged bootstrap model measured
  30.639x aggregate speedup against the preserved earlier executable, with
  identical scores and moves. This small benchmark is not a universal claim.
- Tactical schema 3 adds articulation, gate-access proxies and Queen liberties;
  schemas 1 and 2 remain loadable. All final scores remain learned NNUE outputs.
- The new corpus has 3288 positions split 2706/582 by source game. Targets
  distill Nokamute's static evaluation, blended with natural outcomes, rather
  than establishing independent architecture superiority.
- Both widths completed 24 epochs and 528 updates. Held-out target MSE:
  64-wide 0.024030584; 128-wide 0.023498072. Peak allocated CUDA memory:
  19,080,192 and 36,562,944 bytes respectively.
- Packed embedding-bag forward values and gradients match explicit sums.
  Both exports passed 400 exact native integer inference comparisons;
  sampled float deviations were 6.205632 cp and 7.964738 cp respectively.
- Tactical 64-wide development finished at 2/20 points, entirely opponent
  timeouts. It failed promotion. The 128-wide run was rejected after eight
  completed games when engine results diverged (InProgress versus Draw).
  Its partial points are not a valid completed gauntlet score.
- The earlier distilled 128-wide candidate lost all 20 naturally finished
  development games. No candidate is qualified; final seeds remain unused.
- Nokamute repetition draws are explicitly marked in teacher collection with
  no outcome label. They are not silently added to core rules. Arena result
  divergence remains a run-rejection condition.

## Full-Strength Campaign: Verified First Stage

- Independent Nu search now has four-entry depth/age-replaced TT buckets,
  history-context score validity, mate normalization, persistent iterative-depth
  killer/history ordering, countermoves, reusable buffers and generation
  cancellation. Threat search and LMR are experimental and disabled by default.
- Schema 4 includes engine-defined mobility, Queen escape, pinning, stack and
  gate inputs. The nonlinear format uses paired accumulators and a shared
  32-unit head with perspective-swapped antisymmetric output. Legacy exports
  remain loadable. No handcrafted scoring fallback was added.
- Resumable, bounded-batch training and staged campaign tooling are implemented,
  including grouped leakage filtering, search-backed teacher targets, ranking
  examples, optimizer/random-state checkpoints and atomic evidence reports.
  These are implemented capabilities, not evidence that all stages ran.
- First stage collected 13,032 raw positions; 12,647 survived filtering:
  10,387 training and 2,260 validation positions. Retained natural source games
  numbered 216 training and 36 validation, below the outcome-only fine-tuning
  gate. No outcome-only fine-tuning was run.
- All four schema-4 models completed 24 epochs and 1,968 optimizer updates
  using the same corpus and budgets. Best held-out MSE:
  64 linear 0.06219445; 64 nonlinear 0.06299927;
  128 linear 0.06420996; 128 nonlinear 0.06145178.
  Maximum allocated CUDA memory was 45,323,264 bytes, below 1.5 GiB.
- All four exports passed 400 exact native integer inference comparisons.
  Observed maximum float deviations were respectively 8.6051, 7.1417,
  12.7586 and 6.2762 cp. These are sampled errors, not universal bounds.
- The final standalone build passed all four CTest cases. Differential
  conformance against pinned Nokamute passed 987 positions across ten games.
  Engine SHA-256:
  `ffb851ecc55decab7e9cdfc5594ed075dcceb57e25bd41b283a92272fdf41456`.
- Four completed mirrored 20-game, 250 ms development matches, using one
  search thread, 230 ms internal budget and disabled threat search/LMR:
  64 linear **2/20**, 64 nonlinear **1/20**, 128 linear **0/20**,
  128 nonlinear **2/20**. The nonlinear 64 points came from two repetition
  draws; the two-point runs each had two natural wins. No candidate passed.
- Repetition is an explicit symmetric match policy matching the pinned
  opponent, not a change to vanilla core results. The original rejected run
  lacked a complete failing replay and cannot be retroactively reconstructed.
  New arena reports retain attempted moves and atomic partial/failure evidence.
- Final-build timing: eighteen measurements per thread setting on six fixed
  positions, across 1/2/4/8/12 threads, returned legal moves without a 250 ms
  deadline miss. Maximum observed latency was 231.837 ms; one thread had the
  highest summed completed depth. This is a small performance suite, not a
  strength endorsement or a hard real-time guarantee.
- A further eighteen one-thread measurements with two bounded CPU-load workers
  returned legal moves without deadline misses (maximum 230.638 ms).
  Python leakage, antisymmetry, accumulation and exact CPU checkpoint-resume
  tests passed. No GPU bitwise-resume guarantee is claimed.

Evidence: `Nu/work/campaign-v6/`, including model training/verification files,
completed development reports, conformance and final timing reports.

## Remaining Work

### Deadline And Decision-Quality Experiment

- Search timing now starts before setup, reserves up to ten milliseconds for
  cleanup/response preparation, and checks generation cancellation every four
  callbacks rather than sixteen. Search remains full width with a legal fallback
  and last completed depth; no new selective pruning was enabled.
- Candidate timing passed 180 idle and 180 two-load-worker responses on six fixed
  development positions, one search thread: zero 250 ms misses. Maxima were
  226.469 ms idle and 224.155 ms loaded. This is sampled evidence, not a hard
  real-time guarantee or proof across all positions/thread counts.
- The trainer records held-out sampled-action regret, top-choice agreement and
  validation curves, and supports regret-based selection with resume identity
  checks. Defaults retain the previous MSE selection and ranking weight.
- A three-minute CUDA fine-tune used existing corpus/model, batch 128, learning
  rate 0.0002 and ranking weight 0.25. It stopped at 177 resume updates; the
  selected fully validated epoch-two artifact contains 164 fine-tuning updates.
  Eight requested epochs did not complete; evidence explicitly records this.
- Across 569 held-out partial-action decisions, regret fell from 146.573 to
  115.220 score units; top-choice agreement changed from 74.165% to 74.868%.
  Validation MSE worsened from 0.061452 to 0.068413. No strength conclusion or
  candidate promotion follows from these mixed offline metrics.
- Candidate export passed 400 exact native integer inference comparisons;
  maximum sampled float deviation was 9.255 cp. Reports/checkpoints/timing:
  `Nu/work/reliability-v8/`. Final qualification remains unused.
- Native quantized ranking audit on the same 569 partial-action lists:
  incumbent regret 146.362, candidate 114.735; agreement 74.341% versus 75.220%.
  These static-evaluator metrics are not search-choice or strength guarantees.
- Same-engine mirrored candidate/incumbent development match, seeds 73000-73009,
  one thread and 250 ms external deadline: candidate **11.5/20**, seven natural
  wins, four natural losses, nine adjudicated draws, zero timeouts. This is
  promising small-sample evidence only; the candidate remains unpromoted.
- Subsequent pinned-Nokamute development match, seeds 74000-74009: **0/20**,
  all natural losses, zero timeouts, completed without rejection. The candidate
  fails the external strength gate despite better sampled-action regret and an
  internal match edge. Retain the incumbent; no champion/default model change.
  This does not isolate the evaluator from Nu's independent search limitations.

### October 6 Exact-Feature Performance Repair

- Features are now rebuilt only on evaluation, not on every search make.
  Terminal/repetition/TT returns do not need neural input reconstruction.
- A 256-entry per-thread cache stores complete features and mobility under
  exact serialized state/schema keys. It does not cache history-dependent
  search scores, change model weights, or introduce heuristic evaluation.
- Eager-reference versus lazy/cache tests cover skipped evaluations, nested
  make/unmake, cancellation, feature/accumulator equality and shallow search.
  All four CTest groups passed. Feature diagnostics force refresh before output.
- Thirty-six paired cold-cache depth-two samples per nonlinear model returned
  identical moves, scores and node counts. Measured speed factors: 64-wide
  1.26037 and 128-wide 1.254. This is not evidence of improved match strength.
  Evidence: `Nu/work/performance-v7/feature-benchmark.json`; reproducer:
  `nu_feature_bench MODEL_PATH`. The 80% bottleneck is reduced, not eliminated.
- New mirrored twenty-game development run, seeds 72000-72009, pinned Nokamute,
  one thread, 230 ms internal/250 ms external: **4/20 total**, consisting of
  one natural win among thirteen natural finishes, three opponent timeouts,
  and four Nu timeouts. Report completed without rules/protocol rejection.
  Evidence: `Nu/work/performance-v7/nu-128-nonlinear-development.json`.
  Different openings and timeout contamination prevent a paired strength
  conclusion against the older campaign. Deadline reliability remains a
  blocking gate; no model or champion was promoted, and final seeds stay unused.

- This is a trained, playable initial Nu implementation, **not the entire
  ambitious research plan completed or a qualified champion**.
- Run the 50,000 and 200,000 accepted-position stages, diverse Nu self-play,
  feature-group ablations and sufficient independent natural outcome games.
- Broaden tactical/selective-search checks and statistical strength gates.
- Full UHP conformance and richer CLI analysis/interactive modes.
- Complete TT PV reconstruction; selectively pruned search only after
  tactical validation. No unsupported search optimization claims.
- Symmetry augmentation/invariance studies and collision-free feature ablation.
- Broader repeated end-to-end performance measurements under CPU load.
- Internal incumbent matches, 100-game development confirmation, final
  qualification and champion promotion remain unrun for this campaign.
  Final qualification seeds remain unused; no new model is promoted.
