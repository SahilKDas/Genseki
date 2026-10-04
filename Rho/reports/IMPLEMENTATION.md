# Rho implementation and smoke validation

Actual smoke/development evidence. No overnight training or strength improvement claim.

Current champion: trained G0, 150,274 parameters, SHA-256 `bbe8b1b65acf0932a2074b18d8cc854dd4f410ecd7c687e0c5de884be80619d1`.

Self-play: 12 games, 964 replay positions; 1 natural result, 11 capped games.

The G0 bootstrap trained policy on capped self-play. Its value head remains without terminal supervision. G2, G3 and G6 received actual terminal value labels. G6 used two worker lanes, 64 simulations, CUDA, batch 128, and a game-separated split keeping terminal examples in training. Only one terminal game exists, so independent terminal value validation is unavailable.

Every completed two-game paired arena scored 50% (two capped draws); all challengers were rejected. Champion bytes match the original trained bootstrap. The retained latest candidate is G6.

A Windows ctypes monitoring race stopped the first two-worker run. It was fixed and its failed campaign JSON/Markdown retained. The subsequent two-worker runs passed. No real OOM occurred; batch backoff was tested with an explicitly injected unit-test OOM.

Observed peak tensor allocation: 61.6 MiB; reserved: 86.0 MiB; main-process working-set peak: 1.40 GiB. Minimum observed available RAM: 3.87 GiB. Workspace at verification: 3.01 MiB.

Tests: see test-results.txt and native-test-results.txt for exact final counts and results. Safety coverage includes promotion byte preservation, corruption detection, state recovery, interrupted arena, a real native-worker deadline, parallel resource checks, and injected OOM recovery.

Unvalidated: eight-hour endurance; full 160-ply/64-simulation throughput; genuine playing-strength improvement; external Nokamute performance; native PVS integration; real GPU OOM and physical reboot. No Nokamute moves or games entered replay.

Run from the repository root after other heavy jobs finish:

```powershell
python -m genseki.rho.campaign --workspace Rho --resume --hours 8 --workers 2 --simulations 64 --replay-positions 200000 --max-plies 160 --train-positions 5000 --sample-positions 10000 --epochs 2 --batch-size 128 --arena-games 40 --device cuda
```

Source: genseki/rho/{core,campaign,status}.py. Workspace: champion/, challenger/, checkpoints/, replay/, reports/, models/, logs/, state.json and config.json. Shared engine sources and gitignore were unchanged; all Rho source, models and evidence remain visible to Git.

Machine-readable full verification is in verification.json; per-generation training/arena evidence and every campaign are preserved alongside it.
