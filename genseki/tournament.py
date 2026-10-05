from __future__ import annotations

import argparse
import csv
import hashlib
import json
import queue
import random
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .bots import enabled_bots


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Uhp:
    def __init__(self, command: list[str]):
        self.command_line = command
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        self.response(10.0)

    def _reader(self):
        assert self.process.stdout
        for line in self.process.stdout:
            self.lines.put(line.rstrip("\r\n"))
        self.lines.put(None)

    def response(self, timeout: float):
        deadline = time.perf_counter() + timeout
        lines = []
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
                return lines
            lines.append(line)

    def command(self, text: str, timeout=5.0):
        assert self.process.stdin
        started = time.perf_counter()
        self.process.stdin.write(text + "\n");self.process.stdin.flush()
        return self.response(timeout), (time.perf_counter() - started) * 1000

    def drain(self):
        try:
            self.response(10.0)
        except (TimeoutError, RuntimeError):
            self.kill()

    def kill(self):
        if self.process.poll() is None:
            self.process.kill();self.process.wait(timeout=3)

    def close(self):
        if self.process.poll() is None:
            try:
                assert self.process.stdin
                self.process.stdin.write("exit\n");self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.kill()


@dataclass(frozen=True)
class Entrant:
    name: str
    family: str
    profile: int
    model: Path
    model_hash: str
    completed_score: float
    sign_accuracy: float


