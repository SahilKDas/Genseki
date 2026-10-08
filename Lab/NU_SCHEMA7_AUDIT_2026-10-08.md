# Nu audit and repeatable winning motifs â€” 2026-10-08

## Result orientation and provenance

The screenshot reports **schema 7's points**, not the opponent's. Against frozen Alpha Gen 1, schema 7 earned **1.5/20: one natural win, one 160-ply capped draw, eighteen losses**. There were no timeouts in that screen. The capped draw is not a demonstrated draw under unlimited play.

All three screen hashes match the published campaign summary; point totals match the per-game scores. The frozen engine, schema-7 model, referee, Gen 1, and opening file hashes were checked before reconstruction. Source evidence is `Nu/work/schema7-campaign/screens/gen1.json`; portable audit evidence is `Lab/NU_SCHEMA7_AUDIT_2026-10-08.json`.

## What worked in the win

Development game 15, opening seed 310007, Nu playing White, finished at ply 39. The same opening with Nu playing Black lost at ply 37: the opening is not a demonstrated winning recipe.

| Ply | Verified board event |
| --- | --- |
| 21 | White's first beetle climbed onto its own ant, approaching Black's Queen. |
| 23 | `wB1 bQ` covered Black's Queen. The Queen still had five liberties: covering alone did not win. |
| 26 | Black's beetle climbed onto that stack, taking top control. |
| 27 | `wB2 bB1` restored White control; stack bottom-to-top was Black Queen, White beetle, Black beetle, White beetle. |
| 29â€“37 | White placed/moved surrounding pieces. Black Queen liberties went 4, 3, 2, then 1. White's Queen still had two liberties at ply 37. |
| 37 | White's spider placement reduced Black Queen to one liberty. The original search completed depth 3 and scored +99997, a forced win in three plies. |
| 39 | `wB2 wA3-` left the stack and filled the last Queen neighbor. Black Queen had zero liberties; White Queen had two. |

The distinguishing motif is **Queen confinement plus sustained stack control plus coordinated surrounding**, followed by exact terminal search. Ant deployment helped reach the attack, but this game does not isolate ant-prior weights, canonicalization, or training as the cause of victory. The prior was only +6 immediately after ply 27; it cannot alone explain the whole sequence.

## What the half-point means

Game 1 reached the 160-ply cap. At its end, White’s Queen had three liberties and Black’s had five. White’s beetle cycled between covering its own Queen and a Black ant while Black’s Queen shuttled nearby. This records survival to the cap, not a proven natural draw or successful Queen attack. Treat it as a cycle/progress diagnostic, not a second winning motif.

## Fresh checks on the decisive positions

All checks used the frozen common executable, one thread, threat extension off, requested depth 3 with 230 ms internal / 250 ms external limits, and the same legal replay prefixes. These are single-position checks, not a repeated deadline gate.

| Model | Before ply 37 | Before ply 39 |
| --- | --- | --- |
| Schema 5 | Depth 3, +99997; chose the spider move; about 59 ms | Immediate win, +99999 |
| Schema 6 | Only depth 2, +63; chose another move; about 221 ms | Immediate win, +99999 |
| Schema 7 | Depth 3, +99997; chose the spider move; about 93 ms | Immediate win, +99999 |

Thus schema 5 also finds the winning tactic once given this position. Schema 7's superiority over schema 6 in the screen cannot be attributed solely to neural quality: evaluation cost and completed depth are confounded. Schema 6 did not finish depth 3 in this check; it was not shown incapable of finding the win at a larger budget.

## Current code audit

Scope: root integration, shared transport/gauntlet, Nu native feature/state/search contracts, collection, teacher parsing, training/indexing, arena/benchmark/reporting, and retained development evidence. This was not an exhaustive formal verification or a fresh native rebuild.

The earlier four findings are repaired in current source: depth 64 requests, canonical exclusion keys for schemas 5/6/7, legal board reconstruction, and a command deadline covering queued writes and reads. Seven focused Python suites passed in this audit: transport (13 tests), gauntlet (11), leakage, teacher, collection, benchmark, and residual tests.

### P1: malformed diagnostic positions violate native array bounds

`src/core/board.cpp`, `Board::from_position_string`, accepts duplicate piece identities, more than 22 stones/stacks, and coordinates outside int16 range. Safe schema-3 probes accepted two copies of wA1, accepted 23 duplicate-identity stacks, and wrapped coordinate 65536 to zero. `Nu/src/features.hpp`, `connectivity_pins`, assumes at most 22 cells and indexes fixed-size arrays by cell index; schemas 5/7 can therefore access outside those arrays on accepted malformed positions. No unsafe fast-schema execution was attempted. Validate inventory uniqueness/count, coordinate range, and board geometry before constructing State; retain defensively checked feature boundaries. This is not evidence of the cause of the legal-game schema-6 exits.

### P1: schema-6 multithreaded reliability remains unresolved

The retained benchmark records three heap-corruption exits and fourteen timeouts at four threads, and five timeouts at two threads. No sanitizer diagnosis was performed here. Keep one thread as the baseline and diagnose against recorded roots in an isolated sanitizer build before treating multithreading as supported research evidence. These failures are not the explanation for the one-thread Gen 1 screen, which had no timeouts/exits.

### P2: tracked campaign reporting exposes host paths

`Nu/reports/schema7/campaign.json` contains absolute host paths in frozen-file source metadata. `Nu/tools/report_schema7.py` copies the frozen object into the public report without applying the shared portability sanitizer. Publish relative artifact paths while preserving hashes; do not rewrite the immutable private source evidence. This audit leaves the existing campaign report intact.

## How to repeat the useful part

1. Turn the pre-37 and pre-39 positions into explicit tactical regressions. Verify legal continuations, forced wins across every opponent reply, color-swapped and all twelve rotated/reflected forms. Keep these development exposures out of future final qualification/training validation.
2. Diagnose the eighteen losses using the first missed defense or winning reply, rather than training only on the one win. Compare chosen move and alternatives with frozen deeper Gen 1 search; retain teacher depth and mate diagnostics.
3. Test the already available threat-extension setting (0 versus 2/4 plies) on a disjoint development tactical set and then mirrored screens. It directly targets shallow forced wins/defenses but may consume time; measure completed depth and deadline failures. Do not enable it by default without evidence.
4. Add bounded Queen-confinement/top-control/escape-pressure priors only as a separately versioned candidate after ablation supports them. Changing the prior requires retraining the residual; do not silently change schema 7's ABI. Avoid putting expensive exact mobility back into every evaluation.
5. Select residual candidates on held-out move regret as well as MSE. Current selected weights agree with teacher top choices only 62.48% of 541 held-out decisions; training loss alone is an incomplete strength signal. Mine diverse independent legal games, keeping natural outcomes separate from capped/repetition records and mate targets separate from nonterminal regression.
6. Compare each change with identical search, one thread, memory budget, and 230/250 ms deadlines on fresh development openings. Freeze before larger development matches. Retain every timeout/capped result. Do not retry/tune against sealed qualification seeds or describe replaying game 15 as a new strength result.

The highest-value next experiment is tactical loss diagnosis and a bounded threat-extension comparison, followed by evaluator/prior ablations. The evidence supports a reusable tactical motif, not a repeatable 55% win rate against Gen 1. No model/default/promotion changes, new training, sealed matches, commits, or remote pushes were performed by this audit.
