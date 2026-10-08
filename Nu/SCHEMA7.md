# Schema 7 Reliability Work

Status: reliability repairs, collection, fresh GPU training, profiling, and all
three development screens completed. The challenger is not promoted. Production
defaults and existing checkpoints remain unchanged; no sealed qualification ran.

## Contract

Schema 7 is opt-in. It uses the schema-5 cheap feature banks and strategic prior
v1 with whole-board D6 frames per color-relative perspective. The Queen anchors
each frame; absent Queens use the lowest relative piece identity. Complete
labeled stack geometry breaks frame ties. Coordinates and directional neighbor
heights are transformed together. Frame/anchor changes invalidate affected
piece descriptors. Reconstruction remains the reference implementation.

No exact legal-mobility generation is used as a neural input. Schemas 1--6 and
the untrained schema-3 default remain available. Old model payloads are unchanged.
Re-encoding supports schema 7; residual training supports schemas 5 and 7 and
starts fresh unless an explicitly matching resume checkpoint is present.

## Verified Repairs

- Shared gauntlet search depth is 64 and is recorded in settings.
- Canonical leakage keys apply to schemas 5, 6, and 7. Opening geometry, parent
  positions, ranking alternatives, and observed children are exposures. Index
  identities include `base-symmetry-opening-v2`; stale identities are rejected.
- `genseki-validate-game` legally reconstructs a replay without changing the
  live rules board. Shared gauntlets compare reconstructed positions and headers.
- Transport command locking, queued writes, flushes, and response reads share a
  deadline. A timeout invalidates the session and signals termination; bounded
  cleanup is separate. Shutdown has no synchronous pipe write.
- Nu arenas require a referee, pin its executable and validation policy, validate
  all three boards, and refuse old reports as resumable new-policy evidence.
  The explicit pinned repetition policy permits Draw/InProgress normalization
  only after Nu detects repetition and the rules service remains nonterminal.
  Replay geometry, type, and turn must still agree. Timeouts remain forfeits.

All fifteen Nu suites and the shared core suite, thirteen transport tests, and
eleven gauntlet tests passed. Schema-7 training interruption/resume produced byte-identical exports
in the CPU regression fixture. Additional teacher-parser tests pass, including
mate diagnostics and equivalent move notation. This is not a loaded-system
performance or strength result.

Both preserved schema-5 and schema-6 incumbents also matched their frozen
executables on 384 feature/score positions and twelve fixed-depth search roots
each, using the combined schema-7-capable executable.
Real post-opening depth-64 requests at 230/250 ms returned legal moves in
222.0 ms (schema 5) and 220.8 ms (schema 6). This single-root protocol smoke is
not a deadline-stress or performance gate.

## Historical Validation Repair

The canonical incumbent's historical corpus/index still used schema-5 names
before the schema collision was resolved; its geometry contract is schema 6.
`rebuild_canonical_index.py` verified native schema-6 parent/child features and
rebuilt it under `Nu/work/canonical-repair-v3`, preserving both original inputs.
The repair retained 383 of 384 samples, removed one, and changed 145 split
assignments. Previous validation metrics are pre-repair evidence, not
leakage-controlled metrics. No historical optimizer state is reused for the new
challenger. The existing incumbent registration and pinned model remain intact.

## Frozen Teacher And Collection

`Gen1Teacher` captures diagnostics from the frozen Gen 1 executable itself
(SHA-256 `80d1cc75571c2e3266e0246b2cec00d3657e3ba94029e5ca4635cfe0eaf12ef6`).
Twelve depth-3 roots matched scores and reconstructed best moves. Separate
copies of that same binary can visit different node counts; counts are recorded,
not asserted equal. Evidence: `Nu/work/schema7-teacher-frozen-v3/parity.json`.

Verbose Gen 1 collapses mate-distance scores to printed infinity. Those targets
retain their printed value and null exact raw score; they are excluded from
nonterminal regression/ranking rather than assigned invented labels.

`collect_schema7.py` implements four-game blocks, depth-8 500-ms parents and
250-ms children, four-ply deterministic openings, 8% exploration, each child's
own prior, and canonical exclusion-manifest checks. A canonical in-memory counter
tracks progress; the completed immutable index must agree exactly. Completed games and per-ply progress are
atomic. Artifacts/settings are pinned; expired named stages cannot restart their
clock. The controller uses both shared locks, Idle priority, RAM/storage guards,
and at most one search thread per active engine.

An isolated interrupted/resumed smoke run completed two games and retained
60 positions. It has no held-out samples yet and uses an empty test exclusion
manifest. It is **not training data** and is not the 10,000-position campaign.
Failure logs from notation and diagnostic parsing are retained separately.

## Completed Campaign

Evidence summary: `Nu/reports/schema7/campaign.json`. Full immutable inputs,
checkpoints, per-game replays, diagnostics, and reports remain under the ignored
`Nu/work/schema7-campaign` directory. The separate smoke corpus was not used.

Collection completed in two bounded stages with 234 games and 10,011 accepted
positions: 7,830 training and 2,181 validation (78.2/21.8%). The immutable index
received 10,315 records before deduplication/cross-split removal. Its audit found
zero reserved-position, reserved-opening-family, child-exposure, or cross-split
exposure hits. Of accepted records, 8,256 have natural game results; 1,576 came
from capped games and 179 from repetition games. Capped/repetition outcomes stay
null; their retained search targets are not invented outcome labels.

