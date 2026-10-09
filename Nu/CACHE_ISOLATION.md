# Schema 7 Baseline And Worker Cache Isolation

## Scope

Freeze and profile plain schema 7, then remove serialized-feature-cache copying
without changing features, weights, strategic prior, or search policy. No model
promotion, GUI/default change, training, or strength match was performed.

The baseline engine, allocation-instrumented benchmark, and trained 64-wide model
were copied into an immutable local experiment directory before the ownership
change. The model SHA-256 is
`9267591529b13283ae94994b71c7bbf85cb9ea056d33c9a4a60c45ced6cfa27e`.
Full path-free evidence and binary hashes are in
`reports/cache-isolation-v1/results.json`. Local binary copies and raw evidence
remain under ignored `work/cache-isolation-v1`; they are not distributable defaults.
Build: GCC 14.1.0, Release `-O3 -DNDEBUG`, C++26 mode.

## Ownership Change

Previously, `State` contained an unordered feature cache by value. Search copied
the root state into every worker at each iterative-deepening depth, copying any
populated cache along with the position.

Search now owns one `FeatureCache` per lane for the duration of a search request.
Each cache is capped at 256 entries and reused between depths. A worker borrows
only its own lane's cache. State copy/move operations discard the binding, so
positions copy neither cache entries nor shared mutable ownership. Search joins
all workers before destroying their caches. No cache uses thread-local storage.
Unbound states reconstruct features directly; cache keys still include the schema
and complete serialized position rather than relying on unchecked hashes.

Crucially, schemas 5 and 7 return through the fast-feature path before consulting
this cache. Schema 7's cache was empty: this fixes ownership/copying overhead,
especially for legacy schemas, but does not remove its main evaluation cost.

## Measurements

Native component tests consume every feature bank, prior, inference result,
generated move list, and search result in an emitted checksum. Allocation counters
measure ordinary C++ allocation requests, not live memory, aligned allocations,
or total process memory. Timed searches also record nodes, completed depth, and
feature/inference/generation times. Separate UHP measurements include transport
and process working-set/commit observations.

Exploratory baseline averages, nanoseconds per operation over 200 iterations:

| Root | Full Fast Features | Integer Inference | Board Copy | Move Generation | Feature Allocations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Opening | 576 | 42 | 23 | 580 | 4 |
| Middlegame | 45,470 | 67 | 1,534 | 39,769 | 254 |
| Stacked | 14,376 | 67 | 366 | 9,334 | 119 |
| Tactical | 54,323 | 68 | 2,027 | 68,293 | 349 |

These full reconstructions are not identical to every incremental leaf refresh.
Do not interpret their cost as a measured share of total search time.

Paired UHP requests alternate frozen baseline/candidate execution order, with
four categorized roots, three repeats, 16 MiB tables, depth ceiling 64, 230 ms
internal requests, and 250 ms external deadlines:

| Threads | Baseline Depth Sum | Candidate Depth Sum | Baseline Nodes | Candidate Nodes | Timeouts |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 39 | 39 | 119,360 | 117,043 | 0 / 0 |
| 2 | 36 | 36 | 214,264 | 212,783 | 0 / 0 |
| 4 | 38 | 39 | 299,035 | 299,868 | 0 / 0 |

All 72 paired replies were legal; maximum latency was below 221 ms. Observed
peak working sets were approximately 39.3 MiB for both binaries, with peak
committed memory approximately 34.3 MiB, below the 64 MiB common ceiling.
Separate ordinary UHP runs on six legal seeded roots also had no timeouts, but depth sums
were 180 baseline versus 169 candidate. Instrumented native runs summed to 111
versus 109. Taken together, these small runs establish no meaningful schema-7
depth improvement. Parallel search was not consistently better than one thread.

## Verification And Next Target

### Additional Thread Sweep

The later requested 3/8/9/10/11/12-thread sweep repeated one thread as a fresh
control. Each lane/count has 12 requests (four roots, three repeats):

