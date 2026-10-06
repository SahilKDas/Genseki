# Iota

Independent experimental Base-Hive engine. All new work is isolated here;
Alpha is still the default engine. This directory remains ignored by Git.

## Build and test

```powershell
cmake -S Iota -B Iota/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build Iota/build -j 2
ctest --test-dir Iota/build --output-on-failure
python Iota/tests/test_models.py -v
python Iota/tests/test_encoding.py -v
Iota/build/iota.exe --model Iota/work/gnn32.iota
```

Use the installed Python 3.11 NumPy/PyTorch environment. No new dependency
downloads are required. Model-free mode exposes rules/encoding tools but
rejects bestmove: there is no handcrafted scoring fallback.

## Implemented experiment

- C++ native FP32 inference; Python reference and CUDA training.
- Versioned CNN/GNN models at 32/4 and 64/6; existing v1 files remain loadable.
- Full five-level stack encoding, reserves, Queen/turn status, side to move.
- v2 CNN: radius-22 hex domain with D6-tied neighbor kernels. v2 GNN:
  one node per deployed stone, including covered stones, plus empty frontier.
- Win/draw/loss head and complete legal-action scoring.
- Independent iterative-deepening PVS and policy/value PUCT prototypes.
- Four-entry bucket TT, history-context keys, mate normalization, aspiration,
  killer/history ordering, exact immediate wins, bounded static prediction cache.
- Cancellation checks in separately compiled shared rules and native inference.
- One to twelve native inference lanes; default one, not unverified root splitting.
- Atomic corpus, checkpoint, model, partial-match and qualification evidence.
- Resumable optimizer/RNG state with corpus/config identity checks.
- A one-use final qualification marker, created before random final seeds.

## Commands

Protocol commands: info, newgame, validmoves, play, pass, undo, bestmove,
options, exit. Effective options: Search (alphabeta/mcts), Threads (1..12),
HashMB (1..128), Model (native model path). Extensions are not advertised.

Diagnostics: iota-position, iota-loadposition, iota-canonical, iota-index,
iota-encode cnn/gnn/cnn2/gnn2/cnn3, iota-eval, iota-perft 0..4,
iota-divide 1..4, iota-actions, iota-tactics [1..2000 milliseconds],
iota-searchinfo, iota-stats, iota-modelinfo, iota-result and iota-playindex.
Only protocol output goes to stdout; search diagnostics go to stderr.
Loaded diagnostic positions have no opening replay. Use iota-playindex and
undo there; UHP play/pass is rejected instead of emitting a fictitious game
string. Regular newgame/game-string play and undo remain unchanged.

```powershell
python Iota/tools/corpus.py --games 100 --minutes 30 --output Iota/work/corpus.jsonl
python Iota/tools/train.py --corpus Iota/work/corpus.jsonl --architecture gnn --width 32 --blocks 4 --updates 2000 --batch-size 128 --minutes 30 --output Iota/work/candidate.iota
python Iota/tools/bench.py --model Iota/work/candidate.iota --corpus Iota/work/corpus.jsonl --repeats 30 --minutes 5 --output Iota/work/bench.json
python Iota/tools/match.py --model Iota/work/candidate.iota --mode alphabeta --games 20 --minutes 30 --output Iota/work/development.json
python Iota/tools/campaign.py --stage 10000 --updates 2000 --minutes 60
```

The collector uses public Alpha bestmove calls. It records one-hot teacher
preferences, not a fictitious complete policy or numeric teacher evaluation.
Natural outcomes label value; capped games have no outcome value label.
Cross-split transposition bridge games are dropped. Whole-game assignments
follow known transposition groups. Collection resumes with new game seeds.

Match timers request 250 ms from Iota (which reserves 20 ms internally) and
230 ms from Alpha, while enforcing the same 250 ms external deadline for both.
No final qualification should run before the development gates in STATUS.md.

