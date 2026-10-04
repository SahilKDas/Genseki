# Nokamute Development Status

No active Genseki bot is currently promoted as Nokamute champion.

On 2026-10-04, all six native NNUE candidates (Gamma, Delta, Kappa, Xi, Sigma,
and Chi) were tested on the same non-final mirrored opening pair at 230/250 ms.
Every candidate scored 0/2. A separate native queen-pressure heuristic control
also scored 0/2; that control was not Alpha and is not a Greek bot. Games
completed without illegal moves, UHP divergence, or time forfeits
after deadline-aware move ordering was installed.

The probes reached only depth 3-4. Nokamute's compact board and move generator
are designed for much higher node throughput; Genseki's current vector-backed
board and small 128-game training corpus are not yet competitive. These probes
are rejection evidence, not statistically meaningful strength estimates, so no
20-game development gauntlet and no sealed 100-game final were run.

Promotion remains fail-closed: a candidate must first project above 55% in a
20-game development gauntlet, then score strictly above 55/100 in the frozen
final protocol documented in `docs/NOKAMUTE_GATE.md`.
