# Nokamute evaluation and neural engine failures

Nokamute beats the trained Nu candidates recorded in this project because it combines a useful Hive evaluation with an efficient search implementation. The neural candidates have an expensive feature pipeline, limited training coverage, and a validation objective that does not measure competitive move choice. These are supported mechanisms and measured weaknesses. The existing matches do not isolate their individual contributions, because Nu also changes the board, search, transposition policy and score scale.

The evidence establishes that these neural engines lost. It does not establish that handcrafted evaluation is inherently superior to neural evaluation in Hive. Alpha's independent C++ handcrafted engine also lost badly. A faithful MIT-derived backend achieved approximate parity with the reference. Implementation and search matter alongside the kind of evaluator.

This analysis covers the local pinned Nokamute revision `c9ab65e0d9f496fd8735096ae37babc8bb50a57c`, its MIT-derived Alpha backend, and Nu's completed campaign-v6. Rho has no comparable completed Nokamute strength test. The active Gen 2 implementation and Iota are outside the experimental evidence used here. Source snapshots and calculated aggregates are retained in `snapshot/` and `evidence.json`; `audit_evidence.py` reproduces the calculations using Python's standard library.

## What the matches establish

The four Nu runs share the same engine binary, opening family, one-thread setting, 16 MiB requested tables, 230 ms internal budget, 250 ms external deadline and 160-ply cap. Threat search and late move reductions were disabled. The runs were completed and accepted.

| Nu model | Points | Termination | Mean completed search depth | Median nodes per recorded search |
| --- | --- | --- | --- | --- |
| 64 linear | 2/20 | 20 natural finishes | 2.482 | 1,165.5 |
| 64 nonlinear | 1/20 | 18 natural finishes and 2 repetition draws | 2.650 | 1,143.5 |
| 128 linear | 0/20 | 20 natural finishes | 2.460 | 2,031 |
| 128 nonlinear | 2/20 | 20 natural finishes | 2.449 | 1,417 |

These totals are four wins, two draws and 74 losses across the four runs. The median completed depth is two for every model. One repetition-path search reached depth 64 in the 64 nonlinear run; the mean for that model should not be interpreted as typical depth. Search nodes include work outside the last completed iteration and are not a count of independent positions.

The shared openings and related models mean these 80 games are not 80 independent samples of one candidate. They cannot be pooled into a clean Elo estimate. Nevertheless, the failure is substantial and occurs across widths and architectures. It is not explained by opponent timeouts in these final runs.

Sources: `Nu/work/campaign-v6/nu-*-development.json`. Alpha's recorded independent C++ result is 1.5/20, whereas its MIT-derived backend scored 10.5/20 in a separate mirrored comparison; conditions and limitations are in `Alpha/STATUS.md`. Those separate runs are contextual evidence, not a controlled neural ablation.

## The actual handcrafted formula

`BasicEvaluator` scores from the player-to-move perspective. With default aggression three, its weights are:

| Term | Weight or operation |
| --- | --- |
| Queen liberty factor | 30 |
| Queen effective piece value | 12 |
| Ant | 7 |
| Beetle | 6 |
| Grasshopper and Spider | 2 each |
| Mosquito nominal reserve value | 8 |
| Ladybug | 6 |
| Pillbug | 5 |
| Effective deployed piece multiplier | 2 |
| Reserve piece multiplier | 1 |
| Established pillbug defense | 120 |
| Reserve pillbug defense | 60 |

The score has three major components: the difference in effective deployed and reserve pieces, the difference in queen-neighbor penalties, and pillbug defense. These terms have meaningful interactions; they are not an ordinary material count.

### Connectivity converts pieces into usable resources

The evaluator computes articulation points of the occupied hive with `find_cut_vertexes`. A single-height piece at an articulation point cannot leave without splitting the hive. Its effective piece contribution is skipped. Crawling pieces that have no slidable adjacent destination are also marked immovable.

