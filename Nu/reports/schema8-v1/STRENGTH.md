# Schema 8 Development Gates

Two mirrored 20-game screens completed on the same ten frozen development
openings. Both sides received eight CPU threads, 16 MiB tables, 230 ms internal
requests, 250 ms external deadlines, depth ceiling 64, pondering off, and a
160-ply cap. Every timeout counted as a loss for the offending engine.
Candidate binary/model hashes and opening/referee hashes are in the reports.

| Opponent | Schema 8 Points | Natural Games | Repetition Draws | Capped Draws | Schema 8 / Opponent Timeouts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Schema 7, identical search binary | 14/20 | 7 | 1 | 1 | 4 / 7 |
| Frozen Alpha Gen 1 | 6.5/20 | 15 | 1 | 0 | 1 / 3 |

Both reports are complete and not rejected by replay/board validation. The
schema-7 comparison passed its screen, but timeout forfeits materially affected
the score. Alpha Gen 1 failed the greater-than-50-percent advancement gate.

Sealed qualification was therefore **not launched**, its opening reservation
was not read, and no qualification attempt or champion was registered. No
promotion or default-engine change occurred. Faster schema-7-equivalent
evaluation is demonstrated separately; these results do not establish Alpha
parity. Schema 8 remains opt-in.

Raw resumable evidence remains in ignored `work/schema8-v1`. Public copies
retain per-game searches, moves, results, termination reasons, hashes, and
settings, with invocation paths reduced to filenames.
