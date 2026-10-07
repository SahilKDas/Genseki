# English Game Review

Choose **Review Game** after finishing a game, or import a Base-Hive replay
with **Load UHP** first. Unfinished imports receive a partial-game label.
Review is initiated explicitly; it never supplies live hints.

The separate review window shows a move list, before/after positions,
highlighted evidence, English explanations, and expandable details. Previous
and next controls navigate the replay. The continuation selector and
**Next in line** preview legal alternatives without editing the original
game. **Reset line** returns to the selected starting position. Original
game clocks and move sounds remain paused during review.

## Evidence

The authoritative Base-Hive rules core validates the entire replay first.
Exact facts include placement, Queen surroundings, covering/uncovering,
stack ownership, the Queen deadline, forced passes, and natural results.
Stones are covered, not captured. Movement restrictions are explained only
when checked against legal movement, connectivity, or Queen sliding gates.

Immediate wins and opponent winning replies use legal enumeration with a
200 ms budget per reviewed position. An interrupted check is unknown, not
proof that a position is safe. Definite tactical explanations retain legal
witness moves. Longer suggestions are estimates and possible continuations,
not forced-loss claims, probabilities, or calibrated mistake classifications.

A separate Alpha process supplies suggestions through its existing
diagnostic interface. Pondering and random opening choices are disabled;
the process uses one thread and a 32 MiB table. Root and continuation
searches share a two-second engine-search allowance per move. Review has a
ten-minute overall budget. Completed explanations remain available when
cancellation, resource limits, or an engine error stop later analysis.

Analysis is deferred when another review holds the workspace job mutex,
available RAM is below 0.5 GiB, or detected engine/training processes exceed
the conservative concurrency guard. Recognized native engines (including
Alpha's backend, Nu, Nokamute, Mzinga, and the rules service) are counted;
active native search is detected using sampled process CPU time. Unknown
CPU-heavy executables inside the project are also detected. The reviewer
excludes its own analysis child by process ID, not executable name. One idle
GUI engine is allowed, so opening review does not block itself. Guards only
defer/stop this review; they never terminate unrelated jobs. Replay navigation
remains available. This is a conservative sampled guard, not a machine-wide
sandbox or a guarantee about arbitrary programs outside the project.

## Command Line

```powershell
.\build\genseki_review.exe --input game.txt --output review.json
.\build\genseki_review.exe --input game.txt --output facts.json --facts-only
```

Input is a Base-Hive UHP game string. The default engine is the reviewer's
sibling `genseki.exe`; `--engine` can select an Alpha executable explicitly.
Interrupting analysis retains the latest completed explanations. Exports
use atomic replacement and schema version 1, recording replay, hashes,
effective review settings, structured facts, witnesses, and completion
status. They exclude engine paths and raw subprocess diagnostics.

## Verified Checks

The review test suite exercises replay rejection, score perspective,
illegal suggestions, cancellation, resource deferral, partial results,
covered Queens, stack changes, forced pass, placement deadlines, hive
connectivity, immediate wins, winning replies, simultaneous-surround draws,
uncertain interrupted checks, SHA-256, and privacy-safe JSON.

The native review-window smoke test analyses an imported four-move replay,
navigates it, validates suggested lines, checks replay immutability, exports
JSON, and captures nonblank views at 96 and 144 DPI. The GUI isolation test
checks that opening review does not change the live board/history, clocks,
engine-request state, or queued sounds. Transport tests exercise ineffective
options, illegal moves, malformed output, process exit, and stalled-process
cancellation. Budget tests include in-flight search cancellation.

Dedicated tests cover equivalent replay aliases, an independently enumerated
unique immediate defense, and closed Queen sliding gates. The acceptance
evidence audit replays each claim's source position, regenerates rule facts,
checks witnesses and suggested lines, and matches every fact/explanation
sentence to those templates. Mutation tests reject invented sentences,
altered rule descriptions, and unsupported mandatory-defense certainty.
This is a consistency check against the authoritative rules core, not an
independent second implementation of Hive's rules.

A real Alpha integration run completed all 16 moves of a naturally finished
Base-Hive fixture, with a matching executable hash and a path-free JSON
export. `genseki_review_flow` uses the GUI's shared import and Review Game
handlers, real Alpha inference, navigation, evidence audits, and a native
Cancel-button click during a partial imported review. It checks original
history/clocks and partial exports, and captures layouts at 96, 120, 144,
and 192 DPI. Native resource tests launch an owned CPU-heavy test executable,
verify deferral, and terminate only that fixture. These are automated native
control tests, not a claim that a human manually clicked through the GUI.
