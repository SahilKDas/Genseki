# Alpha performance work

## Safety contract

Evaluation weights, legal moves, pruning, noisy moves, opening policy and default
parallel split depth remain unchanged. Timing fixes can change which depth is
completed; they do not change a completed depth's scoring rules. No benchmark
here establishes strength non-regression or champion qualification.

## Six tracks

1. Profiling: `profile` reports evaluation, move generation, connectivity,
   incremental hash access, board cloning and make/unmake nanoseconds. Its
   make/unmake loop verifies hash restoration. `profile-search` measures complete
   fixed-depth searches and reports single-worker scores/nodes/PV, or parallel
   search diagnostics. `tests/profile_suite.py` freezes its positions from the
   paired corpus, rather than selecting favorable examples.
2. Compiler: native CPU targeting and thin LTO were measured separately. Neither
   demonstrated an improvement on the sampled workload; release defaults remain
   portable. `tools/build-performance.ps1` supports isolated native/LTO and PGO
   builds, records compiler/flags/hash, and restores RUSTFLAGS. A matching
   `llvm-profdata` was not found on PATH, so PGO use is not verified. Raw profiles
   must be collected on representative development searches and merged with the
   matching LLVM tool before profile-use. Do not train profiles on final seeds.
3. Repeated work: queen-neighbor arrays are computed once per evaluation instead
   of per piece. The same hex values and evaluation weights are retained.
   Incremental Zobrist hashing already existed; it was not reimplemented.
   Cut-vertex caching is deferred: make/unmake, stacks and pillbug restrictions
   require invalidation tests before such a cache can be trusted.
4. Allocations: recursive move buffers already use worker-local pools. A reusable
   stable merge sorter matched the original ordering in tests for lengths 0..159,
   but its candidate was slower in paired runs. Production sorting was restored;
   the experimental implementation exists only under cfg(test). Parallel child
   boards must stay independent; removing their copies without an ownership
   redesign would introduce races.
5. TT/parallel: bounded tables and lock-free access already existed. Atomic
   ordering was not weakened. `--serial-cutoff-depth` and profile-search's cutoff
   argument enable measured split-depth experiments; default remains 1. Table
   sizing rounds upward to powers of two upstream, so requested MiB is not an
   exact allocation ceiling. A stricter table-size change needs separate
   capacity/strength validation, not silent cache reduction.
6. Timing: native single-worker and parallel searches directly check monotonic
   deadlines in addition to cancellation flags. The sleeping timer thread no
   longer has sole responsibility for noticing expiry. The last completed
   iteration remains the result source. This is not a hard real-time guarantee:
   scheduling delays and an individual expensive operation can overrun a budget.

## Reproduction

Run from the repository root, with no competing heavy workload for timing claims:

```powershell
cargo build --release -j 1 --manifest-path Alpha/vendor/nokamute/Cargo.toml --target-dir Alpha/build/rust-target
python Alpha/tests/performance.py --baseline Alpha/build/alpha_mit_baseline.exe --candidate Alpha/build/rust-target/release/alpha_nokamute_mit.exe --output Alpha/reports/performance-retained.json --depth 4 --rounds 25
python Alpha/tests/profile_suite.py --engine Alpha/build/rust-target/release/alpha_nokamute_mit.exe --corpus Alpha/reports/performance-retained.json --output Alpha/reports/profile-suite.json
```

The baseline executable is an ignored local snapshot, identified by SHA256 in
each report. The corpus uses seed 0xA1FA2026, nine positions through ply 32,
32 MiB requested tables, no pondering, and no random opening policy. Upstream
still shuffles root search moves, including on one worker. Timed legality checks
request 230 ms and use one/two workers to limit contention with Bravo.

The first depth-4 sorter/LTO run had a summed-median speed ratio of 0.974;
the 25-repeat LTO run had 0.981 (above 1 means faster). Those experiments were
rejected. Native results overlapped a build and are exploratory, not reliable
comparative evidence. Reports retain executable hashes and raw timings.

After restoring default compiler settings and sorting, the retained candidate
measured 1.0182 on the same corpus with 25 repeats per position. Its 18 timed
replies were legal, maximum 230.2924 ms. Two-worker cutoff medians summed to
127098/118571/128082 microseconds for cutoffs 1/2/3, respectively, with matching
root scores on these samples. This is limited development evidence; split depth
1 remains the default. The component suite shows move generation dominates
evaluation on later sampled positions. A reported hash time of 0 ns means the
integer average is below timer resolution; it does not mean free hashing.

## Intelligence next

- Build an independently checked tactical suite: queen escapes, forced surrounds,
  beetle control, articulation/pinning, forced pass and simultaneous-surround
  draws. Keep a held-out set for promotion, not tuning.
- Train value models on game outcomes with game-level train/validation splits.
  Keep adjudicated and heuristic targets separately marked. Do not present
  imitation of queen-pressure labels as independent learned strength.
- Start with an NNUE residual over the current evaluator, gated against the
  unchanged evaluator through the same full-width search. Compare dense/CNN
  baselines with equal optimizer-update budgets and bounded minibatches.
- Test tactical extensions and reductions individually. Require tactical-suite
  non-regression, deadline legality, and mirrored development games before
  enabling them. Higher node throughput alone is not stronger play.
- Tune evaluation scale/weights on development openings with frozen validation
  matches. Never tune on the sealed Nokamute champion-gate seeds.
- Promote only after a larger paired strength test and the established sealed
  100-game gate, strictly above 55 points. Small matches do not prove parity.

Everything in this pass is isolated to Alpha. No Rho files or training processes
are modified. No GPU training or qualification gauntlet is started here.
