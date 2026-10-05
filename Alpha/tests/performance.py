"""Paired, bounded performance/behavior gate; never a strength claim."""
import argparse
import json
import random
import statistics
from pathlib import Path

from gauntlet import Engine, digest


def configure(engine, threads):
    for text in (f"options set NumThreads {threads}", "options set TableSizeMiB 32",
                 "options set RandomOpening False", "options set BackgroundPondering False"):
        answer, _ = engine.command(text)
        assert answer and not answer[0].startswith("err"), answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    paths = [args.baseline.resolve(), args.candidate.resolve()]
    engines = [Engine([str(path), "uhp"]) for path in paths]
    rng = random.Random(0xA1FA2026)
    positions = ["Base"]
    records = []
    try:
        for engine in engines:
            configure(engine, 1)
            engine.command("newgame Base")
        for ply in range(32):
            answers = [engine.command("validmoves")[0][0].split(";") for engine in engines]
            assert set(answers[0]) == set(answers[1]), "rules divergence"
            move = rng.choice(sorted(answers[0]))
            states = [engine.command("play " + move)[0][0] for engine in engines]
            assert states[0] == states[1], "state divergence"
            if (ply + 1) % 4 == 0:
                positions.append(states[0])
            if ";InProgress;" not in states[0]:
                break
        for position in positions:
            legal_sets = []
            for engine in engines:
                engine.command("newgame " + position)
                legal_sets.append(set(engine.command("validmoves")[0][0].split(";")))
            assert legal_sets[0] == legal_sets[1]
            times = [[], []]
            moves = [[], []]
            for trial in range(args.rounds):
                for index in ([0, 1] if trial % 2 == 0 else [1, 0]):
                    # Reload for each measurement to avoid warm-table bias.
                    engines[index].command("newgame " + position)
                    reply, ms = engines[index].command(f"bestmove depth {args.depth}", 30)
                    assert reply[0] in legal_sets[index], reply
                    moves[index].append(reply[0])
                    times[index].append(ms)
            # Upstream shuffles root moves even with one worker; tied choices vary.
            records.append({"position": position, "moves": moves, "ms": times,
                            "baseline_median_ms": statistics.median(times[0]),
                            "candidate_median_ms": statistics.median(times[1]),
                            "same_move_set": set(moves[0]) == set(moves[1])})
        deadline_records = []
        for threads in (1, 2):
            configure(engines[1], threads)
            for position in positions:
                engines[1].command("newgame " + position)
                legal = set(engines[1].command("validmoves")[0][0].split(";"))
                reply, ms = engines[1].command("bestmove seconds 0.230", 2)
                assert reply[0] in legal
                deadline_records.append({"threads": threads, "ms": ms, "move": reply[0]})
        report = {"hashes": [digest(p) for p in paths], "seed": "0xA1FA2026",
                  "depth": args.depth, "rounds": args.rounds, "records": records,
                  "deadline_records": deadline_records,
                  "summed_median_speedup": sum(r["baseline_median_ms"] for r in records)
                  / sum(r["candidate_median_ms"] for r in records)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"positions": len(records), "speedup": report["summed_median_speedup"],
                          "max_response_ms": max(r["ms"] for r in deadline_records)}))
    finally:
        for engine in engines:
            engine.close()


if __name__ == "__main__":
    main()
