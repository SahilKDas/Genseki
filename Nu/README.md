# Nu

Independent C++ NNUE Base-Hive engine. Nu links the shared rules implementation,
not Alpha's search or evaluation. Iota and Rho are outside this implementation.

## Build and Run

```powershell
cmake -S Nu -B build-nu -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-nu -j 2
ctest --test-dir build-nu --output-on-failure
build-nu/nu.exe --model Nu/work/models/nu-64.nnue
build-nu/nu.exe perft 3
build-nu/nu.exe perft 3 --divide
build-nu/nu.exe stress 20
build-nu/nu.exe replay moves.txt
```

Without `--model`, the engine uses deterministic **untrained** weights, not a
handcrafted fallback. Never treat that configuration as a trained engine.

UHP supports `newgame`, `play`, `undo`, `validmoves`, `bestmove`, `info`, `options`,
and `exit`. Replay files contain one UHP move per line. Options include `Threads` (1..12), `TableMiB` (1..256),
`BackgroundPondering` (default False), `ThreatPlies` (0..4, default 0),
`LateMoveReductions` (default False), and `Profile` (default False). Both `options set NAME VALUE` and the
short form are accepted. Debug commands: `nu-position`, `nu-features`, and
`nu-searchinfo`, `nu-profile`, `nu-moveid`, and `nu-matchdraw`. This is not yet a claim of full UHP conformance.

Search challengers additionally expose opt-in `DeadlineGuard` and
`CooperativeOrdering` (both default False), with `nu-timing` reporting setup,
worker joins, total search time, cleanup lag, and reply-format cost. These are
search policies over the unchanged schema-8 weights, not new feature schemas.
Research generations called Schema 9/10 must qualify separately; adding these
options does not itself promote an incumbent or change GUI/Alpha defaults.
The qualified Schema 9 profile scored 15.5/20 against frozen Schema 8 and 1/20
against Alpha Gen 1. See [SCHEMA9.md](SCHEMA9.md) for the selected configuration,
retained failures, and research-only promotion limits.

## Models and Features

Opt-in schema 7 combines the inexpensive schema-5 residual feature banks with
schema-6 D6 frames, including directional masks. See [SCHEMA7.md](SCHEMA7.md)
for verified repairs, historical validation limitations, and outstanding gates.

Opt-in schema 8 retains schema 7's exact feature/score contract with fixed-capacity
feature construction, reusable worker snapshots, block-level accumulator updates,
and collision-verified compact cache identities. Schema-8 models default to eight
search threads; schemas 1--7 keep their existing defaults. See [SCHEMA8.md](SCHEMA8.md)
for checkpoint conversion provenance, parity tests, and measured performance.

8192 x 64 and 8192 x 128 feature transformers, clipped-ReLU,
paired queen-relative perspectives, and either a linear or nonlinear head. Every stone includes
identity, relative ownership, coordinates, stack level and top/covered state.
Coordinates are hashed without cropping; **hash collisions are intentional**.
Schema 1 remains supported for existing trained artifacts. Experimental schema 2
partitions the bank into identity features, shared piece-type features and
top-stone occupancy. Occupancy within radius two of each queen is indexed
directly; distant coordinates remain hashed. Schema-2 positions have up to 66
active features per perspective. Missing queens use the origin.
Schema 3 adds articulation, local gate-access proxies and Queen liberties.
Schema 4 adds actual legal movement-destination counts, including Queen escape
counts, and Queen stack-control flags. Mobility saturates at 15 destinations;
it is not a count of paths, placements or speculative future mobility.
Opt-in schema 6 retains schema-4 feature banks but
canonicalizes the entire labeled board over all six rotations and six reflected
rotations, independently for each color-relative perspective. Queen anchors are
retained; before a Queen is placed, the lowest perspective-relative piece identity
anchors the board instead of the origin. Thus translated, rotated and reflected
boards have identical feature multisets and integer evaluations, including stacks.
Canonical coordinates use full-width integers before hashing. This normalizes
evaluation inputs only: move coordinates, repetition keys and TT keys are unchanged.

Schemas 1--4 keep their original orientation-dependent semantics. Existing weights
are never relabeled as schema 6: reconstruct every corpus position and child with
`refeature.py --schema 6` using the newly built engine, then train a separately named
schema-6 model. Do not mix schemas or resume a schema-4 optimizer as schema 6.
No trained weights or strength promotion are supplied by this rules-level change.
Schema 5 is reserved for the original checkout's distinct fast/residual contract;
the combined engine supports both contracts without interchanging them. The historically tested private schema-5 weights were
renumbered to 6 with exact payload, feature, inference and fixed-depth parity.
The explicit user-promoted 64-wide incumbent is registered as an engine/model
pair in `incumbents/64-linear.json`; launch it with `tools/incumbent.py`.
Alpha's separate Rust adapter still supports its existing schemas, not schema 6.
The collector CLI defaults to `--feature-schema 6`; use `--feature-schema 4`
explicitly when continuing old schema-4 collection manifests. Existing programmatic
campaign callers without that option retain schema 4 to protect resume identities.
The shared rules library uses signed 16-bit axial
coordinates; Nu does not claim mathematically unbounded coordinates.