The legacy v1 operators remain available. v2 GNN has five separate relations:
surface hex adjacency, below-to-above, above-to-below, legal movement source
to destination, and its reverse. Relations aggregate with bounded means;
covered stones cannot acquire legal movement links. Stack order, stone type,
color, level and covered status are preserved. Placements use empty-frontier
destination embeddings and reserve/global information in the policy head.

v2 CNN shares one kernel across all six hex directions, plus a separate center
kernel. It uses a symmetric hex domain around a deterministic stone anchor;
the action head uses invariant displacement distance, not raw q/r components.
v3 is an untied-direction CNN control with the same domain, features, heads,
and normalization. Compare v3 with/without augmentation against v2; do not
compare the old rectangular domain and call that a pure symmetry ablation.
Tied weights change parameter counts, which the trial must report separately.

Connected Base Hive has at most 22 occupied hexes. A connected 22-hex set has
axial coordinate spans at most 21; legal destinations are on its adjacent
frontier (including jump landing). Centering therefore fits inside the 45x45
grid with margin. For the modern hex domain, every stone is within 21 steps of
the anchor, and every legal frontier destination is within 22. A stack has at
most five pieces: one original ground piece
plus at most four climbing Beetles. Inputs never truncate legal Base stacks.

Training streams single-position microbatches and accumulates to the requested
effective batch. CUDA allocation is capped at 1.5 GiB. RAM/storage guards and an
exclusive local heavy-job lock apply. Python preflight rejects known concurrent
training/gauntlet commands. All runs have explicit time limits; no automatic
overnight run or monitor is installed.

See STATUS.md for verified results and important incomplete campaign features.

## Decision Learning And Distillation

Training now defaults to version 2. Use --version 1 to resume legacy runs.
--augment transforms all twelve symmetries and explicitly permutes legal-action
targets; it does not assume move-list order is preserved. Corpus indexing is
disk-backed and rejects cross-split source games, opening families and canonical
transpositions. Effective batches still accumulate streamed microbatches.

supervision.py freezes a neural Iota teacher and records completed MCTS root
visit distributions, side-to-move search estimates, and up to eight partial
child-search rankings. These are estimates, not final outcomes or a complete
expert policy. Exact immediate wins and one-reply losses are checked through
legal continuations. Queen-escape and stack-change labels support tactical
sampling; they are not invented winning targets or runtime heuristic scoring.
Timed-out diagnostics and incomplete searches are excluded with reasons.

train.py --teacher-checkpoint uses frozen teacher policy/value KL targets at
temperature 2, alongside available supervised labels and pairwise rankings.
The teacher can be larger and from the other architecture. It never receives
gradients. Unsupervised teacher value heads are not distilled; search-score-only
teachers supervise expected value, while outcome-trained teachers may supervise
WDL distributions. Best checkpoint/native-export pairs are preserved together, and
resume identity includes teacher hash, representation and objective settings.

```powershell
python -B Iota/tools/verify.py
python -B Iota/tools/symmetry_trial.py --corpus Iota/work/corpus.jsonl --minutes 30 --updates 2000 --output-dir Iota/work/symmetry-trial
python -B Iota/tools/distill.py --corpus Iota/work/corpus.jsonl --minutes 60 --teacher-updates 2000 --student-updates 2000 --output-dir Iota/work/distillation-trial
python -B Iota/tools/bench.py --model Iota/work/candidate.iota --corpus Iota/work/corpus.jsonl --search both --threads 1 --repeats 30 --minutes 5 --output Iota/work/full-search-bench.json
```

distill.py trains a 64/6 GNN teacher, optionally collects its search-backed
targets, trains a 32/4 student, then benchmarks both inside PVS and MCTS.
It has an explicit wall budget and does not promote a model. Benchmarks record
legal responses, nodes/depth and external deadline misses. Stronger validation
predictions are not strength evidence; development matches remain necessary.
