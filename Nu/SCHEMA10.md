# Schema 10: Search Challenger Development

Schema 10 is promoted as a research challenger after meeting the user's
13/20 predecessor gate. It names a search generation, not a new NNUE feature
contract. Candidates retain the trained schema-8 weights. Schema 9, Alpha,
GUI defaults, and existing registrations remain unchanged.

## Qualified Profile

Candidate `search10-v14` scored **13/20** against promoted Schema 9: nine wins,
three losses, and eight adjudicated draws (six ply caps, two repetitions).
It scored **4.5/20** against Alpha Gen 1: two wins, thirteen losses, and five
adjudicated draws (two ply caps, three repetitions). Both mirrored 250 ms
screens completed without timeouts or protocol/rules rejection.

The profile uses eight threads, 16 MiB tables, root PVS, and the deadline guard.
Threat extensions, late-move reductions, coordination ordering, PV-first
scheduling, and pondering are disabled. The selected full-width policy beat
the optional policies in its disjoint development selection; do not attribute
this promotion to the new reduction heuristic.

The exact engine/model pair and portable evidence checksums are registered in
`incumbents/schema10.json`. Check it with:

```powershell
python Nu/tools/incumbent.py --record Nu/incumbents/schema10.json --check
```

Frozen binaries/models remain in the ignored local `work` bundles. Registration
does not replace GUI/Alpha defaults or supply these private artifacts to a fresh
clone. No sealed qualification was run. Fourteen development candidates were
explored; one 20-game pass is not a claim of statistical superiority or Alpha/
Nokamute parity. Failed candidate reports remain available below.

## Changes Under Test

- Nu-only Base-Hive connectivity uses bounded scratch storage for 22 occupied
  cells. Ground and Beetle gates use the two common axial neighbors directly.
  Placement cells are computed once per legal-move generation.
- Optional PV-first root scheduling establishes the previous iteration's
  best-move bound before dispatching remaining scouts. Parallel scheduling is
  retained and compared independently. Exact-result selection and interrupted
  iteration fallback remain required.
- Search workers are reused across iterative depths. Nu-only crawl scratch,
  canonical-frame comparisons, indexed stack heights, and feature-bank sorting
  reduce allocation and reconstruction overhead without changing feature values.
- Runtime-dispatched AVX2 integer accumulator updates retain SSE4.1 and scalar
  fallbacks. Nu-only five-piece inline stacks avoid per-stack heap allocations.
- Development arenas configure the predecessor from its hash-pinned incumbent
  registration, rather than accidentally comparing against its native defaults.

## Verified Evidence

The first candidate, without PV-first scheduling, scored **11/20** against
Schema 9 and **0/20** against Alpha Gen 1. Neither screen had a timeout. It failed
the required 13/20 predecessor gate and remains unpromoted. Sanitized reports are
under `reports/search10-v1`; failed evidence is retained.

The second candidate added PV-first scheduling and selected guarded reductions.
It scored **10.5/20** against Schema 9 and **5/20** against Alpha Gen 1, with no
timeouts in either screen. It also failed promotion. Reports are under
`reports/search10-v2`. Its 6/6 selection result did not transfer to the independent
gate; neither result is omitted.

The third candidate reused search workers across iterative depths and selected
full-width root PVS. It scored **10/20** against Schema 9 and **3.5/20** against
Alpha Gen 1, with no timeouts. It remains unpromoted; see `reports/search10-v3`.

The fourth candidate removed redundant crawl checks and traversal allocations.
It scored **11/20** against Schema 9 and **2.5/20** against Alpha Gen 1, with no
timeouts. Its optional two-ply threat policy scored 1.5/6 in selection and was
not selected. Reports are under `reports/search10-v4`; no promotion was made.

The fifth candidate short-circuited canonical orientation comparisons. Its
benchmark and completed selection evidence are under `reports/search10-v5`.
It did not run a promotion gate: source review found that tied fail-low root
bounds could precede the exact selected PV in the next iteration's ordering.
That ordering was corrected before the next candidate was frozen.

