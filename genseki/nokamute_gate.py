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

from .bots import bot_by_letter


PINNED_NOKAMUTE_VERSION = "1.0.3"
PINNED_NOKAMUTE_REVISION = "c9ab65e0d9f496fd8735096ae37babc8bb50a57c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class UhpProcess:
    def __init__(self, command: list[str]) -> None:
        self.command_line = command
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.reader = threading.Thread(target=self._read_lines, daemon=True)
        self.reader.start()
        self.read_response(5.0)

    def _read_lines(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.lines.put(line.rstrip("\r\n"))
        self.lines.put(None)

    def read_response(self, timeout: float) -> list[str]:
        deadline = time.perf_counter() + timeout
        result: list[str] = []
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError("UHP response deadline exceeded")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("UHP response deadline exceeded") from error
            if line is None:
                raise RuntimeError(f"UHP engine exited: {self.command_line}")
            result.append(line)
            if line == "ok":
                return result

    def command(self, line: str, timeout: float = 5.0) -> tuple[list[str], float]:
        assert self.process.stdin is not None
        started = time.perf_counter()
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        return self.read_response(timeout), time.perf_counter() - started

    def drain_after_timeout(self) -> None:
        try:
            self.read_response(3.0)
        except (TimeoutError, RuntimeError):
            self.kill()

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=3)

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                assert self.process.stdin is not None
                self.process.stdin.write("exit\n")
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.kill()


@dataclass
class GameResult:
    bot: str
    game: int
    opening_seed: int
    bot_color: str
    result: str
    score: float
    plies: int
    reason: str
    max_bot_ms: float
    max_nokamute_ms: float
    max_depth: int
    total_nodes: int
    last_pv: str