An unpinned ant ordinarily contributes 14 at default settings. Pinning that ant removes the contribution. A spider contributes only four. This directly distinguishes losing a valuable mobile resource from immobilizing a less valuable one. Covered pieces are not independently counted in the loop over surface nodes. A stacked surface piece has its value doubled before the effective-piece multiplier; a surface beetle can therefore contribute 24.

This is coarse binary effectiveness rather than an exact count of every legal destination. The evaluator does not fully incorporate the last-move stun into its immovability estimate. It nevertheless exposes the globally important one-hive constraint directly instead of asking a model to infer it from coordinates alone.

### Queen pressure depends on reversibility and ownership

When a friendly surface piece fills its own queen's neighboring cell, the queen penalty is 30 if the piece is immovable and unstacked, or 15 otherwise. A movable obstruction is treated as less dangerous because it can leave. A piece next to the opposing queen applies a penalty of 36 to that queen and sets that piece's effective contribution to zero. The evaluator deliberately stops valuing an attacking stone as a freely available mobile resource.

An isolated comparison that moves an otherwise mobile ant from a neutral position next to the enemy queen loses 14 in effective ant value and gains 36 in opponent queen pressure: a net gain of 22 before changes to other pieces, connectivity and queen neighbors. This illustrates why the constants form a useful strategy even though the author describes them as mostly made up. They favor making a surround while still assigning value to the resources needed to construct it.

Every weight is modest compared with the search's reserved terminal scores. Queen surround wins and simultaneous surrounds are determined by `Rules::get_winner`, not guessed by this formula. Search can therefore reject a move that looks favorable statically but has a forced terminal refutation inside its horizon.

### Reserve and expansion logic add strategic context

Remaining pieces receive positive reserve value. Deployment exchanges some future placement capacity for effective mobility, which helps distinguish playing a useful piece from deploying one that immediately becomes pinned. Reserve availability can be inferred from a full Base position, but the direct formula requires no statistical evidence to assign it a consistent value.

Mosquito value depends on adjacent piece types, and on whether it is stacked. Pillbug defense examines neighboring empty landing cells and their liberties. An established defensive opportunity worth 120 can outweigh several ordinary pieces. The reserve defense bonus is discounted to 60 when a pillbug can still be placed near an unstacked queen. These expansion terms do not explain the Base-only Nu losses: there are no expansion pieces in those matches.

The formula also has imperfections that a neural evaluator could improve. Mosquito value is assigned as the loop visits neighboring non-queen types; it is not the maximum neighboring value. The pillbug landing calculation is a proxy rather than a full proof that every relevant throw is legal. An attacking pillbug branch assigns a queen penalty instead of accumulating it, which makes its interaction with earlier contributions worth testing. Low aggression also increases the penalty for opposing effective pieces, introducing a deliberate perspective asymmetry. These are reasons to study and improve the formula, not to assume every handcrafted detail is correct.

Source: pinned `eval.rs`, especially `BasicEvaluator::new`, `value`, and `Evaluator::evaluate`; the snapshot preserves exact code and its line numbering.

## Why search makes a small formula competitive

Nokamute's board uses a fixed wrapping 32 by 32 grid, compact surface nodes, a separate stack cache, incremental position hashing and make/unmake. Connectivity and move generation are designed around the small fixed board. A small leaf evaluator benefits when the engine can inspect enough continuations to resolve tactical consequences.

Default player construction enables iterative search, a transposition table, countermoves and countermove history. Previous search results and successful replies improve move ordering and alpha-beta cutoffs. The parallel implementation shares work through its own search design. Nu has independently implemented PVS, history, killers, counters, root work distribution and a contextual transposition table. Those capabilities do not make its operational behavior identical.

