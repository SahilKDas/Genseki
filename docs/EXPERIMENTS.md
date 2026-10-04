# Genseki Experiment Plan

Genseki is a Hive bot lab. Its current research target is:

1. Are NNUE evaluators stronger than dense or convolutional neural evaluators?

## Bot Families

Genseki has eighteen active bot identities: six NNUE, six dense, and six
convolutional evaluators. The learned-linear bots Alpha, Beta, Iota, Nu, Rho,
and Phi were removed after the audit below. The remaining families use
search-depth profiles one through six.

The retained historical neural artifacts and removed linear artifacts were
trained for 12 epochs from a deterministic 128-game legacy corpus on an NVIDIA
GeForce MX550. That corpus contained 61 naturally terminal games and 67
heuristic adjudications. The corrected generator emits
training rows only for naturally terminal games, labels them with the actual
win/draw outcome, and tags every row `terminal_outcome`. The trainer rejects
legacy or heuristic-labelled datasets. A new manifest will be produced only
after all three retained families are retrained from a corrected corpus.

## Superseded Mzinga Run

The historical 24-bot roster passed a 50-game, 250 ms gauntlet against MzingaCpp
v0.9.8. Games use paired randomized four-ply openings, mirrored colors, a
160-ply adjudication cap, and strict wall-clock forfeits. Full game rows are in
`reports/mzinga_gauntlet.csv`; the compact audit is
`reports/QUALIFICATION.md`.

| Evaluator | Score | Percentage |
| --- | ---: | ---: |
| NNUE | 227/300 | 75.7% |
| Learned linear (removed) | 224/300 | 74.7% |
| Dense | 221/300 | 73.7% |
| Convolutional | 206.5/300 | 68.8% |

This table is retained for provenance, not as valid architecture evidence.
MzingaCpp v0.9.8 selected its first legal move. The family originally called
"handcrafted" was actually a trained `Linear(128, 1)` model. CNNs received one
full-batch optimizer update per epoch while other models received roughly eight
minibatch updates. The player sampled at most 16 legal moves, then stopped using
its model entirely after ply 48 and switched to a shared queen-pressure closer.

The dataset was also circular: self-play move choice and adjudicated labels were
both dominated by queen pressure. Its 4,701 rows came from 128 games and are not
4,701 independent strategic outcomes. Consequently the old family percentages
do not establish that NNUE is stronger than either neural alternative.

The corrected code uses equal minibatch sizing, evaluates every legal move for
the whole game, and has no shared late-game closer. All retained families must
be retrained before the architecture comparison is rerun.

That retraining completed on 2026-10-04 with 68,627 terminal-outcome positions,
a whole-game train/test split, and batch size 512 for every family. See
`reports/RETRAINING_V2.md`. The 40-game-per-bot Nokamute comparison remains
pending and no strength conclusion is drawn from training metrics alone.

## Nokamute Champion Gate

Nokamute 1.0.3 is now the promotion benchmark. The native search and one-shot
qualification harness are implemented, but no bot has been promoted: all six
NNUE candidates and the native heuristic control lost both colors of an initial
non-final opening probe. See `reports/NOKAMUTE_DEVELOPMENT.md` for the result
and `docs/NOKAMUTE_GATE.md` for the pinned opponent and exact gate.

This supersedes the old interpretation that passing Mzinga's first-legal player
demonstrated ecosystem strength. Those results remain useful compatibility
evidence; they do not count toward champion promotion.

## Evidence Rules

- Every promoted bot needs a frozen source commit, config, model identity, and
  match report.
- Arena matches should use mirrored colors and bounded game counts.
- Evaluator-family claims come from aggregate family results, not one lucky bot.
- The native manually weighted heuristic is only a search sanity control; it is
  not one of the Greek evaluator families.

## Reporting Pipeline

Generate a manifest and mirrored pairing schedule:

```powershell
python -m genseki.experiments --out reports/manifest.json --pairings reports/pairings.csv
```

Summarize an arena CSV:

```powershell
python -m genseki.report data/samples/arena_results.csv
```

The sample CSV exists only to verify the reporting code path. The Mzinga CSV is
preserved compatibility history and is not architecture-ranking evidence.