def parse_search_info(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in text.split(" "):
        key, separator, value = part.partition("=")
        if separator:
            fields[key] = value
    return fields


class Match:
    def __init__(
        self,
        bot: str,
        engine: Path,
        model: Path | None,
        nokamute: Path,
        threads: int,
        table_mib: int,
        internal_ms: int,
        player_mode: str = "native",
        models: Path | None = None,
    ) -> None:
        self.bot = bot
        self.referee = UhpProcess([str(engine)])
        if player_mode == "python":
            if models is None:
                raise ValueError("Python player requires a model directory")
            player_command = [
                sys.executable, "-m", "genseki.player", bot,
                "--engine", str(engine), "--models", str(models),
            ]
        else:
            player_command = [
                str(engine),
                "--threads", str(threads),
                "--table-mib", str(table_mib),
                "--move-ms", str(internal_ms),
            ]
            if model is not None:
                player_command.extend(("--model", str(model)))
        self.player = UhpProcess(player_command)
        self.has_search_info = player_mode == "native"
        self.opponent = UhpProcess([str(nokamute), "uhp"])
        self.opponent.command(f"options set NumThreads {threads}")
        self.opponent.command(f"options set TableSizeMiB {table_mib}")
        self.opponent.command("options set RandomOpening False")
        self.internal_seconds = internal_ms / 1000.0

    def close(self) -> None:
        self.referee.close()
        self.player.close()
        self.opponent.close()

    def play(
        self,
        game: int,
        opening_seed: int,
        max_plies: int,
        external_ms: int,
    ) -> GameResult:
        for engine in (self.referee, self.player, self.opponent):
            response, _ = engine.command("newgame Base;NotStarted;White[1]")
            if not response[0].startswith("Base;"):
                raise RuntimeError(f"newgame divergence: {response[0]}")

        randomizer = random.Random(opening_seed)
        game_string = "Base;NotStarted;White[1]"
        for _ in range(4):
            valid, _ = self.referee.command("validmoves")
            choices = valid[0].split(";")
            move = choices[randomizer.randrange(len(choices))]
            game_string = self.referee.command(f"play {move}")[0][0]
            for engine in (self.player, self.opponent):
                response, _ = engine.command(f"play {move}")
                if not response[0].startswith("Base;"):
                    raise RuntimeError(f"opening divergence on {move}: {response[0]}")

        bot_white = game % 2 == 0
        deadline = external_ms / 1000.0
        max_times = {"bot": 0.0, "nokamute": 0.0}
        max_depth = 0
        total_nodes = 0
        last_pv = ""
        while ";InProgress;" in game_string and game_string.count(";") - 2 < max_plies:
            white_to_move = ";White[" in game_string
            actor = "bot" if white_to_move == bot_white else "nokamute"
            process = self.player if actor == "bot" else self.opponent
            command = (
                f"bestmove time 00:00:00.{int(self.internal_seconds * 1000):03d}"
                if actor == "bot"
                else f"bestmove depthorseconds 99 {self.internal_seconds:.3f}"
            )
            try:
                response, elapsed = process.command(command, timeout=deadline)
            except TimeoutError:
                process.drain_after_timeout()
                score = 0.0 if actor == "bot" else 1.0
                return GameResult(
                    self.bot, game, opening_seed,
                    "white" if bot_white else "black",
                    "timeout", score, game_string.count(";") - 2,
                    f"{actor}-timeout", max_times["bot"] * 1000,
                    max_times["nokamute"] * 1000, max_depth, total_nodes, last_pv,
                )
            max_times[actor] = max(max_times[actor], elapsed)
            move = response[0]
            if actor == "bot" and self.has_search_info:
                info = self.player.command("genseki-searchinfo")[0][0]
                fields = parse_search_info(info)
                max_depth = max(max_depth, int(fields.get("depth", 0)))
                total_nodes += int(fields.get("nodes", 0))
                last_pv = fields.get("pv", "")

            referee_response, _ = self.referee.command(f"play {move}")
            if not referee_response[0].startswith("Base;"):
                raise RuntimeError(
                    f"illegal move from {actor}: {move} in {game_string}; "
                    f"referee={referee_response[0]}"
                )
            game_string = referee_response[0]
            for name, engine in (("bot", self.player), ("nokamute", self.opponent)):
                sync, _ = engine.command(f"play {move}")
                if not sync[0].startswith("Base;"):
                    raise RuntimeError(
                        f"rules divergence: {name} rejected {move} in {game_string}: {sync[0]}"
                    )

        if ";WhiteWins;" in game_string:
            score = 1.0 if bot_white else 0.0
            result = "1-0"
            reason = "surround"
        elif ";BlackWins;" in game_string:
            score = 0.0 if bot_white else 1.0
            result = "0-1"
            reason = "surround"
        else:
            score = 0.5
            result = "1/2-1/2"
            reason = "draw" if ";Draw;" in game_string else "ply-cap"
        return GameResult(
            self.bot, game, opening_seed, "white" if bot_white else "black",
            result, score, game_string.count(";") - 2, reason,
            max_times["bot"] * 1000, max_times["nokamute"] * 1000,
            max_depth, total_nodes, last_pv,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the sealed Nokamute champion gate.")
    parser.add_argument("bot")
    parser.add_argument("--engine", type=Path, default=Path("build/genseki.exe"))
    parser.add_argument("--model", type=Path)
    parser.add_argument("--models", type=Path, default=Path("models/retrained-v2"))
    parser.add_argument("--player-mode", choices=("native", "python"), default="native")
    parser.add_argument("--native-heuristic", action="store_true")
    parser.add_argument("--nokamute", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/nokamute_gate.csv"))
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--opening-seed", type=lambda value: int(value, 0), default=0x4E4F4B46)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--internal-ms", type=int, default=230)
    parser.add_argument("--external-ms", type=int, default=250)
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--table-mib", type=int, default=100)
    parser.add_argument("--phase", choices=("development", "final"), default="development")
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()

    bot = bot_by_letter(args.bot)
    if args.native_heuristic and args.model is not None:
        raise SystemExit("--native-heuristic and --model are mutually exclusive")
    if args.player_mode == "python":
        model = args.models / f"{bot.letter.lower()}.pt"
    else:
        model = None if args.native_heuristic else (
            args.model or Path("models/frozen") / f"{bot.letter.lower()}.nnue"
        )
    if args.games <= 0 or args.games % 2 != 0:
        raise SystemExit("--games must be a positive even number")
    if not (1 <= args.threads <= 12):
        raise SystemExit("--threads must be between 1 and 12")
    if not (0 < args.internal_ms < args.external_ms):
        raise SystemExit("internal deadline must be below external deadline")
    engine = args.engine.resolve()
    opponent = args.nokamute.resolve()
    resolved_model = model.resolve() if model else None
    frozen = {
        "format": "genseki-nokamute-champion-v1",
        "bot": bot.letter,
        "engine_sha256": sha256(engine),
        "model": str(resolved_model) if resolved_model else None,
        "model_sha256": sha256(resolved_model) if resolved_model else None,
        "nokamute_version": PINNED_NOKAMUTE_VERSION,
        "nokamute_revision": PINNED_NOKAMUTE_REVISION,
        "nokamute_sha256": sha256(opponent),
        "threads": args.threads,
        "table_mib": args.table_mib,
        "internal_ms": args.internal_ms,
        "external_ms": args.external_ms,
        "max_plies": args.max_plies,
        "games": 100,
    }
    if args.freeze:
        if args.freeze_manifest is None:
            raise SystemExit("--freeze requires --freeze-manifest")
        if args.native_heuristic:
            raise SystemExit("only a neural candidate may be frozen as champion")
        if args.freeze_manifest.exists():
            raise SystemExit("refusing to replace an existing freeze manifest")
        args.freeze_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.freeze_manifest.write_text(
            json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"FROZEN {bot.letter} {args.freeze_manifest}")
        return
    if args.phase == "final":
        if args.freeze_manifest is None or not args.freeze_manifest.exists():
            raise SystemExit("final qualification requires an existing --freeze-manifest")
        expected = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
        if expected != frozen:
            raise SystemExit("candidate artifact or qualification configuration differs from freeze")
        if args.games != 100:
            raise SystemExit("final qualification must contain exactly 100 games")
        if args.output.exists():
            raise SystemExit("refusing to rerun or overwrite a final qualification report")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    match = Match(
        bot.letter, engine, resolved_model, opponent,
        args.threads, args.table_mib, args.internal_ms,
        args.player_mode, args.models.resolve(),
    )
    score = 0.0
    fields = list(GameResult.__dataclass_fields__)
    try:
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for game in range(args.games):
                opening_seed = args.opening_seed + game // 2
                result = match.play(game, opening_seed, args.max_plies, args.external_ms)
                writer.writerow(result.__dict__)
                handle.flush()
                score += result.score
                print(
                    f"{bot.letter} {game + 1}/{args.games} score={score:g} "
                    f"result={result.result} reason={result.reason} depth={result.max_depth}",
                    flush=True,
                )
    finally:
        match.close()
    threshold = args.games * 0.55
    print(f"QUALIFY {bot.letter} score={score}/{args.games} pass={score > threshold}")


if __name__ == "__main__":
    main()
