# MzingaCpp Qualification (Superseded)

This is preserved historical evidence from the removed 24-bot experiment. It
is not a valid architecture comparison: the removed family was learned linear,
CNN training used far fewer optimizer updates, only 16 candidate moves were
sampled, and all models were replaced by a shared queen-pressure chooser after
ply 48.

Run date: 2026-10-03

- Opponent: MzingaCpp v0.9.8, source revision
  `badd1d0c29a5260e20455eb20278d4bf1c934b5f`
- Games per bot: 50
- Move limit: 250 ms wall clock
- Adjudication: draw at 160 plies
- Openings: deterministic paired four-ply random openings
- Colors: mirrored within each opening pair
- Pass condition: score strictly greater than 25/50
- Outcome: 24 of 24 passed
- Protocol/rules forfeits: 0
- Time forfeits: 0
- Slowest observed Genseki move: 87.15 ms

| Bot | Family | Score |
| --- | --- | ---: |
| Alpha | Learned linear (removed) | 38.0 |
| Beta | Learned linear (removed) | 37.5 |
| Gamma | NNUE | 35.5 |
| Delta | NNUE | 38.0 |
| Epsilon | Dense | 38.5 |
| Zeta | Dense | 35.5 |
| Eta | Convolutional | 39.5 |
| Theta | Convolutional | 33.5 |
| Iota | Learned linear (removed) | 38.0 |
| Kappa | NNUE | 37.5 |
| Lambda | Dense | 35.0 |
| Mu | Convolutional | 30.5 |
| Nu | Learned linear (removed) | 38.0 |
| Xi | NNUE | 39.5 |
| Omicron | Dense | 35.5 |
| Pi | Convolutional | 34.0 |
| Rho | Learned linear (removed) | 35.0 |
| Sigma | NNUE | 40.0 |
| Tau | Dense | 39.0 |
| Upsilon | Convolutional | 35.5 |
| Phi | Learned linear (removed) | 37.5 |
| Chi | NNUE | 36.5 |
| Psi | Dense | 37.5 |
| Omega | Convolutional | 33.5 |

Family totals:

| Family | Score | Percentage |
| --- | ---: | ---: |
| NNUE | 227/300 | 75.7% |
| Learned linear (removed) | 224/300 | 74.7% |
| Dense | 221/300 | 73.7% |
| Convolutional | 206.5/300 | 68.8% |

The raw CSV is the authoritative match record. This run is compatibility
history only and must not be used to rank evaluator architectures.
