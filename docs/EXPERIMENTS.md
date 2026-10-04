# Genseki Experiment Plan

Genseki is a Hive bot lab. The first research target is evaluator evidence, not
vibes:

1. Are NNUE evaluators stronger than dense or convolutional neural evaluators?
2. Are NNUE evaluators stronger than handcrafted evaluators?

## Bot Families

Genseki reserves at most twenty-four bot identities, one per Greek letter from
Alpha through Omega. The active first wave is intentionally small:

- Alpha/Beta: handcrafted evaluator baselines.
- Gamma/Delta: NNUE evaluator candidates.
- Epsilon/Zeta: dense neural evaluator candidates.
- Eta/Theta: convolutional evaluator candidates.

The remaining Greek-letter slots are disabled until the rules engine, search,
and match runner can support larger sweeps without wasting the laptop.

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

The sample CSV exists only to verify the reporting code path. It is not strength
evidence and must not be cited as a real Genseki result.
