# Research Incumbents

`64-linear.json` registers the user-promoted 64-wide linear research incumbent.
It is not the production default or a sealed champion. The previous 64-wide
checkpoint and the 128-wide incumbent remain preserved.

Run `python Nu/tools/incumbent.py --check` to verify the pinned engine/model
hashes, or `python Nu/tools/incumbent.py` to launch that pair over UHP.
Never supply this model alone to another executable.

The original checkout's fast/residual evaluator owns schema 5. The canonical
symmetry evaluator in this registration uses schema 6; it was renumbered after
a collision was found. Its learned payload is unchanged, with feature/score
parity verified on 384 positions and depth-one search parity on 12 positions.
The bundled engine rejects schema 5, and the current fast evaluator rejects
schema 6. These contracts are deliberately not interchangeable.

Registered artifacts are local, hash-pinned files under `Nu/work/incumbents`.
Those binaries and weights remain ignored; committing the registration alone
does not distribute them. Alpha Gen 1 and GUI defaults are unchanged.
