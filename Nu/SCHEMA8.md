# Schema 8: Bounded Schema-7 Runtime

Schema 8 is an opt-in runtime successor, not a new trained network or new feature
semantics. It preserves schema 7's sorted feature multisets, prior v1, integer
score scale, and search policy. Loaded schema-8 models default to **eight CPU
search threads**. Other schemas retain their old defaults; the untrained schema-3
configuration, GUI engine selection, Alpha, and incumbent registry are unchanged.
Threads remain configurable from 1 to 12 for controlled measurements.

## Implementation

- Fixed arrays cover 22 pieces/cells, 22 entries per canonical candidate, six
  features per piece/perspective, and 134 total features per perspective.
- Canonical D6 keys are traversed in unique relative-identity order. This removes
  twelve vector constructions and sorts per perspective without changing frame
  selection or ties. Direction permutations are computed at compile time.
- Per-piece encodings, occupied geometry, and articulation flags use bounded
  storage. Full feature construction performs no heap allocations on tested roots.
- Each search lane owns scratch space and a pool of 128 reusable immutable
  snapshots. Referenced ancestors are never overwritten. Exhaustion uses a safe
  allocating fallback rather than corrupting retained state. Pools are destroyed
  only after workers join, not through thread-local object teardown.
- Only changed descriptor blocks and changed Queen-global features add/remove
  transformer rows. Schema-8 undo retains snapshots instead of copying two active
  feature vectors. Full reconstruction remains the independent reference.
- SSE4.1 adds/removes four sign-extended int16 weights into int32 accumulators.
  Runtime dispatch has a scalar fallback. Accepted biases are bounded by 1,000,000
  and at most 134 active features keep intermediate sums far inside int32 range.
  Existing scalar/SIMD output scoring remains unchanged.
- Legacy feature caches use a 256-slot direct-mapped table instead of serialized
  strings. Full labeled coordinates/layers, schema, side, and ply verify each hash
  hit. Evaluation inputs do not depend on omitted replay history or turn counters.
  Forced equal-hash tests verify that differing identities cannot reuse entries.
  Schemas 5/7/8 bypass this cache; schema 8 uses its separate worker scratch/pool.

The board's owning vectors and diagnostic output vectors still exist. This is
not a claim that the entire engine is allocation-free. CPU-only changes add no
GPU memory use, and existing device limits remain binding.

## Checkpoint Lineage

The trained 64-wide schema-7 source has SHA-256:

`9267591529b13283ae94994b71c7bbf85cb9ea056d33c9a4a60c45ced6cfa27e`

Its explicitly converted schema-8 artifact has SHA-256:

`78f265a5a96ee5994e2e5743817a2017fcbc7dc1d4d2c8fc5661d0584ed1d875`

Only the header's schema field changes. Payload bytes/checksum and all trained
weights remain identical; the original file is preserved. Conversion requires
the source SHA-256, validates dimensions/checksum/bias bounds, refuses overwrite,
and writes a provenance sidecar. It does not relabel optimizer states or validation
metrics, retrain weights, or promote a champion. Both linear/nonlinear formats
and widths 64/128 are supported; measured trained results below use linear/64.

```powershell
python Nu/tools/schema8_model.py --source SOURCE7 --output MODEL8 --source-sha256 SOURCE_SHA256
build-nu/nu.exe --model MODEL8
# UHP options get Threads reports Threads;int;8;8;1;12.
```

The locally converted model is under ignored `work/schema8-v1/model.nnue`.
Existing checkpoints/indexes stay immutable. Residual training, re-encoding,
canonical leakage exclusions, and qualification-opening protections explicitly
recognize schema 8, but no new training or qualification was launched.

## Verified Evidence

All 18 Nu CTest suites passed, including schema-8 eager/lazy make/unmake, scalar
and SIMD parity at extreme int16 weights/bounded biases, nonlinear heads, stacks,
covered pieces, anchor/frame changes, D6 symmetry/translation, passes, pool reuse,
copy isolation, forced cache collisions, artifact corruption/overwrite rejection,
residual-training resume, and parallel search checks.