Accumulator updates use sorted multiset differences, including queen-anchor
changes; schema 8 updates changed piece blocks and Queen globals directly.
Integer scale is 256. SIMD output dispatch requires SSE4.1 and has a
scalar fallback. Files use a 32-byte little-endian header: magic `NUNNUE1\0`,
schema, feature count, width, quantization scale, FNV-1a payload checksum.
Payload: int32 biases, int16 embeddings, int16 output weights. `NUNNUE2\0`
retains the header and adds a fixed 32-unit head: row-major int16 weights
(32 x twice the transformer width), int32 biases, then 32 int16 output weights.
Its score is half the difference between the same clipped head applied to the
paired accumulators and to their swapped order, preserving antisymmetry.
Old model formats and feature schemas remain supported. This checksum
detects corruption; artifact SHA-256 identifies experiments.

## Search

Full-width iterative deepening; single-thread root PVS and interior PVS,
aspiration re-searches, per-worker killer/history/countermove ordering retained
across depths with bounded aging, a four-entry bucket TT with depth/age replacement
and striped locks, terminal mate-distance scores,
search-local repetition handling, legal fallback, completed-depth retention,
and up to 12 root workers. No late-ply evaluator replacement, sampled children,
or enabled-by-default selective pruning. Optional threat search checks actual
winning replies and mandatory defenses. Experimental LMR excludes tactical,
forced and PV-node moves and re-searches improving reduced moves at full depth.
Both experiments require their own timing and strength evidence before adoption.
Pondering lasts at most one second and is cancelled/joined before a foreground
command. Nu's separate rules build checks cancellation inside generation loops;
this improves interruption but is **not a hard real-time guarantee**.
PV may be shortened by TT hits. Conservative history-sensitive TT keys reduce
transposition reuse, but their rolling history component is now O(1). Piece
hashes update incrementally; features still refresh before accumulator deltas.
Legal-move caches restore on undo; per-ply ordering/PV buffers are reused.
Schema-4/6 mobility counts update incrementally for occupied-stack Beetle moves:
ground geometry is unchanged, so only exposed/covered pieces and Beetles refresh.
Other moves rebuild mobility; full recomputation remains the integrity reference.
Profiling reports feature, generation, ordering and TT-probe time separately.
Search applies only engine-generated moves through the trusted rules API;
protocol input continues through checked application. The trusted API's exact
position/legal-generation precondition must never be used for external input.

## Train and Measure

```powershell
python Nu/tools/train.py --games 20 --cap 120 --epochs 8
python Nu/tools/verify_model.py Nu/work/models/nu-64.nnue
python Nu/tools/arena.py --model Nu/work/models/nu-64.nnue --opponent PATH_TO_NOKAMUTE --games 20 --output Nu/work/development.json
python Nu/tools/expert.py --engine build-nu/nu.exe --expert PATH_TO_NOKAMUTE --output Nu/work/expert.jsonl --games 60
python Nu/tools/train.py --data Nu/work/expert.jsonl --output Nu/work/expert-models --epochs 24
```

Training uses bounded minibatches (default 128), identical updates for both
architectures, CUDA allocator ceiling 1.5 GiB, RAM-reserve checks, and game-level
validation splits. Natural outcomes and search targets remain separate fields.
Capped games have null outcomes, not invented draw labels. Bootstrap search
targets originate from untrained Nu, so they are weak supervision, not evidence
of strong Hive play. `--source-model` generates subsequent corpora from a trained
Nu model; use a new `--data` path to avoid reusing the old corpus accidentally.
Training selects the best held-out target-MSE epoch. Expert corpora can include
legal child preferences and real outcomes, not copied heuristic evaluations.
`refeature.py` preserves outcomes and game splits; it drops old preferences
unless their child coordinates were retained. Such a run is an outcome-only
ablation, not a fair isolated architecture comparison. Neither held-out MSE nor
training loss is a substitute for playing-strength evidence.
When `--evaluator` is supplied to `expert.py`, it records pinned expert static
scores (scaled by four into Nu units). Targets blend 90% bounded expert score
with 10% natural outcome; capped/adjudicated games use the score alone. This is
explicit teacher distillation, not an independent architecture-strength study.
The optional adapter compiles upstream modules only for data generation:

```powershell
git clone http._//github.com/edre/nokamute.git .tmp/nu-nokamute
git -C .tmp/nu-nokamute checkout c9ab65e0d9f496fd8735096ae37babc8bb50a57c
cargo build --release --locked -j 2 --manifest-path Nu/tools/teacher/Cargo.toml --target-dir .tmp/nu-teacher-build
```

See `tools/teacher/NOTICE.md` for the license. Nu's runtime does not link this
code. Expert repetition adjudications are recorded with null outcomes; unexplained
rules divergences abort collection and save evidence. Qualification still rejects
rules divergence rather than silently changing the core's draw rules.
The bounded loader rejects existing corpora over 256 MiB rather than scaling a
GPU batch to the corpus size. Generated artifacts live in ignored `Nu/work/`.

