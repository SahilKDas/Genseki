# Overnight Campaign Outcome

The original campaign window began October 4, 2026 at approximately 17:20 PDT
and ended October 5 at approximately 01:20 PDT. No restart was made after that
window; monitoring was paused.

- Retained replay: 60 games and 6,412 positions.
- Natural finishes: 26; 160-ply capped games: 34.
- G8 completed CUDA training: two epochs, 82 optimizer updates, 5,200 training
  positions and 1,212 validation positions; batch size 128.
- G8's 40-game promotion arena did not complete. No score or strength claim
  is supported. G0 remains the authoritative champion.
- Initial run stopped on the 30-second move watchdog. Recovery used 120 seconds
  with unchanged simulations, workers, memory caps and original deadline.
- Recovery stopped after 21,650.20 seconds at the 2 GiB available-RAM floor.

Evidence: `G8-training.json`, `campaign-1791159602857541300.json`,
`campaign-1791160739529946700.json`, corresponding source snapshots and logs.
Champion, challenger, replay manifest and immutable lineage are retained.
Resume currently starts a fresh generation, not the unfinished G8 arena.
