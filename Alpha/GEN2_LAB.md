# Gen 2 Lab Redesign

This replaces the development workflow, not Gen 1's evaluator or search.
Old models, games, calibration and pinned executables remain historical evidence.
No residual hybrid, expansion support, GUI default change or automatic promotion
is introduced. Iota is excluded.

## Native Evaluation

- Neural schema 4 and integer weights remain unchanged.
- Articulation flags use the engine's single cut-vertex traversal instead of
  flood-filling the board once per stone. The old calculation remains a reference.
- Worker-local exact-state feature caching retains at most 128 KiB and 32 entries.
  Keys include stone identities, stacks, inventory, queens and full move history;
  there is no hash-only cache match or cached search value.
- The total evaluator/table ceiling reserves 256 KiB for each of twelve workers
  plus the controller, then subtracts model memory before sizing the table.
- `alpha-feature-cache` reports serial-thread hits, misses and retained bytes.
  These metrics do not aggregate parallel-worker counters.
- Full reconstruction and make/unmake parity remain correctness references.
  Feature maintenance is not fully incremental. Low cache hit rates are reported,
  not presented as a solution to cold feature costs.

## Development Data

`tools/gen2_lab.py collect` consumes declared development arena replays only.
It samples across source games deterministically, including student loss lines,
and scores **every legal child** with frozen Gen 1 evaluation/search through the
same native binary. An interrupted decision is not committed as a sampled one.
Completed decisions are atomic and resume from their recorded IDs.

Rows retain searched/static target provenance, actual child search depth/nodes,
both feature perspectives, canonical parent/child states and opening family.
Natural outcomes require independent rules confirmation; capped, timeout and
repetition-adjudicated games get no invented outcomes. Position annotations cover
queen pressure, stacks, reserve availability and student-loss sources; they are
not certified tactical proofs.

Training keeps source games and mirrored opening families together, excludes
cross-split transpositions and all parent/child tactical exposures. The default
checkpoint criterion is held-out **decision regret**, with explicit ranking loss
weight 0.25. Training refuses data without full-width decisions in both splits.
Checkpoint regret applies native score clipping and rules-resolved terminal or
repetition values, rather than judging the network on states where rules decide
the value. The Alpha training wrapper is pinned alongside the Nu trainer.
`--selection mse` is an explicit research ablation, not the default. Static versus
searched labels use separate corpus namespaces via `--target static|search`.
The pinned Nu trainer retains its recorded natural-outcome blend; this pass does
not claim an independently tested outcome-weight ablation or symmetry augmentation.

## Measurements

`audit` reconstructs model predictions for all children of held-out decisions and
reports top-choice agreement, mean regret in Gen 1 units and slice counts.
Training loss is not a strength gate.

`compare` runs fresh serial searches using identical search options and total
memory ceilings, pairing Gen 1 and neural evaluation at requested fixed depth and
230 ms internal time. Actual completed depth, nodes, elapsed time, PV, model/table
diagnostics and cache metrics are retained. A mate stop or time interruption that
does not complete the requested depth is flagged, not labeled equal-depth evidence.
This diagnostic is not an external 250 ms gauntlet or a loaded-system guarantee.

All stages are locked, Idle priority, resumable with artifact/config checks,
limited to two hours and restricted to one heavy job. Existing RAM/storage floors
and the 1.5 GiB training VRAM cap remain in force. New executables require new
report namespaces; old gauntlets resume only with their original pinned executable.

## Commands

Use a hash-frozen model plus its calibrated `.alpha.json` sidecar as `MODEL`.

```powershell
python Alpha/tools/gen2_lab.py collect --model MODEL --sources Alpha/reports/gen2/latest-nu-vs-gen1.json --corpus lab-next --positions 256 --seconds 7200 --stage-id lab-collect-next
python Alpha/tools/gen2.py train --corpus lab-next --selection regret --ranking-weight 0.25 --seconds 7200 --stage-id lab-train
python Alpha/tools/gen2_lab.py audit --model MODEL --sources Alpha/reports/gen2/latest-nu-vs-gen1.json --corpus lab-next --seconds 600 --stage-id lab-audit
python Alpha/tools/gen2_lab.py compare --model MODEL --sources Alpha/reports/gen2/latest-nu-vs-gen1.json --positions 16 --depth 3 --seconds 600 --stage-id lab-compare
```

A corpus freezes its binary, model, calibration, source-report hashes and label
configuration. Extending a corpus invalidates an already-created training index;
use a new training/corpus namespace rather than mixing changed input identities.
Small smoke datasets verify machinery only and are not champion training evidence.
Development and sealed strength gates remain unchanged.

## Evidence And Recovery

Before the branch interruption, the pilot committed 15 complete decisions. Its
two retained held-out decisions had mean regret 14.5 Gen 1 units and 50% top-choice
agreement. This is a workflow smoke test, not a generalization or strength claim.
The four-position paired test preceded the single-traversal optimization and
showed low cache reuse and substantial cold-feature cost. A post-optimization
speedup has not been measured; do not substitute those older timings for it.

GitHub Desktop's automatic stash on `history` retained the ignored artifacts.
On 2026-10-06, 68 selected artifact files were recovered without applying or
popping the stash, and verified byte-for-byte against its Git blobs. The latest
Nu checkpoint, frozen Gen 1 binary and Nu reference executable also matched
their pinned SHA-256 checksums. All eight Lab pipeline tests pass with the
restored corpus. The pinned Nokamute executable was not present in the stash
and remains missing. No training, model comparison or gauntlet was launched
during recovery. Pinned trainer source may be rehydrated only when current
source matches its retained checksums; missing weights must never be silently
replaced with untrained models.

Commit-readiness verification on 2026-10-06: 30 native Rust tests, eight Gen 2
integration tests, eight Lab pipeline tests, four Lab audit regressions, six
gauntlet unit tests, two transport tests and three headless spectator tests
passed. Dependency registry URLs in the Alpha Cargo lockfile were repaired
without changing versions or checksums. This verification ran no training or
strength matches and makes no new performance or promotion claim.
