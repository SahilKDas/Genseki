# Alpha black-box contracts

Alpha is an independent implementation. Reference behavior is captured through
public UHP input/output and replayable game strings; upstream implementation
details are not part of the contract.

## Stable Alpha surface

- Startup emits engine id, supported expansions, then `ok`.
- Every command response terminates with `ok`, including errors.
- Search and perft never mutate the current game.
- `bestmove` returns a member of `validmoves`.
- `alpha-searchinfo` reports the last fully completed depth, score, nodes,
  elapsed seconds, and a PV that can be replayed from the current position.
- `perft N` returns the exact leaf count at depth N.
- Base opening perft is 1, 4, 96 at depths 0, 1, and 2.
- Options use UHP semicolon records and reject values outside their bounds.

Executable transcripts for these contracts live in `tests/contracts.py` and
`tests/smoke.py`.

## Reference boundary

The intended reference is Nokamute commit
`7e5cdf2ebdf3e5fc3a64ad18165e289a0e2675b5`. The locally available source and
binary are from a different revision. They remain useful as a secondary rules
oracle, but their behavior must not silently replace the pinned contract.

On 2026-10-04, the available binary matched Alpha for all eight Base games
through 40 plies. A Base+MLP replay diverged at ply 32 after:

`wS1;bM -wS1;wM wS1/;bA1 /bM;wL wM-;bS1 /bA1;wQ wL/;bQ /bS1;wG1 \\wM;bL -bS1;wG1 wM\\;bL bS1\\;wS2 wL\\;bS2 bL\\;wB1 wG1\\;bG1 bQ\\;wB2 \\wM;bG2 bS2-;wA1 wQ/;bA2 bG2\\;wP wA1/;bP /bQ;wA2 wS2\\;bG1 -bP;wS2 wP\\;bB1 bQ\\;wA2 bA1\\;bA3 -bQ;wA2 /wB2;bA2 bB1\\;wS2 wS2/;bB2 -bS1`

Alpha treated the resulting position as terminal while the available oracle
listed legal moves. This replay is evidence to resolve against the exact pinned
revision, not permission to guess.