The sixth candidate included the exact-PV ordering correction. Its best
selection policy scored 3/6 and suffered one timeout loss; it did not advance
to a promotion gate. Reports are under `reports/search10-v6`. Earlier clean
timing probes do not establish that all deadline failures are eliminated.

The seventh candidate explicitly compared parallel-root and PV-first schedules.
Its best selection score was 3/6, with no timeouts, and it did not advance.
Reports are under `reports/search10-v7`. The `RootPVFirst` setting is frozen in
new arena identities, checked by the launcher, and excluded from legacy sealed
qualification. Both schedules have fixed-depth score/optimality tests.

The eighth candidate used indexed stack heights and feature-bank sorting. Its
selected parallel, full-width schedule scored **12/20** against Schema 9 and
**5/20** against Alpha Gen 1, with no timeouts. It failed the 13/20 threshold;
see `reports/search10-v8`. A close failure is not a promotion.

The ninth candidate added runtime-dispatched AVX2 accumulator updates, retaining
SSE4.1 and scalar fallbacks. Exact feature/integer tests exercised AVX2 on the
test laptop. Its best selection score was 2.5/6, with no timeouts, and it did
not advance. Reports are under `reports/search10-v9`; throughput is not strength.

The tenth candidate restricted immediate winning-reply simulations to the
Queen's sole empty neighbor, still checking actual terminal results. Eighteen
fixed-depth threat scores matched frozen Schema 9. Its selected full-width
policy scored **8/20** against Schema 9 and **5.5/20** against Alpha Gen 1,
with no timeouts. It failed promotion; see `reports/search10-v10`.

The eleventh candidate added inline Base-Hive stacks. All 20 CTest suites passed;
legal lists, replay, and undo matched the reference on 1,285 positions and 1,280
deterministic random plies. Eighteen threat-search scores matched frozen Schema 9.
The selected guarded-reduction policy scored 4/6 in selection, then **10.5/20**
against Schema 9 and **5/20** against Alpha Gen 1. Both screens had no timeouts.
It failed promotion; see `reports/search10-v11`.

The twelfth candidate widened failed aspiration windows progressively instead
of immediately repeating a full-window search. All 20 suites passed and 18
fixed-depth scores matched Schema 9. Its selected guarded-reduction policy
scored **10.5/20** against Schema 9 and **4.5/20** against Alpha Gen 1, with no
timeouts. It failed promotion; see `reports/search10-v12`. A harness-only depth
check initially rejected early mate completion; that failure is retained under
`work/search10-aspiration-parity-v12`, and the corrected verification is under
`reports/search10-aspiration-parity-v12b`.

The thirteenth candidate discarded only pre-placement history from TT contexts:
Base Hive never removes stones, so those earlier positions cannot recur.
Reversible history and repetition eligibility remain in the context, and undo
restores both. All 20 suites passed; 18 fixed-depth scores matched Schema 9.
Its guarded-reduction policy scored **11.5/20** against Schema 9 and **2.5/20**
against Alpha Gen 1, with no timeouts. It failed promotion; see
`reports/search10-v13`.

The fourteenth candidate broadened optional quiet reductions only in calm
positions. Queen/Beetle moves, enemy-Queen contact, Queen-adjacent departures,
low-liberty positions, TT moves, and killer/counter moves remain protected.
All 20 suites passed, including a depth-4 reduced/full-width score comparison
and defensive search checks. Full-width search nevertheless won selection at
5/6, then passed at **13/20** and scored **4.5/20** against Alpha Gen 1.
Reductions and threat extensions are disabled in the promoted profile. Reports
are under `reports/search10-v14`.

The Nu-only rules changes matched the frozen Schema 9 engine on 1,283 positions
and 1,280 deterministic random plies, including legal lists, replay, undo, and
stack fixtures. The PV-first candidate passed all 20 CTest suites. Its
135-response timing probe had no timeouts. These checks establish neither
strength nor promotion.

Screens use mirrored openings, eight threads, 16 MiB tables, 230 ms internal
requests, 250 ms external deadlines, depth ceiling 64, and a 160-ply cap.
Timeouts lose. Selection and gate opening families are disjoint. No sealed
qualification has been launched.