class Tournament:
    def __init__(self, root: Path, engine: Path, models: Path, alpha: Path):
        self.root = root
        self.engine = engine.resolve()
        self.models = models.resolve()
        self.alpha = alpha.resolve()
        self.matches = root / "matches"
        self.reports = root / "reports"
        self.openings = root / "openings"
        for path in (root, self.matches, self.reports, self.openings):
            path.mkdir(parents=True, exist_ok=True)
        self.entrants = self._seed()
        self._freeze()

    def _seed(self):
        manifest = json.loads((self.models / "manifest.json").read_text())
        accuracy = {row["bot"]: float(row["sign_accuracy"]) for row in manifest["bots"]}
        scores = {}
        for bot in enabled_bots():
            report = Path("reports/nokamute_v2") / f"{bot.letter.lower()}.csv"
            score = 0.0
            with report.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    if "timeout" not in row["reason"]:
                        score += float(row["score"])
            scores[bot.letter] = score
        entrants = []
        for bot in enabled_bots():
            model = self.models / f"{bot.letter.lower()}.pt"
            entrants.append(Entrant(bot.letter, bot.evaluator.value, bot.search_depth,
                                    model, sha256(model), scores[bot.letter],
                                    accuracy[bot.letter]))
        entrants.sort(key=lambda e: (-e.completed_score, -e.sign_accuracy, e.name))
        return entrants

    def _freeze(self):
        frozen = {
            "format": "genseki-greek-knockout-v1",
            "engine": str(self.engine), "engine_sha256": sha256(self.engine),
            "alpha": str(self.alpha), "alpha_sha256": sha256(self.alpha),
            "seeding": "timeout-adjusted Nokamute completed score, corrected-corpus sign accuracy, name",
            "match_games": 20, "final_games": 40, "tiebreak_games": 10,
            "external_ms": 250, "max_plies": 160,
            "entrants": [dict(seed=i + 1, name=e.name, family=e.family,
                              profile=e.profile, model=str(e.model),
                              model_sha256=e.model_hash,
                              completed_score=e.completed_score,
                              sign_accuracy=e.sign_accuracy)
                         for i, e in enumerate(self.entrants)],
        }
        target = self.root / "seeds.json"
        encoded = json.dumps(frozen, indent=2) + "\n"
        if target.exists() and target.read_text() != encoded:
            raise RuntimeError("frozen tournament manifest changed")
        target.write_text(encoded)

    def player(self, name: str):
        return Uhp([sys.executable, "-m", "genseki.player", name,
                    "--engine", str(self.engine), "--models", str(self.models)])

    def _game(self, left: str, right: str, left_white: bool, seed: int,
              external_ms: int, max_plies: int, alpha_side: str | None = None,
              internal_ms: int = 0, session=None):
        referee, first, second = session
        actors = {"left": first, "right": second}
        maximum = {"left": 0.0, "right": 0.0}
        trace = []
        try:
            for process in (referee, first, second):
                answer, _ = process.command("newgame Base")
                if not answer or answer[0].startswith("err "):
                    raise RuntimeError(f"newgame failed: {answer}")
            rng = random.Random(seed)
            state = "Base;NotStarted;White[1]"
            for _ in range(4):
                legal, _ = referee.command("validmoves")
                move = rng.choice(legal[0].split(";"));trace.append(move)
                for process in (referee, first, second):
                    answer, _ = process.command("play " + move)
                    if not answer or answer[0].startswith("err "):
                        raise RuntimeError(f"opening divergence: {move}: {answer}")
                state = answer[0]
            while ";InProgress;" in state and len(trace) < max_plies:
                white = ";White[" in state
                actor_name = "left" if white == left_white else "right"
                actor = actors[actor_name]
                command = (f"bestmove depthorseconds 99 {internal_ms / 1000:.3f}"
                           if actor_name == alpha_side else "bestmove seconds 0.230")
                try:
                    answer, elapsed = actor.command(command, external_ms / 1000)
                except TimeoutError:
                    actor.drain()
                    winner = "right" if actor_name == "left" else "left"
                    return {"seed": seed, "left_white": left_white, "winner": winner,
                            "score_left": 1.0 if winner == "left" else 0.0,
                            "reason": actor_name + "-timeout", "plies": len(trace),
                            "max_left_ms": maximum["left"], "max_right_ms": maximum["right"],
                            "moves": trace}
                maximum[actor_name] = max(maximum[actor_name], elapsed)
                move = answer[0];trace.append(move)
                for label, process in (("referee", referee), ("left", first), ("right", second)):
                    answer, _ = process.command("play " + move)
                    if not answer or answer[0].startswith("err "):
                        raise RuntimeError(f"{label} rejected {move}: {answer}")
                state = answer[0]
            if ";WhiteWins;" in state:
                winner = "left" if left_white else "right";reason = "surround"
            elif ";BlackWins;" in state:
                winner = "right" if left_white else "left";reason = "surround"
            else:
                winner = None;reason = "draw" if ";Draw;" in state else "ply-cap"
            return {"seed": seed, "left_white": left_white, "winner": winner,
                    "score_left": 0.5 if winner is None else float(winner == "left"),
                    "reason": reason, "plies": len(trace),
                    "max_left_ms": round(maximum["left"], 3),
                    "max_right_ms": round(maximum["right"], 3), "moves": trace}
        finally:
            pass

    def match(self, match_id: str, left: str, right: str, games: int,
              seed_base: int, external_ms=250, alpha_side=None, internal_ms=0):
        target = self.matches / f"{match_id}.json"
        if target.exists():
            saved = json.loads(target.read_text())
            if saved.get("complete"):
                print(f"resume {match_id}: {saved['winner']}", flush=True)
                return saved["winner"]
        rows = [];batch = 0;administrative = False
        required = games
        referee = Uhp([str(self.engine)])
        first = Uhp([str(self.alpha), "uhp"]) if alpha_side == "left" else self.player(left)
        second = Uhp([str(self.alpha), "uhp"]) if alpha_side == "right" else self.player(right)
        session = (referee, first, second)
        try:
            if alpha_side:
                actor = first if alpha_side == "left" else second
                actor.command("options set NumThreads 12")
                actor.command("options set TableSizeMiB 100")
                actor.command("options set RandomOpening False")
            while True:
                for game in range(required):
                    seed = seed_base + batch * 1000 + game // 2
                    row = self._game(left, right, game % 2 == 0, seed, external_ms,
                                     160, alpha_side, internal_ms, session)
                    row["game"] = len(rows);rows.append(row)
                    print(f"{match_id} {len(rows)}/{games if batch == 0 else len(rows)} "
                          f"{left}-{right} score={sum(r['score_left'] for r in rows):g}", flush=True)
                left_score = sum(row["score_left"] for row in rows)
                if left_score * 2 != len(rows):
                    break
                if batch >= 2:
                    administrative = True
                    break
                batch += 1;required = 10
        finally:
            referee.close();first.close();second.close()
        if administrative:
            if alpha_side:
                winner = "Draw"
            else:
                seeds = {entrant.name: i for i, entrant in enumerate(self.entrants)}
                winner = left if seeds[left] < seeds[right] else right
        else:
            winner = left if left_score > len(rows) / 2 else right
        report = {"id": match_id, "left": left, "right": right, "winner": winner,
                  "left_score": left_score, "right_score": len(rows) - left_score,
                  "games": rows, "complete": True, "external_ms": external_ms,
                  "alpha_side": alpha_side,
                  "administrative_tiebreak": "higher-frozen-seed-after-40-tied-games"
                      if administrative else None}
        target.write_text(json.dumps(report, indent=2) + "\n")
        return winner

    def run(self):
        names = [e.name for e in self.entrants]
        q15 = self.match("Q1", names[14], names[17], 20, 0x71010000)
        q16 = self.match("Q2", names[15], names[16], 20, 0x71020000)
        slots = [names[0], q16, names[7], names[8], names[4], names[11], names[3], names[12],
                 names[5], names[10], names[2], names[13], names[6], names[9], names[1], q15]
        round16 = [self.match(f"R16-{i+1}", slots[i*2], slots[i*2+1], 20,
                              0x72000000 + i*0x10000) for i in range(8)]
        quarters = [self.match(f"QF-{i+1}", round16[i*2], round16[i*2+1], 20,
                               0x73000000 + i*0x10000) for i in range(4)]
        semis = [self.match(f"SF-{i+1}", quarters[i*2], quarters[i*2+1], 10,
                            0x74000000 + i*0x10000, 125) for i in range(2)]
        champion = self.match("FINAL", semis[0], semis[1], 40, 0x75000000)
        showdown = self.match("ALPHA-SHOWDOWN", champion, "Alpha", 2, 0x76000000,
                              500, "right", 450)
        epilogue = f"Alpha kindly guided {champion} to the retirement home and went on to part ways."
        summary = {"champion": champion, "alpha_showdown_winner": showdown,
                   "alpha_showdown_games": 2, "epilogue": epilogue,
                   "complete": True}
        (self.root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        self.render(champion)

    def render(self, champion):
        lines = ["# Greek Evaluator Knockout", "", f"Champion: **{champion}**", "",
                 f"Alpha kindly guided **{champion}** to the retirement home and went on to part ways.", "",
                 "All match files contain complete mirrored openings, timings, and move traces.", "",
                 "## Seeds", "", "| Seed | Bot | Family | Profile |", "|---:|---|---|---:|"]
        for i, entrant in enumerate(self.entrants, 1):
            lines.append(f"| {i} | {entrant.name} | {entrant.family} | {entrant.profile} |")
        lines += ["", "## Results", ""]
        for path in sorted(self.matches.glob("*.json")):
            report = json.loads(path.read_text())
            lines.append(f"- `{report['id']}`: {report['left']} {report['left_score']:g}-"
                         f"{report['right_score']:g} {report['right']}; winner **{report['winner']}**")
            if report["id"] == "SF-2":
                lines.append("  Sigma got a metal chair from the spectators and beat Xi to death with it.")
        (self.root / "bracket.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("Tournament"))
    parser.add_argument("--engine", type=Path, default=Path("build/genseki.exe"))
    parser.add_argument("--models", type=Path, default=Path("models/retrained-v2"))
    parser.add_argument("--alpha", type=Path,
                        default=Path("Alpha/build/rust-target/release/alpha_nokamute_mit.exe"))
    args = parser.parse_args()
    Tournament(args.root, args.engine, args.models, args.alpha).run()


if __name__ == "__main__":
    main()
