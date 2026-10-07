# Repository audit and implementation decisions

Inspected clean HEAD `b8611fdd30370515c2040836426c8070660696c1` and the six
commits from `2e84963` through `b8611fd`. There is no applicable AGENTS.md.

The rules, position/game serialization, complete legal successor enumeration,
make/unmake, perft and UHP tests are native C++. Existing Python training uses
128-feature evaluators and has a documented corrected terminal-only corpus.
Existing native PVS consumes a specific single-layer NNUE binary format.
The Rho network cannot honestly be exported to that incompatible format.
Its `evaluate_value(positions)` interface returns player-to-move values; a future
native adapter must convert these to the white-relative convention at the
native static-evaluation boundary. No PVS speed or strength claim is made.

The local ignored Alpha directory is a separate clean-room engine experiment,
with its own rule-compatibility caveats and an active benchmark when this work
began. Rho does not import Alpha, Nokamute, historical Greek models, old labels,
or their game records. User authorization allowed a bounded Rho smoke run to
overlap that benchmark. Its processes and binaries were left untouched.

The Nokamute gate pins release 1.0.3, source revision
`c9ab65e0d9f496fd8735096ae37babc8bb50a57c`, executable hash
`57c3fd7c99aec434dad68130c4f8ff784311ae5a930cc20491f08dd1a580df70`, symmetric
one-thread search, mirrored openings, and fail-closed protocol checks. Rho
reuses its bounded-response UHP process transport. Nokamute probing is disabled;
no Rho gate adapter or external benchmark was run. Existing gate constraints
are unchanged.

Plan executed: build a shared piece-state encoder and legal-successor scorer;
implement signed PUCT and full-game neural self-play; add rolling compressed
replay and game-separated minibatch training; pair deterministic arena openings;
require completed arena evidence for promotion; preserve immutable champion
checkpoints and atomic manifests; add resource/time guards, resume/status,
tests, real training and retained campaign reports.

Architecture: a 136-input MLP with two 256-unit shared layers, 64-unit value
head and a 64-unit scorer of concatenated current/successor embeddings.
150,274 parameters. Every legal successor is scored; there is no fixed invalid
action space. Piece coordinates are translated to the hive center and are
unclipped; all pieces and covered stack levels remain represented. No pressure
heuristic is used as a feature, target or closer. A small MLP reuses native
serialized states and avoids graph/convolution runtime dependencies.

G0 construction preserves a random precursor and a separately hashed trained
bootstrap. G0's first corpus was capped, so its value head has no terminal-result
supervision yet. G1 and later must pass the paired arena; a failed challenger
never replaces G0. All initialization and promotion events remain in lineage.

Resource budget: one PyTorch thread; at most two self-play lanes and two native
rule processes, CPU inference, one training process, Windows Idle priority,
2 GiB available RAM floor and 1 GiB emergency floor, 1.5 GiB CUDA allocator cap,
2 GB workspace with 16 MB reserved headroom. Training and arenas do not overlap
self-play. Existing build/.tmp/models storage measured approximately 6.8 MB
before training. No dependency download or engine rebuild was needed.
