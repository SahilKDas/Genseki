# Combined Nu Integration

Both implementations are now in the primary checkout, on `standard`.
The symmetry worktree remains intact, and nothing was committed or pushed.

## Preserved Contracts

| Schema | Contract |
| --- | --- |
| 1--4 | Existing orientation-dependent features and scores |
| 5 | Fast local descriptors, incremental piece snapshots, strategic prior v1 and learned residual |
| 6 | Canonical D6 geometry, exact mobility and schema-4 tactical feature banks |

Untrained engine runs still default to schema 3, preserving the main checkout's
behavior. Trained model headers select their own schema. The combined loader
accepts schemas 1--6, rejects unknown schemas and prohibits overriding a loaded
model's schema. The schema-5 strategic prior is not applied to schema 6.
Alpha, the 128-wide incumbent, and GUI defaults were not changed.

Schema 6 uses the main checkout's deferred evaluation and bounded thread-local
cache, with exact mobility enabled for schemas 4 and 6 only. Fast schema 5 never
falls through into exact mobility feature construction. Search and instrumentation
from the main checkout were retained.

Training, collection, and re-encoding accept the canonical contract explicitly.
Residual training still requires schema-5 prior metadata for parents and children.
Both arena implementations were reconciled: saved settings/artifacts, mirrored
prefixes and totals are validated; completed matches are not rewritten or replayed;
artifacts are checked between games. Engine options explicitly disable pondering
and fix table size and opponent search settings. No historical arena report was
rewritten or resumed using the combined binary.

## Verified Evidence

- Standalone Release build: all 11 Nu CTest suites passed.
- Root-project Release build: all 15 selected suites passed, including the 11 Nu
  suites and shared transport, resource, artifact, and gauntlet tests. This was not
  a run of every repository test or a GUI acceptance test.
- Root binary SHA-256:
  `b51e033e95054db73cc871093624ff668b4afe54aca3c3da20b73001f90df968`.
- Trained schema 6: feature/score parity on all 384 curated positions and exact
  move, score, node count and PV parity on 12 depth-one searches against the
  incumbent's frozen engine/model pair.
- Trained schema 5: the same parity checks on all 379 pilot corpus positions and
  12 depth-one searches against the fast evaluator's frozen engine/model pair.
- Legacy schemas 1--4: 384 feature/score positions and 12 depth-one searches per
  schema against the pre-combination fast executable, using deterministic seed
  weights. This is compatibility evidence, not a new strength result.
- Training tests verify byte-identical interrupted CPU training for both the
  schema-4 model and the schema-5 residual, with bounded accumulation and leakage
  exclusions. No new training campaign or gauntlet was started.

Machine-readable reports are under ignored `work/combined-verification`, including
`root-canonical-parity.json`, `root-fast-parity.json`, and
`legacy-{1,2,3,4}-parity.json`. `tests/contracts.py` reproduces the checks with
explicit reference/model hashes and bounded development positions. Existing
strength and deadline limitations have not been waived by integration parity.

The registration `incumbents/64-linear.json` deliberately retains the original
hash-pinned pair and historical match evidence. The combined executable can load
that schema-6 model, but its new hash does not inherit an old arena qualification.
No new incumbent or production promotion was made during this merge.

## Backups And Artifacts

Full pre-combination copies, including ignored weights, checkpoints and reports:

```
.tmp/nu-combine-backup-20261007-224202/main-Nu
.tmp/nu-combine-backup-20261007-224202/symmetry-Nu
```

The sibling `manifest.json` records 88 files / 85,192,367 bytes for main Nu and
76 files / 43,036,392 bytes for symmetry Nu, with content-tree hashes. Preserve
these backups until the combined changes have been reviewed and committed.

The symmetry training and gauntlet history was copied into primary
`Nu/work/symmetry-v5`; all 20 copied files matched the backup hashes. That name and
the archived header-5 canonical weights are historical, not the fast schema-5
contract. Use their frozen historical executable only; use the migrated schema-6
registration for current canonical play. Never relabel or interchange model
headers between these contracts.

Original schema-4 64-wide weights, 128-wide weights and Alpha Gen 1 hashes remain
unchanged. Immutable local artifacts and backups stay ignored. Committing source
and registration does not distribute the weights or executables.

## Review Before Commit

All combined source, tools, tests and documentation are under primary `Nu/`.
Keep all new test/tool files with the modified CMake file; do not commit only the
tracked modifications. No staging, commit, stash operation, branch switch or push
was performed. Backups and historical source worktrees have not been deleted.
