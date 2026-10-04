"""Mirrored Base-Hive gauntlet between isolated Alpha and a UHP opponent."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import queue
import random
import subprocess
import threading
import time
from pathlib import Path


class Engine:
    def __init__(self, command: list[str]):
        self.command_line = command
        self.proc = subprocess.Popen(command, text=True, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=1)
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.response(5.0)

    def _read(self):
        assert self.proc.stdout
        for line in self.proc.stdout:
            self.lines.put(line.rstrip("\r\n"))
        self.lines.put(None)

    def response(self, timeout: float):
        deadline = time.perf_counter() + timeout
        out = []
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError from error
            if line is None:
                raise RuntimeError(f"engine exited: {self.command_line}")
            if line == "ok":
                return out
            out.append(line)

    def command(self, text: str, timeout=5.0):
        assert self.proc.stdin
        started = time.perf_counter()
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()
        return self.response(timeout), (time.perf_counter() - started) * 1000

    def close(self):
        if self.proc.poll() is None:
            try:
                assert self.proc.stdin
                self.proc.stdin.write("exit\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=2)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.proc.kill()


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_game(alpha_path: Path, opponent_path: Path, game: int, seed: int,
             threads: int, table: int, internal_ms: int, external_ms: int,
             cap: int):
    referee = Engine([str(alpha_path), "uhp"])
    alpha = Engine([str(alpha_path), "uhp"])
    opponent = Engine([str(opponent_path), "uhp"])
    engines = (referee, alpha, opponent)
    alpha_white = game % 2 == 0
    maximum = {"alpha": 0.0, "opponent": 0.0}
    trace: list[str] = []
    try:
        for engine in engines:
            engine.command("newgame Base")
        for engine in (alpha, opponent):
            engine.command(f"options set NumThreads {threads}")
            engine.command(f"options set TableSizeMiB {table}")
            engine.command("options set RandomOpening False")
            engine.command("options set BackgroundPondering False")
        rng = random.Random(seed)
        state = "Base;NotStarted;White[1]"
        for _ in range(4):
            legal, _ = referee.command("validmoves")
            move = rng.choice(legal[0].split(";"))
            trace.append(move)
            for engine in engines:
                reply, _ = engine.command("play " + move)
                if not reply or reply[0].startswith("err "):
                    raise RuntimeError(f"opening divergence on {move}: {reply}")
            state = reply[0]

        while ";InProgress;" in state and len(trace) < cap:
            white = ";White[" in state
            actor_name = "alpha" if white == alpha_white else "opponent"
            actor = alpha if actor_name == "alpha" else opponent
            try:
                answer, elapsed = actor.command(
                    f"bestmove depthorseconds 99 {internal_ms / 1000:.3f}",
                    external_ms / 1000,
                )
            except TimeoutError:
                score = 0.0 if actor_name == "alpha" else 1.0
                return {"game": game, "seed": seed, "alpha_color": "white" if alpha_white else "black",
                        "score": score, "result": "timeout", "reason": actor_name + "-timeout",
                        "plies": len(trace), "max_alpha_ms": maximum["alpha"],
                        "max_opponent_ms": maximum["opponent"], "trace": ";".join(trace)}
            maximum[actor_name] = max(maximum[actor_name], elapsed)
            move = answer[0]
            trace.append(move)
            for name, engine in (("referee", referee), ("alpha", alpha), ("opponent", opponent)):
                reply, _ = engine.command("play " + move)
                if not reply or reply[0].startswith("err "):
                    raise RuntimeError(f"{name} rejected {move} at ply {len(trace)}: {reply}")
            state = reply[0]

        if ";WhiteWins;" in state:
            score = 1.0 if alpha_white else 0.0; result = "1-0"; reason = "surround"
        elif ";BlackWins;" in state:
            score = 0.0 if alpha_white else 1.0; result = "0-1"; reason = "surround"
        elif ";Draw;" in state:
            score = 0.5; result = "1/2-1/2"; reason = "draw"
        else:
            score = 0.5; result = "1/2-1/2"; reason = "ply-cap"
        return {"game": game, "seed": seed, "alpha_color": "white" if alpha_white else "black",
                "score": score, "result": result, "reason": reason, "plies": len(trace),
                "max_alpha_ms": round(maximum["alpha"], 3),
                "max_opponent_ms": round(maximum["opponent"], 3), "trace": ";".join(trace)}
    finally:
        for engine in engines:
            engine.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", type=Path, required=True)
    parser.add_argument("--opponent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=lambda x: int(x, 0), default=0xA17A2026)
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--table-mib", type=int, default=100)
    parser.add_argument("--internal-ms", type=int, default=230)
    parser.add_argument("--external-ms", type=int, default=250)
    parser.add_argument("--cap", type=int, default=160)
    args = parser.parse_args()
    if args.games <= 0 or args.games % 2 or not 1 <= args.threads <= 12:
        raise SystemExit("games must be positive/even and threads must be 1..12")
    if not 0 < args.internal_ms < args.external_ms:
        raise SystemExit("internal deadline must be below external deadline")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"alpha_sha256": digest(args.alpha), "opponent_sha256": digest(args.opponent),
                "games": args.games, "seed": args.seed, "threads": args.threads,
                "table_mib": args.table_mib, "internal_ms": args.internal_ms,
                "external_ms": args.external_ms, "cap": args.cap}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for game in range(args.games):
        row = one_game(args.alpha.resolve(), args.opponent.resolve(), game,
                       args.seed + game // 2, args.threads, args.table_mib,
                       args.internal_ms, args.external_ms, args.cap)
        rows.append(row)
        print(f"{game + 1}/{args.games} {row['alpha_color']} {row['result']} "
              f"score={row['score']} reason={row['reason']}", flush=True)
    with (args.output / "games.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    score = sum(row["score"] for row in rows)
    summary = {"score": score, "possible": args.games, "percentage": score / args.games * 100,
               "wins": sum(row["score"] == 1 for row in rows),
               "draws": sum(row["score"] == .5 for row in rows),
               "losses": sum(row["score"] == 0 for row in rows)}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
