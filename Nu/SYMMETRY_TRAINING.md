# Canonical Symmetry Retraining

The original private run used schema 5; its canonical contract was subsequently
migrated to schema 6. Schema 5 now identifies the separate fast/residual evaluator.
Historical paths and hashes below intentionally retain their original meaning.

## Verified Run

The reproducible 64-wide linear challenger was retrained from fresh weights on
CUDA, not initialized by relabeling schema-4 embeddings or optimizer state.
`tools/symmetry_retrain.py` reads the original curated SQLite index read-only,
checks its corpus identity against the original checkpoint, re-encodes parent
and saved child geometry, and verifies that samples and splits remain identical.
Missing child geometry is an error, not silently discarded supervision.

Results retained in `work/symmetry-v5/linear-64`:

- 384 curated positions: 271 training, 113 validation; original tactical
  exclusions and game/opening metadata preserved.
- Same 12 epochs, batch 128, seed 220620 and learning rate 0.001 as the source.
- 36 optimizer updates; epoch 1 selected by held-out MSE.
- Validation MSE: 0.08882829784292036, versus 0.08679094567763067 for the
  original schema-4 run. Later epochs worsened, so the exported model is not
  the last epoch. These losses are not strength measurements.
- Peak PyTorch CUDA allocation: 12,464,128 bytes, below the 1.5 GiB ceiling.
- Native model loading succeeded; features and scores matched across 48
  rotated/reflected/translated checks on four encoded positions.
- Original checkpoint and curated-index hashes remained unchanged.

Model SHA-256:
`da255c85cf7ec29d07f81e3131c331fc991c40d385e1d0062ead8d2580b39e26`.
The stage manifest pins source identities, encoder and trainer hashes, the
encoded corpus checksum, and the original two-hour deadline. Resume uses the
same identities and remaining deadline, never the schema-4 optimizer.

## Pending Work

The 128-wide nonlinear Nu model is explicitly pending at the user's request:
its original source corpus was not found in the checkout or a stash. It was
not retrained using the smaller replacement corpus.

Full verification was subsequently completed before the incumbent gauntlets:
native integer inference matched the integer reference exactly on 400 positions.
The maximum float-checkpoint versus quantized-model difference was
13.239554688334465 centipawns. Evidence is retained under
`work/symmetry-v5/gauntlets/series-001/artifacts` with the pinned model.
Twenty-game incumbent screens followed by Alpha Gen 1 are development evidence,
not sealed qualification. No production promotion was performed.

## Development Gauntlets

All three requested screens completed in order, with ten mirrored opening pairs,
250 ms external deadlines, 230 ms internal requests, one thread, 16 MiB tables,
pondering disabled and a 160-ply cap. Seeds were 82000--82009. Both Nu incumbents
used the same frozen Nu executable as the challenger; Alpha Gen 1 used its
separately pinned binary. No rules/protocol divergence was reported.

| Opponent | Points | Wins | Draws | Losses | Score |
| --- | --- | --- | --- | --- | --- |
| Original 64-wide linear | 10.5/20 | 5 | 11 | 4 | 52.5% |
| Original 128-wide nonlinear | 3/20 | 2 | 2 | 16 | 15% |
| Alpha Gen 1 | 0.5/20 | 0 | 1 | 19 | 2.5% |

The two wins against the 128-wide model were **opponent timeout forfeits**, not
natural board wins. No challenger timeout occurred. The first screen's draws
were ten ply caps and one repetition; the other screens had two and one capped
draws respectively. Maximum observed move times were 228.60 ms, 257.90 ms
(including a timeout), and 234.25 ms respectively.

Evidence is retained in `work/symmetry-v5/gauntlets/series-001`, including
per-game moves, search diagnostics, timing, immutable engine/model copies,
and `series.json`. Completed game rows may resume only with matching pinned
identities, options and mirrored order; rejected runs cannot resume.

This corrects geometric feature invariance, but does not demonstrate competitive
improvement over the stronger incumbents. No promotion was made at the end of
these screens; the later user-authorized 64-wide replacement is recorded below.

## Authorized 64-Wide Incumbent

The user subsequently explicitly promoted this model as the 64-wide research
incumbent, not the production champion. Inspection of the original checkout
found an independent fast/residual evaluator also using schema 5. To prevent
silent feature-contract substitution, the canonical evaluator was assigned
schema 6, reserving schema 5 for that parallel implementation.

The binary model's header was migrated from 5 to 6; its entire learned payload
was unchanged. The float checkpoint's schema metadata was migrated with exact
tensor equality. Native features and scores matched the frozen gauntlet pair
on all 384 curated positions; 12 depth-one searches matched move, score, nodes
and principal variation. All eight schema-6 suites passed.

The original checkout's `Nu/incumbents/64-linear.json` pins the required engine
and model pair. `Nu/tools/incumbent.py` verifies both hashes before launching.
The bundle's schema-6 model must not be loaded into the original fast evaluator.
Original checkpoints, historical gauntlets and parallel source changes remain
preserved; no Alpha/GUI default or sealed qualification was changed.

Both implementations have now been reconciled in the main checkout. See
`COMBINED_INTEGRATION.md` for the new combined-build parity checks. The original
registration and gauntlet binaries remain pinned; neither was silently replaced.
