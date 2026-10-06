# Alpha Gen 2 development

Gen 1 remains the production default. Neither neural candidate is promoted.
The GUI's default engine and sealed qualification have not been changed.
No Iota content was read or used.

## Native evaluator interface

The MIT backend now wraps its existing `BasicEvaluator` in `SelectedEvaluator`.
Gen 1 delegates evaluation and noisy-move generation to the original evaluator.
Neural mode replaces leaf scores only; pruning, ordering, quiescence, openings,
and terminal handling are unchanged. No move sampling or late heuristic switch
is introduced.

Start the isolated backend with `--evaluator neural --model PATH`, or use UHP:

```text
options set ModelPath PATH
options set Evaluator neural
options set Evaluator gen1
```

Paths containing spaces work through `ModelPath`. Each model needs an adjacent
`PATH.alpha.json` containing `trained: true`, its SHA-256, and a positive finite
`score_scale`. The staged tooling verifies training evidence before admitting
Nu artifacts. The sidecar is provenance metadata, not a cryptographic proof
that arbitrary user-supplied weights were trained.

Bad checksums, dimensions, schemas, biases, score scales, and untrained sidecars
are rejected without fallback. Neural games and neural diagnostics support Base
only. Gen 1 retains existing variant behavior, including previously documented
expansion limitations. Evaluator/model changes drop the old player, cancel its
pondering, replay the board, and construct new search state and tables.

`alpha-neural` reports exact sorted features, integer output, SHA-256, schema,
score scale, model bytes, and requested TT bytes. `alpha-eval` reports the
selected score. Neural scores are clamped outside the reserved mate range.
`alpha-search DEPTH [MILLISECONDS]` is a bounded, single-worker diagnostic
search reporting score, PV, nodes, and completed depth; it is not substituted
for production `bestmove` during matches.

Accumulator vectors and previous feature multisets are worker-local. Their
updates handle duplicate features, model changes, and undo. Full reconstruction
remains the reference. Feature extraction itself is still reconstructed: this
is not yet a fully incremental mobility/geometry implementation.

## Reproducibility and stages

`Alpha/tools/gen2.py` provides prepare, parity, schemas, collect, train, calibrate,
benchmark, and arena stages. Every requested stage is at most 7,200 seconds.
Use `--stage-id NAME` to retain an absolute deadline across interrupted resumes;
resuming does not reset that deadline. A separately named stage can continue a
campaign after the earlier stage expires. A workspace OS lock prevents duplicate
Alpha stages. Heavy-job preflight refuses competing training/arena work.

The original Gen 1 executable is hash-pinned in `reports/gen2/gen1.json`.
Frozen development-search binaries/source hashes are in `reports/gen2/search-pins`.
Copied models, calibrated candidate copies, optimizer/RNG checkpoints, replay
data, and runtime sources live in ignored `Alpha/work/gen2/`. The original Nu
trainer is pinned from the Gen 1 source revision, independently of subsequent
Nu edits. Do not delete that workspace when resuming a campaign.

Each new corpus namespace snapshots its teacher executable before collection.
The initial bootstrap corpus predates this safeguard: its seven completed games
and exact teacher scores/hash are retained, but its intermediate teacher
executable was replaced. To grow data with the finalized diagnostic depth/time
controls, use a new `--corpus NAME`; the tool will not mix teacher identities.

Examples, from the repository root:

```powershell
cargo build --release --manifest-path Alpha/vendor/nokamute/Cargo.toml --target-dir Alpha/build/gen2-target
py -3.11 Alpha/tools/gen2.py prepare
py -3.11 Alpha/tools/gen2.py collect --corpus gen1-v2 --games 20 --seconds 600 --stage-id corpus-v2-1
py -3.11 Alpha/tools/gen2.py train --corpus gen1-v2 --seconds 600 --stage-id training-v2-1
py -3.11 Alpha/tools/gen2.py arena --model PATH --name candidate-vs-gen1 --games 20 --seconds 600 --stage-id screen-1
```

Training splits by source game/opening family and removes cross-split
transpositions. Search targets and natural outcomes are recorded separately;
capped/repetition-adjudicated games receive no invented outcome. Calibration
excludes held-out opening groups and mate scores. Existing tactical/performance
fixtures are checked against the indexed training and validation samples.
Development seed namespaces are used; sealed openings were not accessed.

Training uses bounded minibatches, resumable optimizer state, and the 1.5 GiB
CUDA allocator cap. Stages use Idle priority, one heavy job, available-RAM and
storage checks. The stage RAM floor is conservatively 2 GiB; the binding device
minimum remains 0.5 GiB. Temporary-size checks enumerate explicitly named roots,
never Iota. They are not a measurement of excluded Iota storage.

