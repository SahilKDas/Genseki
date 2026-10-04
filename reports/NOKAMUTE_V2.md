# Nokamute V2 Development Gauntlet

Run date: 2026-10-04

## Protocol

- Opponent: Nokamute 1.0.3
- Opponent source revision:
  `c9ab65e0d9f496fd8735096ae37babc8bb50a57c`
- Active bots: 18
- Games per bot: 20
- Total games: 360
- Openings: 10 deterministic four-ply seeds, mirrored by color
- Opening seed base: `0x32304741`
- Variant: Base Hive
- Internal move request: 230 ms
- External wall-clock deadline: 250 ms
- Threads: one per engine
- Adjudication: draw at 160 plies
- Player path: full-width one-ply PyTorch evaluation for every architecture

No game produced a rules or protocol divergence. All raw game rows are retained
under `reports/nokamute_v2/`.

## Bot Results

| Bot | Family | Official score | Nokamute timeouts | Ply-cap draws | Timeout-adjusted score |
| --- | --- | ---: | ---: | ---: | ---: |
| Gamma | NNUE | 5/20 | 5 | 0 | 0/15 |
| Delta | NNUE | 0/20 | 0 | 0 | 0/20 |
| Epsilon | Dense | 2/20 | 2 | 0 | 0/18 |
| Zeta | Dense | 4/20 | 4 | 0 | 0/16 |
| Eta | Convolutional | 2/20 | 2 | 0 | 0/18 |
| Theta | Convolutional | 2.5/20 | 2 | 1 | 0.5/18 |
| Kappa | NNUE | 3/20 | 3 | 0 | 0/17 |
| Lambda | Dense | 5/20 | 5 | 0 | 0/15 |
| Mu | Convolutional | 2/20 | 2 | 0 | 0/18 |
| Xi | NNUE | 2/20 | 2 | 0 | 0/18 |
| Omicron | Dense | 4/20 | 4 | 0 | 0/16 |
| Pi | Convolutional | 1.5/20 | 1 | 1 | 0.5/19 |
| Sigma | NNUE | 0/20 | 0 | 0 | 0/20 |
| Tau | Dense | 6/20 | 6 | 0 | 0/14 |
| Upsilon | Convolutional | 0/20 | 0 | 0 | 0/20 |
| Chi | NNUE | 0/20 | 0 | 0 | 0/20 |
| Psi | Dense | 0.5/20 | 0 | 1 | 0.5/20 |
| Omega | Convolutional | 0/20 | 0 | 0 | 0/20 |

## Family Results

| Family | Official score | Nokamute timeouts | Ply-cap draws | Timeout-adjusted score |
| --- | ---: | ---: | ---: | ---: |
| NNUE | 10/120 | 10 | 0 | 0/110 |
| Dense | 21.5/120 | 21 | 1 | 0.5/99 |
| Convolutional | 8/120 | 7 | 2 | 1/113 |
| Total | 39.5/360 | 38 | 3 | 1.5/322 |

## Interpretation

No Genseki bot won a completed game. Thirty-eight of the official points were
Nokamute wall-clock forfeits and the remaining 1.5 points were capped draws.
Therefore the official family ordering is dominated by opponent timeout noise
and is not evidence that dense evaluation is stronger.

The corrected networks learned terminal outcomes substantially better than the
old corpus, but full-width one-ply selection is still far below Nokamute's
iterative search. The next strength experiment must put all supported
evaluators behind the same multi-ply search interface; architecture comparisons
before that change would mostly measure search depth zero versus Nokamute.
