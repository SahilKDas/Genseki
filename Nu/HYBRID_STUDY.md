# Independent Hybrid Evaluator Development Study

The full handcrafted + trained schema-7 candidate remains opt-in. No promotion,
default change, training, sealed qualification, commit, or push occurred.
This addition imports no opponent code or weights. Alpha Gen 1 is an opponent;
offline decision labels come from the already retained Gen 1 teacher corpus,
not newly generated teacher data.

## Frozen Controls

Portable evidence: `Nu/reports/hybrid-v1/results.json`. Full pinned artifacts,
roots, trials and atomic game reports are in `Nu/work/hybrid-study-v1`.
Both Nu sides use the same new executable and existing schema-7 checkpoint.
The experiment changes only `HybridEvaluation`, with weight 100 and all six
terms enabled (`HybridTerms 63`). The opponent's mode is disabled.

Ten fresh deterministic four-ply openings were frozen before profiling/matches.
Their canonical keys avoid the retained schema-7 training/validation exposures,
fast-incumbent exposures, previous development openings, tactical keys, and the
public reserved qualification-family keys. Private sealed openings were not read
or played. Every opening is played twice with colors reversed.

All matches use one thread, 16 MiB tables, a 64 MiB evaluator-plus-table ceiling,
pondering off, threat extensions off, LMR off, depth limit 64, 230 ms internal
requests, 250 ms external deadlines and a 160-ply cap. Both shared locks, Idle
priority and existing resource floors remain in force. Each stage finished
within two hours. Resume identity now includes hybrid mode, weight and term mask;
older reports missing these fields cannot silently resume under changed settings.

## Cost And Depth

There are 39 identical nonterminal roots. One continuation naturally ended
before its fourth checkpoint. Cost trials use consumed native scores and legal
make/evaluate/unmake on identical children. Five shuffled configuration rounds
reduce order effects; search profiles themselves are sequential and still subject
to system/thermal noise.

| Configuration | Cached evaluation total | Make/evaluate/unmake total | Depth sum | Profile timeouts |
| --- | ---: | ---: | ---: | ---: |
| Plain schema 7 | 0.3697 ms | 17.8782 ms | 114 | 0 |
| Full hybrid | 2.0674 ms | 21.5088 ms | 107 | 0 |
| Without neighbors | 1.7464 ms | 17.9861 ms | 89 | 1 |
| Without friendly surround | 1.8108 ms | 19.3772 ms | 95 | 0 |
| Without Queen control | 1.7590 ms | 18.3861 ms | 93 | 0 |
| Without nearby Beetles | 1.7890 ms | 18.8733 ms | 90 | 1 |
| Without Queen exits | 0.5676 ms | 19.4774 ms | 96 | 0 |
| Without critical liberties | 1.6550 ms | 17.9263 ms | 95 | 0 |

Cost entries are medians of five trials, not per-move costs. Cached evaluation
totals cover 3,900 consumed calls. Composite costs cover the same capped legal
child lists. The full candidate costs about 5.59x as much for cached evaluation,
20.3% more for make/evaluate/unmake, and completed 6.1% less summed depth here.
Depth/node sums include only legal completed replies; failing ablations have
38 replies rather than 39 and are not passed deadline gates. No engine exits
occurred. All measured private-commit peaks stayed below 34.3 MiB, and native
model-plus-table allocations met the 64 MiB ceiling.

## Controlled Screens

| Opponent | Points | Natural wins | Draws | Losses | Opponent timeout wins |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plain schema 7 | 15.5/20 | 12 | 5 | 2 | 1 |
| Frozen Alpha Gen 1 | 1.5/20 | 0 | 1 | 18 | 1 |

Against plain Nu, draws comprise two capped, two repetition, and one natural
draw. Against Gen 1, the sole draw is capped. Every timeout counts as a loss
for the offending engine; neither opponent forfeit was excluded. The candidate
had zero match timeouts. Maximum observed caller elapsed times, including timeout
observation/scheduling delays, were 306.040 ms and 253.507 ms respectively.
All forty games were persisted with no rejected rules/protocol divergence.

The plain screen is promising development evidence, not production qualification.
The Gen 1 points contain no natural win. Its earlier 1.5/20 screen used different
openings and cannot serve as a causal before/after comparison.

## Term Ablations

Every ablation changes only one mask bit. Offline ranking uses 541 retained
validation decisions with each candidate's own geometry and teacher score.
Those decisions are now development-exposed and must not be presented as a fresh
held-out test of future tuning. No ablated model was selected or matched.

| Configuration | Mean teacher regret | Top-choice agreement |
| --- | ---: | ---: |
| Plain | 33.1534 cp | 62.8466% |
| Full | 33.0573 cp | 63.4011% |
| Without neighbors | 32.7689 cp | 63.5860% |
| Without friendly surround | 33.1534 cp | 63.7708% |
| Without Queen control | 33.1608 cp | 63.2163% |
| Without nearby Beetles | 33.3678 cp | 63.2163% |
| Without Queen exits | 33.9150 cp | 62.8466% |
| Without critical liberties | 32.3845 cp | 63.4011% |

Queen exits and nearby Beetles have the clearest favorable *conditional offline*
regret changes: removing them worsens regret by about 0.858 and 0.311 cp.
Removing Queen control worsens it slightly (0.104 cp). Friendly surround gives
mixed evidence: removing it worsens regret slightly but improves agreement.
Removing neighbors or critical-liberty bonuses improves regret, so those are
plausible over-weighting/double-counting suspects rather than demonstrated gains.

Correlation with the existing strategic prior is 0.647 for neighbors, 0.485 for
critical liberties, 0.562 for Queen exits, 0.398 for friendly surround, 0.159 for
Queen control and 0.005 for nearby Beetles. Correlation alone does not prove
harmful double-counting, and these small regret deltas are not match-strength
claims. The full frozen candidate was not adjusted after inspecting ablations.

## Controls And Verification

`HybridTerms` is a six-bit mask: neighbors=1, friendly surround=2, Queen
control=4, nearby Beetles=8, Queen exits=16, critical liberties=32. All terms=63;
zero terms restores plain evaluation. Mode/weight/mask changes isolate table
scores and stop pondering before the next search. Existing checkpoint/prior ABI
and terminal/repetition handling remain unchanged.

Sixteen Nu suites pass, including hybrid correctness, zero-mask behavior,
rotation/reflection, brute-force search, terminal precedence, protocol bounds
and arena resume rejection for changed hybrid settings. Defaults remain disabled.
Further term tuning requires separate fresh confirmation games before promotion.