In particular, Nu permits transposition score reuse only when both the position key and its full accumulated history context match. That is conservative about repetition-dependent scores, but different paths to the same board will generally fail the context check. The cached move can still assist ordering. Nokamute's table is keyed by its game hash; its repetition handling is different. This is a correctness and efficiency tradeoff to measure, rather than a reason to weaken Nu's checks without validation.

### Quiescence exists but is not enabled by default

Nokamute's evaluator implements a Hive-specific noisy-move policy intended to avoid stopping immediately after placement, before the new piece gets to move. However, minimax's default `max_quiescence_depth` is zero, and Nokamute enables depth two only when `--quiet-search` is selected. Null-move pruning and aspiration windows are also optional in the inspected defaults.

There is an additional detail: the noisy-move function returns immediately when the player's queen is already placed. Its comment describes waiting until movement is possible, but its implemented condition is not a general post-placement extension in ordinary queen-placed middlegames. It needs a behavioral test before being recommended as a tactical cure. The recorded Nu opponent invocation supplies neither quiet search nor null-move pruning. A claim that default quiescence explains these wins would be incorrect.

Sources: pinned `player.rs:285`, vendored minimax `strategies/iterative.rs:133`, pinned `eval.rs` noisy-move method, and the arena invocation manifests.

## Nu pays for features before it can use the network

Nu's schema-four network has paired accumulators. Integer accumulator sums are updated by differences between old and new active feature lists. That does not mean that feature extraction itself is incrementally maintained.

`State::make` rebuilds the next feature list after virtually every generated move. Schema four computes mobility for both colors, connectivity flags, gate-access proxies, queen-relative coordinates and stack/control inputs. Its mobility shortcut applies only to a particular occupied-to-occupied beetle move whose source remains occupied. Ground moves and placements generally reconstruct mobility. This work occurs even before the subsequent search call can discover that a node is terminal or a leaf.

The recorded final single-thread timing suite contains 18 samples. Feature construction accumulated 3.293 seconds over 4.146 seconds of measured response wall time: **79.43%**. This timer covers the mobility refresh and feature construction, not the entire accumulator update or integer dot product. At multiple threads its summed worker timers exceed response wall time, as expected; those ratios must not be interpreted as serial fractions.

The model matrix multiplication is therefore not the only, or necessarily the main, cost. A neural engine can have fast integer inference while spending most of its budget manufacturing neural inputs. This is a directly measured performance defect relative to the intended efficient NNUE design.

An idealized elimination of that entire measured serial fraction would imply a maximum speed factor of about 4.86 on these samples. Feature computation cannot actually be eliminated, and a changed pipeline can alter caching and ordering, so this is an upper-bound illustration rather than a forecast. There is no paired Nokamute depth profile on these exact positions in this audit; the evidence does not establish the precise number of plies lost to features.

Sources: `Nu/src/state.hpp:24`, `Nu/src/features.hpp`, and `Nu/work/campaign-v6/final-thread-timing.json`; calculations in `evidence.json`.

## The networks learn a small and particular approximation problem

The completed first stage contains 13,032 raw positions from 271 source games: 252 natural finishes, 17 capped games and two repetition endings. After filtering, the training split contains 10,387 positions and validation 2,260. Natural source-game counts are 216 and 36. The collector follows a 20 ms search teacher after random opening moves, with an eight-percent random continuation probability; there was no source Nu model in this corpus configuration. Alternative children are searched for five milliseconds.

The teacher creates a fresh serial search with 16 MiB tables for each request. Scores are converted to White's perspective and multiplied by four. The raw labels have a median principal-variation length of four; PV length is not a certified completed-depth metric. This is a useful teacher, but it does not provide deep, persistent-search certainty across the training set.

The network learns `tanh(raw_output)` against `tanh(teacher_search_score / 600)`. For natural endings, the target blends 90% teacher target and 10% final outcome. Capped and repetition games do not receive invented outcome labels. A ranking term with weight 0.05 favors selected children over sampled alternatives. Validation and checkpoint selection use blended-target MSE.

