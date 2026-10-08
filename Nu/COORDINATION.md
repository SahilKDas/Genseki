# Joint-threat development evaluator

Opt in with `HybridEvaluation True`, `HybridTerms 64`, `HybridWeight 100`.
Bit 64 is independent of the earlier six hybrid terms; mask 64 does not enable them.
Existing models, feature schemas, production defaults and prior weights are unchanged.

The position term examines Queens with at most three liberties. Legal movement
generation accounts for connectivity, gates, covered pieces and Queen placement.
A small subset dynamic program matches distinct attackers to distinct empty
Queen neighbors: one attacker cannot cover several liberties simultaneously.
Moves vacating another occupied Queen neighbor are excluded from coverage and
discounted. Adjacent immobile enemy pieces and a single mobile non-Queen defender
provide small dependency/fragility signals. White and Black receive identical
analysis, so attacking opportunities also expose our defensive weaknesses.

Weights are independently chosen development hypotheses, not fitted evidence:
24 per matched liberty, 8 per immobile adjacent defender, 12 for a sole mobile
adjacent defender, minus 4 per vacating attack (maximum four penalties).
Immobility is not necessarily a tactical pin; proximity is not proof that a
piece is an essential defender. Coverage uses current legal movement, not future
placements or a guarantee that several moves can be executed consecutively.

With `ThreatPlies 2`, the bounded forcing search examines actual immediate wins,
defenses against immediate wins, and moves creating an immediate winning threat
when either Queen has at most two liberties. Opponent replies remain adversarial.
It does not prove general long combinations. Search cancellation also interrupts
legal movement generation. Both sides of the development screen use the same
forcing-search configuration; zero-threat production behavior remains unchanged.

`tools/coordination_study.py` pins artifacts and runs a consumed native evaluation
benchmark, twelve timed roots per mode and a mirrored 20-game screen against
plain schema 7. One thread, 16 MiB tables, no pondering, 230 ms internal and
250 ms external deadlines, 160-ply cap. Timeouts are losses. Completed games
are persisted and resumable only with matching identities. The openings have
already been used in development: this is not fresh confirmation or qualification.
Shared locks, Idle priority and the two-hour stage limit remain enforced.

Tests cover D6/translation invariance, score orientation, make/unmake integrity,
depth-one brute-force agreement, terminal precedence and legacy protocol behavior.
No promotion, training, GUI-default change, commit or push is performed.

## Verified development result

The completed screen scored **9/20**: seven natural wins, ten natural losses,
two repetition draws, and one opponent timeout win. Nu had no timeouts.
The maximum observed caller time was 273.292 ms on the opponent timeout;
timeouts are forfeits, not discarded measurements.
The twelve timed roots per mode had no timeouts: completed-depth totals were
30 plain versus 26 coordinated, with 74,531 versus 58,257 nodes.
The native 39-root consumed make/evaluate/unmake benchmark measured 13.9395 ms
plain versus 61.897 ms coordinated, about 4.44x cost. These are aggregate times,
not per-call latency. The candidate is not promoted.