`reports/schema8-v1/parity-final.json` records 462 trained-model positions and
54 fixed-depth searches. Features, priors, scores, nodes, moves, and PVs matched
schema 7 exactly. A separately implemented Python integer calculation also
matched native inference. Binary inspection verified `pmovsxwd`, `paddd`, and
`psubd` in the schema-8 row-update routine; SIMD correctness is established by
the arithmetic bounds and differential tests, not instruction presence alone.

## Performance

Authoritative barrier-equipped measurements:
`reports/schema8-v1/benchmark-checked.json`. Binary/model hashes are recorded;
local frozen artifacts remain under ignored `work/schema8-v1/benchmark-checked`.
Prior trial reports are retained separately, not overwritten.

Component measurements consume outputs into a checksum and use compiler memory
barriers between 200 iterations per root. Ordinary-new allocation requests are
not peak live memory and do not count aligned allocations. These are exploratory
microbenchmarks, not a whole-search speedup estimate:

| Root | Schema-7 Features (us) | Schema-8 Features (us) | Feature Allocations 7 / 8 | Make/Evaluate/Unmake 7 / 8 (us) |
| --- | ---: | ---: | --- | --- |
| Opening | 0.51 | 0.03 | 4 / 0 | 3.78 / 1.42 |
| Middlegame | 22.32 | 3.23 | 254 / 0 | 31.56 / 12.21 |
| Stacked | 5.55 | 1.14 | 119 / 0 | 15.78 / 3.03 |
| Tactical | 27.19 | 4.95 | 349 / 0 | 30.25 / 6.44 |

Forward integer inference itself did not demonstrate a meaningful speed change;
the improvement comes from feature/transformer updates and allocation removal.

Alternating UHP comparisons use the same executable, payload-equivalent models,
four categorized roots, three repeats, pondering off, unchanged selective-search
settings, 16 MiB tables, depth ceiling 64, 230 ms internal requests, and 250 ms
external deadlines. Each row below covers 12 requests:

| Schema | Threads | Completed Depth Sum | Nodes | Timeouts |
| --- | ---: | ---: | ---: | ---: |
| 7 | 1 | 37 | 69,509 | 0 |
| 8 | 1 | 39 | 142,084 | 0 |
| 7 | 8 | 37 | 209,649 | 0 |
| 8 | 8 | 39 | 442,191 | 0 |

At eight threads, this run measured 2.11x nodes and two additional summed completed
depths, not two extra plies per move. The preceding final-runtime run measured
39 versus 44 summed depths and approximately 1.97x nodes. The varying depth totals
are reported rather than selecting the best run. Effective workers are capped by
legal root-move count, so opening roots cannot always use eight workers.

All 48 paired replies were legal and within deadline; maximum latency was below
223 ms. Peak working sets were approximately 39.3 MiB and peak process commit
approximately 34.3 MiB, below the common 64 MiB ceiling. These small development
measurements do not establish playing strength or qualify a production promotion.

## Reproduction

Build `nu`, `nu_schema7_baseline`, and all tests in Release mode. The verification
and benchmark controllers use both shared heavy-job locks, Idle priority, a
two-hour stage cap, RAM-floor checks, bounded subprocess waits, and immutable
output paths:

```powershell
python Nu/tools/schema8_verify.py --engine ENGINE --schema7 MODEL7 --schema8 MODEL8 --report NEW_PARITY_REPORT
python Nu/tools/schema8_benchmark.py --engine ENGINE --benchmark COMPONENTS --schema7 MODEL7 --schema8 MODEL8 --directory NEW_LOCAL_FREEZE --report NEW_PUBLIC_REPORT
```

No strength gauntlet, sealed qualification, commit, or push was performed.
