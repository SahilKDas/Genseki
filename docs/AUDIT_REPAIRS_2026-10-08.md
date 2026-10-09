# Audit Repairs: 2026-10-08

This is a correctness audit, not a strength qualification or a claim that every
possible defect has been eliminated. Existing model artifacts and defaults are
unchanged. No matches, promotion, commit, or push were performed by this pass.

## Alpha

- Terminal bestmove requests return errors instead of reaching a panic.
- Malformed perft arguments no longer accidentally request depth 20.
- Zero and overflowing search durations are rejected.
- CLI table sizes and aspiration windows are range-checked before narrowing.
- Expansion strings reject empty, duplicate, and trailing expansion sections.
- The auxiliary UHP client handles EOF and missing replies, preserves fractional
  time limits, limits line allocations, and uses bounded writer/reader channels.
  Its administrative response watchdog is 30 seconds, not a 250 ms arena gate.
- C++ fallback numeric options reject trailing text; option changes discard
  cached search and pondering results.
- Frozen training runtime snapshots include their canonical-key dependency.
  Tactical exclusions use the index's declared position-key version.

## Shared Engine And Nu

- Diagnostic positions reject duplicate identities, oversized coordinates, and
  non-Beetle pieces above ground. Turn counters no longer wrap after 255 turns.
- Checked UHP notation rejects illegal passes.
- Nu feature caches are owned by individual states rather than thread-local
  objects. Repeated four-worker teardown and cache independence are tested.
  This addresses a suspect path from historical crash evidence; the original
  trained-model crash has not been exhaustively reproduced and cleared.
- Native GUI/review pipe writes have bounded waits; shutdown avoids synchronous
  protocol writes. Python response timeouts reject nonfinite values.
- Arena deadline/resource stops preserve completed games instead of marking a
  recoverable interruption as rules divergence. Resume policy distinguishes
  equal-search Nu opponents from external engines and rejects incompatible runs.

## Verified Evidence

- 36 Alpha Rust library tests passed, including Gen 1 evaluation parity and new
  terminal, duration, EOF, and stalled-response regressions.
- Four Alpha CTest suites passed: smoke, contracts, modes, and audit repairs.
- All 16 Nu CTest suites passed.
- Eleven selected shared CTest suites passed: core, review, review transport,
  review locking, Python transport, resources, artifacts, gauntlet, GUI state,
  GUI layout, and spectator. Core tests passed again after the pass-notation fix.
- Builds used isolated audit directories; production binaries were not replaced.

## Remaining Coverage Limits

- No new strength, loaded-machine latency, or interactive GUI acceptance run.
- Coordinate arithmetic at the diagnostic board's signed-16-bit boundary still
  requires a wider-coordinate contract or explicit checked arithmetic.
- Legacy C++ fallback repetition/TT history behavior needs dedicated differential
  search tests; it is not certified as equivalent to the MIT backend.
- Auxiliary Player trait methods still surface transport errors through their
  infallible interface; converting those callers to recoverable errors requires
  a separate interface change.
- New interruption preservation needs a dedicated mid-game interruption/resume
  integration test beyond the existing arena identity tests.