Nu's integer inference scales raw output by 600. The teacher multiplication by four means this is a different unit system from native Nokamute evaluation. A uniform positive scale would preserve exact full-width minimax ordering, but finite windows, quantization, training loss and truncation can interact with calibration. Score orientation is consistent in the inspected pipeline: teacher labels and training predictions are White-oriented, while native inference selects the mover's perspective. Exact integer inference verification provides evidence against a blanket claim of broken score signs or bad export.

### Model capacity and coverage

An 8192 by 64 embedding already contains 524,288 weights; width 128 contains 1,048,576. Biases, outputs and an optional 32-unit head add further parameters. Sparse sharing means simple parameter-to-example ratios are not a proof of overfitting. They do show that 10,387 related positions must support a large approximation with many rare feature combinations.

Both widths and both heads trained for 24 epochs and 1,968 updates. **Every selected checkpoint is from epoch one.** This is a warning about later generalization and the chosen optimization/regularization/data regime. The final training report alone does not reveal the complete per-epoch validation curve or identify a single cause, so increasing epochs or width is not an evidence-based remedy.

| Model | Best held-out target MSE | Selected epoch | Development points |
| --- | --- | --- | --- |
| 64 linear | 0.06219445 | 1 | 2/20 |
| 64 nonlinear | 0.06299927 | 1 | 1/20 |
| 128 linear | 0.06420996 | 1 | 0/20 |
| 128 nonlinear | 0.06145178 | 1 | 2/20 |

A value RMSE around 0.25 in this transformed target space is substantial. It cannot be converted to a universal centipawn error because tanh is nonlinear, outcomes are blended and these are Hive score units. Correct native reproduction of the exported network proves that the intended approximation is running; it does not prove that approximation preserves the teacher's move preferences.

### Position error and decision error differ

Search chooses among competing children, often with small value gaps. An average position error objective can improve while the network reverses the ordering of the critical best move and its refutation. The training scheme includes preferences, but model selection does not directly minimize search decision regret, tactical misses or playing losses. Self-play teacher positions also do not cover every losing or adversarial line visited by the student's search. Searching a learned evaluator can preferentially find positions where its errors look attractive; this distribution shift is a plausible mechanism that requires targeted measurement.

The raw corpus has 2,183 positions, or 16.75%, where the static teacher and searched teacher scores have opposite nonzero signs. This confirms that search targets carry information beyond simple static imitation. It does not measure neural ranking error. There are 807 raw search labels with absolute score above 2,400, or 6.19%, all within the collector's 6,000 clamp. At those scales tanh is nearly saturated, so larger raw-score distinctions produce little value-loss gradient. Terminal outcomes remain the search's responsibility.

### Symmetry and feature aliasing

The features contain queen-relative coordinates, per-piece identity, shared piece roles, local cells, mobility and stack flags. They are more informative than raw occupancy. However, their coordinate hashes are not made invariant to Hive rotations and reflections. No symmetry augmentation is implemented in the inspected collector/trainer. Missing identity invariance among interchangeable ants or other repeated pieces can also fragment learning; the shared-role features partially address this.

Hash banks necessarily alias distinct configurations. The raw corpus contains 255,265 repeated active indices out of 2,511,948 feature occurrences across both perspectives. That **is not an accidental-collision rate**: some feature repetitions intentionally represent shared flags or multiple occurrences. Measuring harmful aliasing requires recording the semantic feature keys before hashing and checking score conflicts or ablations. A collision-free tactical bank and symmetry experiments are justified tests, not established explanations for the match gap.

Sources: `Nu/tools/collect.py`, `Nu/tools/learning.py`, `Nu/tools/teacher/src/main.rs`, `Nu/src/model.hpp`, `Nu/src/features.hpp`, corpus manifest and model training reports.

## Causes ranked by current evidence