| Requested Threads | Baseline Depth Sum | Candidate Depth Sum | Candidate Versus 1 Thread | Candidate Timeouts |
| --- | ---: | ---: | ---: | ---: |
| 1 | 35 | 34 | 0 | 0 |
| 3 | 35 | 32 | -2 | 1 |
| 8 | 36 | 37 | +3 | 0 |
| 9 | 35 | 35 | +1 | 0 |
| 10 | 35 | 36 | +2 | 0 |
| 11 | 37 | 33 | -1 | 0 |
| 12 | 32 | 32 | -2 | 0 |

Evidence: `reports/cache-isolation-v1/high-thread-paired.json`. These are summed
depths, not extra plies on every root. Search limits effective worker count to
the number of legal root moves, so a four-move opening cannot use twelve workers.
Eight threads scored highest for the candidate in this small sweep; this does
not qualify it as the universal best setting or justify a default change.

Free RAM dropped below the binding 0.5 GiB reserve during this run. The controller
stopped, saved its completed prefix, and resumed after RAM recovered to about
2.9 GiB. The frozen artifacts and settings were verified; completed requests,
including the candidate's 3-thread timeout (approximately 252.8 ms), were retained
and not rerun. Original stop evidence remains locally preserved. The result spans
different resource conditions, so it is an exploratory scaling measurement,
not a controlled proof that the cache change improves strength or throughput.

### Repeat With Available RAM

At the user's request, a fresh sweep started with approximately 5.9 GiB free
RAM and completed without a resource-floor stop. Previous evidence was retained.
Same binaries, model, roots, settings, and three repeats were used:

| Requested Threads | Baseline Depth Sum | Candidate Depth Sum | Baseline / Candidate Timeouts |
| --- | ---: | ---: | --- |
| 1 | 34 | 38 | 1 / 0 |
| 3 | 35 | 36 | 0 / 0 |
| 8 | 39 | 39 | 0 / 0 |
| 9 | 37 | 37 | 0 / 0 |
| 10 | 37 | 37 | 0 / 0 |
| 11 | 39 | 38 | 0 / 0 |
| 12 | 37 | 38 | 0 / 0 |

Evidence: `reports/cache-isolation-v1/high-thread-repeat.json`. All 84 candidate
requests returned legal replies within the deadline; the baseline had one
one-thread timeout at approximately 264 ms, retained with zero credited depth.
Eight threads led the candidate by only one summed depth versus its one-thread
control. This repeat does not establish a significant high-thread depth advantage
or a cache-change speedup. More available RAM did not eliminate every deadline
failure, and the baseline timeout makes its one-thread depth comparison incomplete.

- All 16 Nu CTest suites passed after the ownership change.
- Frozen baseline/candidate comparisons matched features, priors, moves, scores,
  node counts, and PVs on 12 roots across schemas 5, 6, and 7: 36 comparisons.
- Tests exercise detached state copies/assignment, independent cache bindings,
  cache reuse, entry limits, make/unmake parity, and repeated parallel teardown.
- Benchmark evidence overwrite protection has a regression test.
- Initial parity tooling mistakenly rejected a completed shallow mate. Its
  completion check was corrected; original failure evidence remains preserved.

The next schema-7 optimization should attack full-frame feature construction
and its temporary allocations, retaining full reconstruction as the reference.
This experiment does not justify changing network width, reducing feature
coverage, changing pruning, or promising greater playing strength.

## Reproduction

Build `nu` and `nu_schema7_baseline` in Release mode. Start a fresh output
directory for a baseline; do not overwrite an existing experiment:

```powershell
python Nu/tools/cache_benchmark.py --engine ENGINE --benchmark BENCHMARK --model MODEL --output EXPERIMENT --lane baseline
# After the ownership change, using separately built candidate binaries:
python Nu/tools/cache_benchmark.py --engine ENGINE --benchmark BENCHMARK --model MODEL --output EXPERIMENT --lane candidate
python Nu/tools/cache_paired.py --directory EXPERIMENT
```

Controllers use the existing shared heavy-job locks and Idle priority. Each
stage is bounded, sequential, and CPU-only. Component roots include diagnostic
stacked/tactical fixtures; the separate ordinary UHP suite uses legal replays.
