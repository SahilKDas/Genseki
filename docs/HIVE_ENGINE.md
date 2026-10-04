# Hive Engine

Genseki implements regular, expansion-free Hive. The rules core is the sole
authority used by command-line tools, UHP, tests, and future bots and GUIs.

## Rules

- The first piece is placed at axial coordinate `(0, 0)`. A Queen may not be
  either player's first piece.
- Later placements must touch a friendly top piece and no enemy top piece,
  except Black's first placement, which necessarily touches White's opener.
- A player's Queen must be placed on or before that player's fourth turn.
  Pieces cannot move until their own Queen has been placed.
- Lifting a piece may not disconnect the occupied cells. Only the top piece of
  a stack can move.
- Ground movement obeys the two-neighbor sliding gate. Beetle gates use the
  height needed to clear the source, destination, and two flanking stacks.
- Queens slide one step. Spiders slide exactly three non-repeating steps.
  Beetles move one step and may climb. Grasshoppers jump over one or more
  occupied cells in a straight line. Ants slide to every reachable perimeter
  cell.
- A side with no placement or movement receives exactly one legal `pass`.
- Surrounding one Queen wins; surrounding both Queens on the same move draws.

Coordinates are axial `(q, r)` with neighbors `(1,0)`, `(1,-1)`,
`(0,-1)`, `(-1,0)`, `(-1,1)`, and `(0,1)`. Stacks are stored bottom
to top.

## UHP

With no arguments, `genseki` is a line-oriented Universal Hive Protocol
engine. It prints:

```text
id Genseki v0.1.0
ok
```

The engine supports the complete base-game command set and standard relative
move notation. UHP game strings are replayed move by move and rejected if a
move, state field, or turn field is inconsistent. Expansion game types are
rejected because Genseki currently advertises no expansion capabilities.

`bestmove depth N` and `bestmove time hh:mm:ss` validate the requested
limit and currently return the first deterministic legal move. This is a
protocol-correct baseline that will be replaced by the Greek bot search.

The UHP grammar follows the [Universal Hive Protocol specification](http._//github.com/jonthysell/Mzinga/wiki/UniversalHiveProtocol).

## Validation

Initial-position base-game perft was checked against Mzinga's published table:

| Depth | Nodes |
| ---: | ---: |
| 0 | 1 |
| 1 | 4 |
| 2 | 96 |
| 3 | 1,440 |
| 4 | 21,600 |
| 5 | 516,240 |

The permanent suite keeps depths 0-3 as fast golden tests. Deeper counts are
available through `--perft`. `--stress N` plays deterministic random legal
moves and verifies that every make/unmake restores the exact serialized state.

## State Invariants

- Stack cells are unique and sorted; pieces in each stack are bottom-to-top.
- Piece identities use UHP order-of-play names such as `wA1` and `bB2`.
- Legal move output is deterministic and same-type reserve pieces produce one
  canonical placement branch.
- Checked play rejects illegal and post-terminal moves.
- Search may use `make_move` and `unmake_move`; public replay uses checked
  `play`.
- No repetition or move-count draw is added to the game rules.