| Finding | Evidence status | What it explains |
| --- | --- | --- |
| Expensive feature reconstruction | Directly measured and traced in source | Reduced work available inside a fixed search budget |
| Handcrafted connectivity and queen pressure | Exact source behavior | A reliable strategic prior with no training requirement |
| Limited corpus and epoch-one selection | Recorded training facts | A concrete reason to investigate generalization before enlarging models |
| Whole-engine comparison confounds | Exact engine settings and different source implementations | Why the score gap cannot be assigned entirely to evaluation |
| Target loss versus move ordering | Objective verified; strength failure observed | Why low validation loss is insufficient for promotion |
| Student search exploits approximation errors | Plausible, not isolated | A possible mechanism for mistakes outside teacher trajectories |
| Hash aliasing and missing symmetry | Representation verified; damage unmeasured | Possible sample-efficiency and expressivity losses |
| Incorrect model orientation or export | Inspected code and existing parity checks argue against it | Not a supported general explanation |
| Default quiescence advantage | Defaults and invocation contradict it | Not an explanation for these recorded matches |
| Neural networks cannot play Hive well | Unsupported | No architecture-wide conclusion follows from these candidates |

## Experiments that can resolve the remaining uncertainty

The first priority is the Gen 2 developer's comparison through identical Alpha search. Use pinned Gen 1 and neural artifacts, the same openings and terminal policy, a shared total memory ceiling, and actual allocated TT capacity. Verify fixed-depth Gen 1 scores before interpreting new matches. Keep development tests separate from sealed qualification.

Within that common search, compare at both fixed completed depth and fixed elapsed time. Fixed depth better isolates decision quality; fixed time captures feature overhead and search efficiency. Log nodes, legal move counts, completed depth, evaluator calls, feature time and inference time. A model that ranks better at fixed depth but loses at fixed time is primarily a deployment-cost problem; one that loses both needs data or evaluation improvement. This inference still depends on exact rule and search parity.

Next, evaluate all legal children of held-out development positions with a longer frozen Gen 1 analysis budget. Measure top-choice agreement, regret relative to the best child, sign mistakes, and performance on small-margin decisions. Retain separate slices for queen escapes, forced surrounds, articulation changes, stack moves, reserve deployment and adverse student-generated states. Do not select those slices using final qualification outcomes.

Separate feature-cost changes from model changes. Keep weights and exact features fixed while incrementally maintaining connectivity/mobility inputs or reducing repeated generation. Prove accumulator and feature equality after every make/unmake before timing it. A speed change can then be attributed to implementation rather than new learned strength.

For learning, compare static-teacher targets, searched targets and separately weighted natural outcomes through the same search. Report transformed MSE alongside ranking regret and tactical errors. Compare symmetry augmentation and exact tactical feature banks with the same accepted positions and optimizer budget. Preserve the best epoch and learning curves. Increase corpus diversity, especially defensive and losing lines, before interpreting larger width as the solution.

Finally, ablate the handcrafted evaluator in an isolated baseline: mobility/pinning, queen pressure, reserves and expansion-specific terms separately. Fix search and score conventions. That establishes which inexpensive domain priors account for actual wins. A residual neural model over the unchanged handcrafted score is an additional research control if authorized; it is a distinct design from the active Gen 2 replacement plan and should not be silently substituted for it.

## Implication for Genseki

Nokamute's current advantage is credible as an engineering advantage: it computes useful Hive abstractions cheaply, assigns them consistent values, and searches their consequences efficiently. Nu learns an approximation from a limited teacher distribution while repeatedly paying for complex features. The recorded experiment then changes the search implementation as well. Better neural inference arithmetic alone cannot remove those disadvantages.

The appropriate claim is that the current handcrafted engine is the stronger verified incumbent. The most promising path is to preserve its search, measure neural decision quality separately from feature cost, and train against the failures exposed by that common pipeline. The existing evidence identifies what to fix and what to measure; evaluator-only causal attribution awaits those controlled comparisons.
