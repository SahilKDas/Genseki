# Nu fast hybrid evaluator (experimental)

Schema 5 is opt-in through its model header or `--feature-schema 5` for untrained diagnostics. Schema 3 remains the seed default; schemas 1Ã¢â‚¬â€œ4 retain their feature definitions and trained weights. Schema 4 remains the reconstruction reference. Existing trained models cannot be relabeled with schema 5.

## Implementation

- Schema 4 retains the pending move through lazy evaluation. A single occupied-to-occupied elevated beetle move can reuse ground mobility; multiple unevaluated moves and other occupancy changes reconstruct exact mobility. Undo restores pending work and cached ancestors.
- Schema 5 stores immutable per-piece descriptors and encoded features. Unchanged descriptors reuse feature blocks; changed pieces, stacks and adjacent height patterns update their blocks. Queen anchor changes invalidate relative-coordinate blocks. Sorted multiset deltas update accumulators, preserving duplicate hashed features.
- Exact legal mobility and articulation are absent from schema 5 neural inputs. Local gate patterns are proxies, never claims of legal mobility. Snapshot construction still scans at most 22 pieces and sorts small feature lists: this is not a claim of constant-time make/unmake.
- The fixed prior distinguishes covered, connectivity-pinned, and locally gate-blocked pieces. Reasons are mutually exclusive. Connectivity uses an exact small Tarjan graph, cached until occupied geometry changes; no ant/spider move generation is invoked by the prior.
- Prior v1 penalties (queen, spider, beetle, grasshopper, ant): covered `[45,65,55,70,145]`; pinned `[25,40,35,45,100]`; locally blocked `[12,18,16,20,30]`. Queen pressure adds `18 * occupied_neighbors^2`. White-oriented prior clamps to Ã‚Â±1800; hybrid evaluation to Ã‚Â±6800. Search retains terminal scores near Ã‚Â±100000.

These are explicit initial strategic preferences, not evidence that pinning an ant is always better in every position. Changing this prior requires a new schema contract; a trained residual must keep the same prior.

## Threading findings

The one-thread root path uses PVS null-window probes after its first move. Parallel roots use aspiration windows and may require full-window re-searches; lanes do not share a live root alpha. Worker threads are recreated each depth, so their thread-local schema-4 feature caches are also recreated. These code paths explain why more threads can perform different amounts of work; profiling does not isolate their individual costs. One thread remains the experimental baseline.

Schema 5 coordinates remain orientation-dependent. Symmetry-normalized training exclusion keys prevent leakage; they do not make neural evaluation rotation-invariant. Integrating symmetry-based transposition tables requires separate evaluator invariance verification.

## Residual training

Schema 5 corpus rows must provide `strategic_prior_version=1` and `prior_white`, including each ranking child. Training compares `tanh(network + prior_white/600)` with the existing supervised target. Ranking and validation add each childÃ¢â‚¬â„¢s own prior. Exported weights contain only the residual. Natural outcomes remain distinct from teacher search targets; capped outcomes are not invented. Mate-range labels are excluded by the pilot.

The trainer keeps optimizer/RNG checkpoints, rejects incompatible resumes, and exports immutable schema-5 candidates. Canonical leakage keys normalize translation, all twelve Hive symmetries and interchangeable identities; opening/game grouping and child exposure exclusions remain active. Frozen tactical exposures are excluded by the campaign.

## Bounded reproduction

Build a separate executable from `Nu/src/main.cpp` and `src/core/board.cpp`, with `-std=c++23 -O2 -DGENSEKI_NU_CANCELLATION -Iinclude -INu/src`. Run builds/tests under the existing team lock; standalone research tools acquire team then application locks themselves.

```
python -B Nu/tools/fast_campaign.py --engine <new-nu.exe> --baseline-engine <frozen-old-nu.exe> --baseline-model <schema4.nnue> --data Alpha/work/gen2/corpus --exclude-fixtures .tmp/team-genseki/developer-3/contracts/tactical-fixtures-v2.json --output Nu/work/<fresh-pilot> --seconds 1800 --epochs 8 --screen
```

Stages run serially at Idle priority, with CPU minibatches and existing RAM checks. Profiling requests use 230 ms internal / 250 ms external deadlines at 1/2/4 threads and identical verified table requests. Future runs enforce a common 64 MiB peak working-set/commit ceiling. Reports preserve deadline failures, legal replies, nodes, depth, feature/inference/generation timings and working-set measurements. Profiling uses fresh sessions per root to avoid order-dependent table/cache carryover. Worker profiling times are summed CPU elapsed measurements, not fractions of wall time.

The pilot checks independent integer inference, schema-4 completed-depth parity, and immutable input hashes. A 20-game mirrored development screen uses one thread and a 160-ply cap only after preflight passes. Completed games can resume only with `arena.py --resume` and matching artifact hashes, settings and game prefixes. No automatic promotion, sealed qualification or default change.

Evidence is kept in `Nu/work/fast-schema5-pilot-v2/`; interrupted v1 evidence is preserved separately. Results and exact hashes are summarized in the final role handoff.

## Verified pilot results

All four implementation stages are complete. Schema 4 completed-depth parity matched scores, moves and nodes on 8/8 positions; independent integer inference matched 24/24. Native state/undo/worker tests, protocol tests, residual validation, deterministic interrupted-training resume, and arena resume/hash rejection checks passed.

The corrected paired benchmark consumed evaluation outputs and used 576 identical moves at width 64: schema 4 took 74.0993 ms versus schema 5 at 9.7417 ms for make/evaluate/unmake (7.61Ã—); feature work was 72.1659 versus 7.3322 ms (9.84Ã—). This measures evaluation cost, not playing strength or overall search speed.

| Evaluator | Depth sum, 1 thread | 2 threads | 4 threads | Timeout counts, 1/2/4 |
| --- | ---: | ---: | ---: | --- |
| Frozen schema 4 | 42 | 30 | 13 | 0/3/10 |
| Compatible optimized schema 4 | 41 | 22 | 17 | 0/5/8 |
| Schema 5 hybrid | 51 | 42 | 45 | 0/0/0 |

These totals cover five development roots and three repeats with 230 ms internal / 250 ms external deadlines. A separate final memory preflight enforced the common 64 MiB peak working-set/commit ceiling and verified thread/table settings. One thread remains the baseline.

The 20-game mirrored development screen scored 11.5/20: 14 natural games yielded 8 points, three capped games 1.5 points, and three timeout games 2 points. One candidate timeout and two opponent timeouts occurred. No protocol divergence or illegal move was reported. The candidate is **promoted by explicit user decision**, excluding its timeout loss from promotion scoring: **11.5/19 (60.5%)**. The original 11.5/20 arena record is preserved. The user overrides the deadline gate for this promotion; the candidate remains not deadline-qualified, and no sealed strength qualification was performed. Production defaults remain unchanged.

The CPU residual pilot used eight epochs on a small existing teacher corpus; the selected checkpoint was epoch 1 (64 total updates in the run). This checkpoint is the user-promoted schema-5 candidate. Initial interrupted pilot evidence and all timeout failures remain available.
