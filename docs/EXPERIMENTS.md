# Genseki Experiment Plan

Genseki is a Hive bot lab. The first research target is evaluator evidence, not
vibes:

1. Are NNUE evaluators stronger than dense or convolutional neural evaluators?
2. Are NNUE evaluators stronger than handcrafted evaluators?

## Bot Families

Genseki trains all twenty-four bot identities, one per Greek letter from Alpha
through Omega. Each consecutive group of four rotates through handcrafted,
NNUE, dense, and convolutional evaluators. The six groups use search-depth
profiles one through six.

Every model was trained for 12 epochs from the same deterministic 128-game
corpus on an NVIDIA GeForce MX550 through PyTorch CUDA 13.0. The final corpus
contains 4,701 positions, 61 naturally terminal games, and 67 bounded
adjudications. See `models/frozen/manifest.json` for seeds, hashes, metrics,
architectures, and artifact paths.

## Qualification Result

All 24 bots passed the required 50-game, 250 ms gauntlet against MzingaCpp
v0.9.8. Games use paired randomized four-ply openings, mirrored colors, a
160-ply adjudication cap, and strict wall-clock forfeits. Full game rows are in
`reports/mzinga_gauntlet.csv`; the compact audit is
`reports/QUALIFICATION.md`.

| Evaluator | Score | Percentage |
| --- | ---: | ---: |
| NNUE | 227/300 | 75.7% |
| Handcrafted | 224/300 | 74.7% |
| Dense | 221/300 | 73.7% |
| Convolutional | 206.5/300 | 68.8% |

On this run, NNUE beat both comparison families, but its lead over handcrafted
and dense evaluation is small. This is evidence for the next experiment, not a
generational claim yet. MzingaCpp v0.9.8 chooses its first legal move for
`bestmove`, and every Genseki family shares the same tactical closer, so a
stronger external opponent and direct family-vs-family round robin remain
necessary.

## Evidence Rules

- Every promoted bot needs a frozen source commit, config, model identity, and
  match report.
- Arena matches should use mirrored colors and bounded game counts.
- Evaluator-family claims come from aggregate family results, not one lucky bot.
- Handcrafted functions remain the sanity baseline until neural evaluators beat
  them under equal search and time controls.

## Reporting Pipeline

Generate a manifest and mirrored pairing schedule:

```powershell
python -m genseki.experiments --out reports/manifest.json --pairings reports/pairings.csv
```

Summarize an arena CSV:

```powershell
python -m genseki.report data/samples/arena_results.csv
```

The sample CSV exists only to verify the reporting code path. The Mzinga
qualification CSV is the real baseline evidence.
