# Schema 9: Qualified Research Search Profile

Schema 9 names the promoted **research search generation**, not a new NNUE
feature schema. It uses the unchanged trained schema-8 model and exact feature,
prior, integer-inference, and score contract. No weights were retrained or
relabeled. GUI/Alpha defaults and the previous 64-wide registration are unchanged.

## Qualified Configuration

Eight CPU threads, 16 MiB table, pondering off, deadline guard on, root PVS on,
guarded late-move reductions on, threat extensions off, cooperative ordering off.
The registered engine/model pair and settings are hash-pinned in
`incumbents/schema9.json`. Launch the research profile with:

```powershell
python Nu/tools/incumbent.py --record Nu/incumbents/schema9.json
```

The launcher verifies local artifacts and configures the frozen UHP settings.
Models/binaries remain in ignored work storage; missing or altered artifacts
fail explicitly. Native feature diagnostics correctly continue reporting schema 8.

## Changes

- The deadline guard reserves 35 ms of a 230 ms request for cancellation,
  unwinding, joining, destruction, and reply preparation. The external deadline
  remains 250 ms. Cancellation propagates to other workers immediately, and
  legal-generation checkpoints check the deadline more frequently.
- Reply notation for an engine-generated move avoids regenerating the full legal
  list. The public checked notation API still validates arbitrary input.
- `nu-timing` exposes setup, joining, search/cleanup, deadline lag, and formatting
  costs. It does not promise hard real-time scheduling on Windows.
- Root PVS shares exact lower bounds across lanes. Fail-low root results are
  upper bounds and cannot be selected as exact PVs. Failed high probes re-search
  at full depth/window; interrupted iterations retain the last completed result.
- Reductions exclude all moves in positions where either Queen has at most two
  liberties, protecting remote defensive moves as well as Queen-adjacent tactics.
- Opt-in cooperative ordering recognizes executable surrounds, mandatory
  defenses, and pinned defenders. Development evidence did not select it; it is
  not silently enabled in the promoted profile.

## Strength Evidence

Each screen used ten deterministic four-ply openings with colors reversed,
230 ms internal requests, 250 ms external deadlines, eight threads, 16 MiB
tables, depth ceiling 64, and a 160-ply cap. Timeouts always lose. Gate opening
families were separate from selection openings and prior failed gates.

| Candidate | Frozen Schema 8 | Alpha Gen 1 | Timeout Forfeits |
| --- | ---: | ---: | ---: |
| First candidate: guard + extensions + reductions | 6/20 | 2.5/20 | 0 |
| Selected root-PVS + guarded-reduction candidate | **15.5/20** | **1/20** | 0 |

The promoted gate had 15 natural games (13 wins, two losses), three capped draws,
and two repetition draws. Its Alpha screen had 18 natural losses and two
repetition draws. Both runs completed without reconstructed-board/protocol
rejection. Public reports retain all failures and per-game moves/search evidence
under `reports/search9-v1` and `reports/search9-v2`, with host paths removed.

The second candidate meets the user's **at least 13/20 versus its predecessor**
research promotion criterion. It does **not** establish Alpha/Nokamute parity,
supersede the sealed 100-game champion gate, or justify a GUI-default change.
This is a small development result, not a statistically established general
strength claim. Failed candidates and weak Alpha results are not excluded.

## Verification

State/search suites cover mate selection, remote defense, make/unmake,
cancellation, worker independence, root-PVS score and selected-move optimality
against full-width search at one/two/eight threads, and checked/trusted notation
parity. Protocol, artifact, leakage, arena-resume, and export-redaction tests
remain included. Each candidate's 135-response timing probe had no timeouts;
the first used the previous five actual timeout positions plus four baseline
roots. All settings and binary/model/opening hashes are frozen in the reports.

Legacy sealed qualification explicitly rejects these newer profiles until its
configuration protocol is updated and separately verified. No sealed openings
were revealed and no final qualification was launched.
