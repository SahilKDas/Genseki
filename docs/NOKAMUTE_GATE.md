# Nokamute Champion Gate

Nokamute is Genseki's strength benchmark. MzingaCpp remains the independent
rules and UHP compatibility reference; its first-legal-move player is not a
promotion opponent.

## Pinned Opponent

- Release: Nokamute 1.0.3
- Source revision: `c9ab65e0d9f496fd8735096ae37babc8bb50a57c`
- Windows archive SHA-256:
  `8a629cc070f57bd5444d9faef5d143976de474cc6dcb2e63bba2788dfe4492e0`
- Extracted `nokamute.exe` SHA-256:
  `57c3fd7c99aec434dad68130c4f8ff784311ae5a930cc20491f08dd1a580df70`
- Invocation: `nokamute.exe uhp`
- Options: `RandomOpening=False`, `NumThreads=1`, `TableSizeMiB=100`
- Move command: `bestmove depthorseconds 99 0.230`

The one-thread setting is intentional and symmetric. Genseki's current native
search is deterministic and single-threaded; advertising unused worker lanes
would give Nokamute an asymmetric allowance. The device contract permits up to
12 threads, so a future root-parallel implementation may freeze a new symmetric
configuration at any value from 1 through 12.

## Qualification Contract

- Base Hive only, with no expansions.
- 100 games from 50 deterministic four-ply openings, mirrored by color.
- 230 ms internal search limit and 250 ms external UHP response deadline.
- 160-ply cap; capped games are draws and reported separately.
- Win = 1 point, draw = 0.5, loss/illegal move/timeout = 0.
- Promotion requires strictly more than 55 points. Exactly 55 fails.
- Any rules or protocol divergence aborts the run instead of scoring it.
- Each row records color, seed, result, termination, maximum move times,
  completed depth, nodes, and final principal variation.

The harness uses Genseki itself as an independent referee. Both players receive
the same opening and every move; rejection by either implementation aborts the
run.

## Freeze And Run

Development matches may be repeated on development seeds:

```powershell
python -m genseki.nokamute_gate Sigma `
  --engine build\genseki.exe --model models\frozen\sigma.nnue `
  --nokamute .tmp\nokamute\bin\nokamute.exe --games 20 `
  --threads 1 --opening-seed 0x44455631 `
  --output reports\work\sigma-development.csv
```

Only freeze a candidate after development evidence projects above 55%:

```powershell
python -m genseki.nokamute_gate Sigma --freeze `
  --freeze-manifest models\champion\nokamute-freeze.json `
  --engine build\genseki.exe --model models\frozen\sigma.nnue `
  --nokamute .tmp\nokamute\bin\nokamute.exe --threads 1
```

The final run validates every frozen hash and setting, requires exactly 100
games, and refuses to overwrite an existing report:

```powershell
python -m genseki.nokamute_gate Sigma --phase final `
  --freeze-manifest models\champion\nokamute-freeze.json `
  --engine build\genseki.exe --model models\frozen\sigma.nnue `
  --nokamute .tmp\nokamute\bin\nokamute.exe --threads 1 `
  --opening-seed FINAL_SEED --output reports\nokamute-final.csv
```

No final run is authorized merely because the tooling exists. A failed final is
retained as evidence and is never rerun with the same sealed seed set.