## Comparison and gates

Screens use ten deterministic opening seeds mirrored into twenty games, one
search worker per engine, 230 ms requests, strict 250 ms response deadlines,
32 MiB evaluator-plus-TT ceilings, and 160-ply caps. The pinned Nokamute 1.0.3
revision/executable/options are in `reports/gen2/nokamute-pin.json`.
Its accepted common command is `bestmove seconds 0.230`.

Gen 1 uses a 32 MiB TT. The 64-wide neural artifacts occupy 1,048,992 bytes;
their TTs are reduced to 16 MiB plus a 256 KiB model/cache bookkeeping reserve.
This reflects the inherited power-of-two TT allocator, not equal actual TT
sizes. Diagnostics report sizes; they are not total-process RSS measurements.

Each completed arena game is atomically persisted. Resumes require matching
binaries, models, calibration sidecars, settings, and opening manifests.
Protocol/rules failures invalidate a run; resource-floor stops preserve completed
games for resume. Timeouts and illegal moves score zero. PV is recorded where
the pinned UHP implementation exposes it. Per-move node/completed-depth telemetry
is not exposed by those production UHP servers and remains null in arena records;
separate bounded diagnostic searches measure it before matches.

Both clean 20-game screens must score strictly above 50% before 100-game
development is allowed. Larger development uses a different seed namespace.
Resource-contaminated screens cannot advance. Nothing promotes automatically:
more than 55/100 against Gen 1 and explicit authorization for the existing sealed
Nokamute gate remain necessary. This tool has no sealed-qualification mode.

## Verified evidence so far

Latest Nu training sources are pinned from the working tree in
`reports/gen2/trainer-latest-pin.json`, including the ranking audit tool.
The earlier Git-snapshot runtime and checkpoints remain preserved. A changed
Nu source pin is rejected rather than silently mixed into a resumed stage.
Parity reports now record the Nu reference executable checksum as well.
The latest reliability-v8 128-wide nonlinear checkpoint is separately frozen
in `reports/gen2/nu-latest.json` (model SHA-256 starts `2cb26dd0e360`). Its native
adapter matched current Nu exactly on 320 positions and 46 undo checks. This
checkpoint is a bounded partial-training export, not a promoted champion; its
adapter was calibrated on 249 training-split development positions to scale
0.1779741166522808. Cross-split transpositions, validation rows and tactical
fixtures were excluded. Calibration RMSE was 30.14 Gen 1 units (250.85 before
scaling); this is a scale fit, not held-out strength evidence. The calibration
and model are frozen together by checksum. Fourteen preflight replies were
legal and within 250 ms (maximum 230.41 ms); loaded-system guarantees remain
unverified. The fresh mirrored development screens use the repaired search.
Gen 1 is Nokamute-derived: its screen and the pinned Nokamute screen are related
baseline checks, not independent evidence against distinct engine families.

The screens below predate the identity-sensitive neural transposition-key
repair. They are historical integration experiments, not advancement evidence
for the repaired search. Gen 1's identity-independent keys remain unchanged.

- Native Rust suite: 29 tests passed, including identity-sensitive neural TT keys.
- Python suite: eight tests passed, including frozen Gen 1 fixed-depth root
  scores, rejection, two-worker pondering/model switching, tactical exclusions,
  mirrored completed openings, and immutable stage deadlines.
- Each selected schema-4 linear model matched Nu on 320 legal positions and
  46 undo checks. Nu's diagnostic cache is explicitly refreshed before comparing.
- Bootstrap training: seven natural games, 406 score/outcome records; after
  grouped/transposition filtering, 271 training and 113 validation positions.
  Twelve epochs/36 updates; validation selected epoch 1. Peak allocated CUDA
  memory was 12,464,128 bytes. This is a small integration experiment.
- Nu adapter versus Gen 1: 1.5/20, no timeout-decided games.
- Nu adapter versus Nokamute: 2/20, including two capped draws.
- Alpha-trained bootstrap versus Gen 1: 0/20.
- Trained versus Nokamute: paused after 18 games at 7 points, all points from
  opponent timeouts; eight games were timeout-decided. Concurrent Nu training
  and a RAM-floor stop were observed. It is not clean strength evidence.

These results reject promotion of both candidates. They do not prove that
neural evaluation is inherently worse than Gen 1's evaluator. Fully incremental
feature maintenance, broader training data, explicit forced-pass/terminal
neural fixtures, exhaustive schema/head differential checks, loaded-system
deadline validation, and interruption/recovery coverage remain research work.
