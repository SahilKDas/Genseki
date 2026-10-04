# Neural Retraining V2

Run date: 2026-10-04

## Corpus

- Generator: corrected terminal-outcome-only self-play
- Requested games: 4,096
- Naturally terminal games: 2,110
- Capped games: 1,986; contributed no training rows
- Total labeled positions: 68,627
- Training positions: 54,602
- Held-out positions: 14,025
- Split unit: whole source game
- Dataset SHA-256:
  `181b5b6ceb57cc89c431530ce0953948404d81c2d74123257c3019e86bac497b`
- Labels: 33,058 white wins, 34,906 black wins, 663 draws
- Label provenance: `terminal_outcome` for every row

## Training

- Active bots: 18
- Families: six NNUE, six dense, six convolutional
- Epochs: 12
- Batch size: 512 for every family
- Device: NVIDIA GeForce MX550 through PyTorch CUDA
- Output: `models/retrained-v2`
- Manifest SHA-256:
  `75cbbe99bbe4b201f27fe30f0c11945f7740b0793e17951aeffd05889d556908`

The run began before the 1.5 GiB VRAM ceiling became binding. It was not
interrupted or restarted. Observed device usage was 241 MiB near the end of the
run. Future sessions enforce the ceiling through `--max-vram-gib 1.5`.

## Held-Out Metrics

| Family | Bots | Mean sign accuracy | Mean MAE | Mean training seconds |
| --- | ---: | ---: | ---: | ---: |
| NNUE | 6 | 72.0% | 0.64 | 19.70 |
| Dense | 6 | 71.1% | 0.62 | 18.79 |
| Convolutional | 6 | 72.1% | 0.65 | 49.00 |

These are correlated position-level metrics from game-grouped held-out data.
They are useful training diagnostics, not playing-strength conclusions.

All six NNUE models were also exported to the native `.nnue` format. The
requested 40-game Nokamute gauntlets are pending explicit user authorization;
no partial gauntlet report is retained.