Fresh CUDA training used 64-wide linear residual weights, 24 epochs, batch 128,
AdamW, learning rate 0.001, seed 1701, ranking weight 0.05, and held-out MSE
selection. All 1,488 updates completed. Epoch 2 was selected at MSE
0.0414089391; later epochs overfit. Held-out decision regret was 33.183 cp on
541 decisions, with 62.48% top-choice agreement. Peak CUDA allocation was
15,147,520 bytes and peak reserved memory 25,165,824 bytes (24 MiB), below the
1.5 GiB cap. Optimizer/RNG recovery and selected-weight checkpoints are retained.

Selected artifact: `training/nu-64-linear-e2-u1488.nnue`, SHA-256
`9267591529b13283ae94994b71c7bbf85cb9ea056d33c9a4a60c45ced6cfa27e`.
Independent integer inference matched native inference on 400 positions; maximum
floating-to-quantized score difference was 13.254 cp. Legacy schemas 5 and 6
again matched 384 frozen feature/score positions and twelve searches each.

## Benchmark

The accepted report is `Nu/work/schema7-campaign/benchmark-v4/benchmark.json`:
40 identical frozen roots, consumed inference, make/evaluate/unmake, and
1/2/4-thread searches. All three models use the same executable, SHA-256
`f2c4a8ba9a81c5ed13945dabb13712997b0ca7db4c60097c49e3293ed47fe8d1`.
At one thread, all 120 Nu replies were legal with zero timeouts or exits.
Maximum observed private-commit peak was below 34.3 MiB, and native evaluator
plus table allocation stayed below the common 64 MiB ceiling. Gen 1 also met
the measured memory ceiling and returned 40 legal replies with zero timeouts.

| Model | One-thread completed-depth sum | Nodes | Make/evaluate/unmake total |
| --- | ---: | ---: | ---: |
| Fast schema 5 | 120 | 324,856 | 8.2214 ms |
| Canonical schema 6 | 101 | 101,512 | 64.6424 ms |
| Fast canonical schema 7 | 110 | 201,529 | 21.9781 ms |

Totals cover the same roots/child moves; they are not per-move costs. Gen 1's
depth sum was 203. Its profiling enables verbosity to obtain diagnostics;
matches leave verbosity disabled. Schema 7 removes much of schema 6's feature
cost but remains slower than schema 5 on this suite.

Schema 6's two-thread profile had five timeouts. At four threads it had fourteen
timeouts and three Windows heap-corruption exits. These unresolved failures
are retained, not excluded or described as a passed multithreading gate.
Schemas 5 and 7 had no profile timeouts/exits at any tested thread count.
Attempts before v4 are retained but are not accepted comparison evidence:
the first used unsupported `undo 0`; later attempts exposed exits and an invalid
Gen 1 time spelling (`.230` instead of `0.230`). The harness now spells the
budget with a leading zero and preserves missing diagnostics explicitly.

## Development Screens

Artifacts and settings were frozen before matching under `frozen-screen`.
Each opponent used the same ten four-ply openings, mirrored colors, one thread,
16 MiB tables, pondering off, depth 64, 230 ms internal requests, 250 ms external
deadlines, and a 160-ply cap. Nu opponents share the exact executable/search
settings; only their model changes. Every timeout is a loss for its offender.

| Opponent | Points | Wins | Draws | Losses | Capped draws |
| --- | ---: | ---: | ---: | ---: | ---: |
| Schema 5 | 10.5/20 | 6 | 9 | 5 | 8 |
| Schema 6 | 19/20 | 18 | 2 | 0 | 2 |
| Frozen Alpha Gen 1 | 1.5/20 | 1 | 1 | 18 | 1 |

All sixty games completed with no timeouts, repetition adjudications, illegal
moves, or rejected protocol/rules divergence. Maximum observed move times were
245.518 ms, 223.441 ms, and 232.172 ms respectively. The schema-5 screen includes
one natural draw; all other non-capped completed results were decisive.

The challenger beats the canonical incumbent in this development screen but
is far behind Gen 1. It is not qualified or promoted, and these small screens
are not a statistical claim of superiority over schema 5.

## Qualification History Check

Reachable Git history, both `archive` and `origin/archive`, and local Nu/Alpha
work evidence contained no frozen Nokamute qualification manifest. Archive
contains historical tournament seeds and a superseded Mzinga qualification
document, neither of which is this gate. `qualify.py` first appeared in
`2381962`; it generates final seeds only after development gates pass. This
does not prove that no external or deleted ignored file ever existed. There is
no recovered historical qualification set to exclude.

A fresh immutable reservation now holds fifty distinct canonical qualification
opening families privately, ten disjoint public development openings, and 21
tactical/reference position keys. Public key-only evidence is
`Nu/reports/schema7/qualification-exclusions.json`; private seeds/replays stay
ignored in `Nu/work/schema7-campaign/openings/sealed-qualification-openings.json`.
No sealed game ran. Development openings were checked against both incumbents'
parent and ranking-child exposures. Schema-7 qualification requires the frozen
manifest; development results do not authorize that attempt.