## Strength Campaign

The new pipeline streams per-game corpus shards through a bounded SQLite index.
Opening families stay together; transpositions crossing splits are removed,
including positions exposed by ranking children. Duplicate positions are
deduplicated. Every architecture uses the same split, minibatch order, seed,
epochs and optimizer-update budget. Checkpoints preserve optimizer, random
states, corpus identity and the next unprocessed batch; configuration mismatches
reject resume. Batch 128 is the default; bounded gradient accumulation is optional.

```powershell
python Nu/tests/learning.py
python Nu/tools/collect.py --engine build-nu/nu.exe --teacher .tmp/nu-teacher-build/release/nu_offline_teacher.exe --directory Nu/work/campaign/corpus --positions 20000
python Nu/tools/learning.py --data Nu/work/campaign/corpus --index Nu/work/campaign/positions.sqlite --output Nu/work/campaign/models --epochs 24
python Nu/tools/benchmark.py --engine build-nu/nu.exe --model Nu/work/campaign/models/nu-64-linear.nnue --output Nu/work/campaign/timing.json
python Nu/tools/campaign.py --incumbent Nu/work/models-v5/nu-64.nnue --directory Nu/work/staged-campaign
```

`collect.py` uses pinned offline search scores and multiple scored legal children;
static scores remain separately recorded for comparison. Optional Nu self-play
provides one quarter of the games. Capped and repetition-adjudicated games have
null outcome labels. Outcome-only fine-tuning requires a trained initialization
and at least 500 naturally finished training games plus 100 validation games.
The staged controller targets 10,000, 50,000 and 200,000 accepted positions;
bounded collection/training slices return with recoverable progress when unfinished.
Run the same command to continue. These capabilities are not claims that all
three stages or every ablation have already been run.

`--ablate` removes a named feature-bank group while keeping architecture and
update budgets constant. Related information can still exist in other groups;
these are bank-group ablations, not claims of removing a concept everywhere.

Match-level repetition uses the pinned Nokamute 1.0.3 policy: after more than ten
plies, compare the current bug/color/height position against 4, 8, ..., 32 plies
earlier; two previous matches adjudicate a draw. Core vanilla results are unchanged.
Reports distinguish natural results, repetition, ply caps and timed forfeits.
Unexpected results and protocol failures reject a run and atomically save its
attempted move sequence and position. The original rejected 128-wide gauntlet
predated this capture support; its missing failing-game replay cannot be recovered.

`qualify.py` requires >55% in at least 100 confirmation games and at least 50%
in a 20-game incumbent match, with matching
artifact hashes/configuration before generating final seeds. It consumes a
one-shot attempt marker, runs 50 mirrored opening pairs at 250 ms and a 160-ply
cap, and promotes only scores strictly above 55/100. Protocol/rules divergence
aborts. Qualification remains intentionally unrun after weak development
results. The generated seeds are distinct from development seeds but are not
cryptographically hidden from an operator with filesystem access.

See COMBINED_INTEGRATION.md for the reconciled schema-5/schema-6 implementation,
verified compatibility, backup locations and commit-review scope.
See STATUS.md for measured evidence and remaining work. Device constraints in
the root constraints file remain binding.

## Independent Handcrafted + NNUE Candidate

Enable the opt-in candidate with `options set HybridEvaluation True`; tune its
percentage with `options set HybridWeight 100` (0--200). Default is disabled.
Search combines the existing checkpoint evaluation with independently written
position weights: enemy Queen neighbors (18), friendly surrounding tops (12),
enemy Queen stack control (90), adjacent friendly Beetles (14), own Queen local
open gates (4), and enemy Queen at one/two liberties (140/50).
These weights favor the resulting positions of moves, not bonuses accumulated
per ply. Full-width search still chooses the move; terminal/repetition results
override heuristic scores. No new Nokamute code, weights, calls, or training
data are used for this candidate. Existing schema-5/7 trained prior v1 remains
unchanged inside the base evaluation; this is a separate optional addition.

`nu-hybrid-eval` reports base, handcrafted, and combined side-to-move scores and
the heuristic version. Mode/weight changes stop pondering and invalidate search
table scores before reuse. Checkpoints, feature schemas and defaults are intact.
The added weights are unqualified; no strength improvement is claimed.
Verification: sixteen Nu suites pass, including symmetry, zero-weight/default
parity, score orientation, table isolation, brute-force depth-two comparison,
make/unmake, and terminal-win precedence. The frozen trained schema-7 model
matched the previous executable on twelve fixed-depth roots with the mode off;
with it enabled, twelve legal 230/250-ms replies had no timeouts (maximum
220.773 ms). Evidence: `Nu/work/hybrid-v1/verification.json`.
Subsequent controlled screens scored 15.5/20 against plain schema 7 and 1.5/20
against frozen Alpha Gen 1, including one opponent timeout win in each screen.
No natural Gen 1 win occurred. See HYBRID_STUDY.md for cost, depth, term ablations,
forfeits, capped results and limitations. The mode remains opt-in; no retraining
or promotion was performed.
