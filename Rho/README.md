# Rho

New policy/value reinforcement learning system; unrelated to the retired learned-linear bot.

Run from the repository root with Python 3.11+, installed NumPy/PyTorch and
`build/genseki.exe`. The native executable remains the rules authority.

```powershell
python -m genseki.rho.campaign --workspace Rho --resume --hours 8 --workers 2 --simulations 64 --replay-positions 200000 --max-plies 160 --train-positions 5000 --sample-positions 10000 --epochs 2 --batch-size 128 --arena-games 40 --device cuda
```

Finish other heavy training/gauntlets before starting the overnight campaign.
The first overnight campaign stopped before completing its eight-hour window:
G8 trained on CUDA, but its promotion arena stopped at the 2 GiB available-RAM
floor. See [reports/OVERNIGHT_SUMMARY.md](reports/OVERNIGHT_SUMMARY.md).

```powershell
python -m genseki.rho.status --workspace Rho
python -m genseki.rho.campaign --workspace Rho --resume --dry-run
python -m genseki.rho.campaign --workspace Rho --resume --smoke-test
python -m unittest discover -s Rho/tests -v
ctest --test-dir build --output-on-failure
```

For a fresh workspace omit `--resume`. Resume retains saved settings; explicit
options override them. Smoke settings are recorded in smoke-config.json and
campaign reports; config.json keeps the overnight defaults after smoke.

| Path | Meaning |
| --- | --- |
| champion/rho.pt | Canonical current trained model |
| checkpoints/G0.pt | Immutable random precursor |
| checkpoints/G0-trained.pt | Immutable trained bootstrap |
| checkpoints/Gn.pt | Immutable promoted generations |
| challenger/rho.pt | Latest candidate, including rejected candidates |
| replay/*.json.gz, index.json | Hashed compressed game shards and FIFO manifest |
| state.json, state.backup.json | Champion pointer, lineage, attempts, phase, counters |
| config.json | Overnight configuration |
| reports/ | Campaign JSON/Markdown, training/arena reports, test evidence |
| models/, logs/ | Reserved for exports and logs; no uncontrolled raw logs |

Each replay example contains native position and game strings, complete legal
move identifiers, search visit counts, side, game identity and terminal value.
Policy is normalized root visits. Value is +1/0/-1 from the player-to-move
perspective. Ply-cap games have a null value target and train policy only;
arenas score caps as explicitly recorded draws. There is no heuristic
adjudication. Whole-game validation separation prevents adjacent-position
leakage. Terminal/capped games are split separately, keeping at least one
terminal game in training. With only one terminal game, independent value
validation is unavailable and its labeled count is explicitly zero. The initial
smoke bootstrap's value head is unsupervised until terminal
data trains a challenger that passes promotion.

Self-play uses root Dirichlet noise (alpha .3, weight .25), temperature 1 through
ply 23 and .5 afterward. Evaluation has no noise and takes the most visited move.
Search counts are real simulations, not depth claims. No adaptive simulation
reduction is currently performed. Both arena players have the same simulation
budget, configurable move ceiling (30 seconds by default; 120 seconds in the
overnight recovery) and campaign deadline; native protocol responses
have a five-second maximum. A move timeout aborts the arena and prevents
promotion. Openings are deterministic four-ply legal random openings shared by
each color pair. A >=60% score is a development heuristic, with no Elo or
statistical certainty claim.

On interruption, incomplete games are discarded, committed replay remains,
and an interrupted arena cannot promote. Resume starts a fresh generation
instead of continuing a partial optimizer or arena. A file lock prevents two
Rho runners using this workspace. Model writes are verified before rename;
state commits select immutable champion bytes. Recovery restores canonical
bytes from the authoritative pointer and removes partial temporary files.
Replay corruption fails closed and is retained as failure evidence. Resume
does not silently fall back from a corrupt authoritative champion.

FIFO replay eviction cleans old shards; uncommitted shards and partial model
files are cleaned on recovery. The latest rejected candidate is overwritten by
the next verified candidate, while all rejection summaries remain. Champion
lineage and reports are never evicted. If retained evidence approaches the
workspace limit the campaign stops before the cap rather than deleting lineage.
GPU OOM halves the batch size and retries, down to one; failure then stops with
the champion preserved. Resource floors stop work safely; resume after freeing
memory. Deadline checks occur during each simulation, native command and
minibatch. Shutdown/report flush and a running GPU kernel can add a small exit
latency; no new generation launches after expiration.

See [AUDIT.md](AUDIT.md) for architecture/reuse decisions and held-out benchmark
policy. See reports/latest.md and state.json for actual outcomes. Scientific
limits: small smoke corpus and arena, no established strength improvement,
no native PVS adapter, no Nokamute probe, and no successfully completed
eight-hour endurance test.
