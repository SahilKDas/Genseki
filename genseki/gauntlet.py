from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .bots import GREEK_BOTS, BotSpec


class UhpProcess:
    def __init__(self, command: list[str]) -> None:
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )
        self.read()

    def read(self) -> list[str]:
        assert self.process.stdout is not None
        result = []
        while True:
            line = self.process.stdout.readline()
            if line == "":
                raise RuntimeError("UHP engine exited")
            line = line.rstrip("\r\n")
            result.append(line)
            if line == "ok":
                return result

    def command(self, line: str) -> tuple[list[str], float]:
        assert self.process.stdin is not None
        started = time.perf_counter()
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        return self.read(), time.perf_counter() - started

    def close(self) -> None:
        if self.process.poll() is None:
            assert self.process.stdin is not None
            self.process.stdin.write("exit\n")
            self.process.stdin.flush()
            self.process.wait(timeout=3)


@dataclass
class Result:
    bot: str
    game: int
    bot_color: str
    result: str
    score: float
    plies: int
    reason: str
    max_bot_ms: float
    max_mzinga_ms: float


def play_game(
    bot: BotSpec,
    game: int,
    native: Path,
    mzinga: Path,
    opening_seed: int,
    max_plies: int,
    time_limit: float,
    processes: tuple[UhpProcess, UhpProcess, UhpProcess] | None = None,
) -> Result:
    owns_processes = processes is None
    if processes is None:
        processes = (
            UhpProcess([str(native)]),
            UhpProcess(
                [sys.executable, "-m", "genseki.player", bot.letter, "--engine", str(native)]
            ),
            UhpProcess([str(mzinga)]),
        )
    referee, player, opponent = processes
    engines = {"bot": player, "mzinga": opponent}
    bot_white = game % 2 == 0
    max_times = {"bot": 0.0, "mzinga": 0.0}
    try:
        for engine in (referee, player, opponent):
            engine.command("newgame Base;NotStarted;White[1]")
        randomizer = random.Random(opening_seed)
        game_string = "Base;NotStarted;White[1]"
        for _ in range(4):
            valid, _ = referee.command("validmoves")
            choices = valid[0].split(";")
            move = choices[randomizer.randrange(len(choices))]
            game_string = referee.command(f"play {move}")[0][0]
            for engine_name, engine in engines.items():
                sync_response, _ = engine.command(f"play {move}")
                if not sync_response[0].startswith("Base;"):
                    return Result(
                        bot.letter, game, "white" if bot_white else "black",
                        "forfeit", 0.0, game_string.count(";") - 2,
                        f"{engine_name}-opening-sync", 0.0, 0.0,
                    )

        while ";InProgress;" in game_string and game_string.count(";") - 2 < max_plies:
            before_position = referee.command("genseki-position")[0][0]
            turn_white = ";White[" in game_string
            actor = "bot" if turn_white == bot_white else "mzinga"
            response, elapsed = engines[actor].command("bestmove time 00:00:01")
            max_times[actor] = max(max_times[actor], elapsed)
            if elapsed > time_limit:
                score = 0.0 if actor == "bot" else 1.0
                return Result(
                    bot.letter, game, "white" if bot_white else "black",
                    "timeout", score, game_string.count(";") - 2,
                    f"{actor}-timeout", max_times["bot"] * 1000, max_times["mzinga"] * 1000,
                )
            move = response[0]
            referee_response, _ = referee.command(f"play {move}")
            if referee_response[0].startswith("invalidmove"):
                print(f"DIFF game={game} actor={actor} move={move} state={game_string}", flush=True)
                score = 0.0 if actor == "bot" else 1.0
                return Result(
                    bot.letter, game, "white" if bot_white else "black",
                    "forfeit", score, game_string.count(";") - 2,
                    f"{actor}-illegal:{move}", max_times["bot"] * 1000, max_times["mzinga"] * 1000,
                )
            game_string = referee_response[0]
            for engine_name, engine in engines.items():
                sync_response, _ = engine.command(f"play {move}")
                if not sync_response[0].startswith("Base;"):
                    engine_moves, _ = engine.command("validmoves")
                    print(
                        f"DIFF game={game} engine={engine_name} sync={sync_response[0]} "
                        f"move={move} valid={engine_moves[0]} "
                        f"position={before_position} state={game_string}",
                        flush=True,
                    )
                    return Result(
                        bot.letter, game, "white" if bot_white else "black",
                        "forfeit", 0.0, game_string.count(";") - 2,
                        f"{engine_name}-sync", max_times["bot"] * 1000, max_times["mzinga"] * 1000,
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
        return Result(
            bot.letter, game, "white" if bot_white else "black", result, score,
            game_string.count(";") - 2, reason,
            max_times["bot"] * 1000, max_times["mzinga"] * 1000,
        )
    finally:
        if owns_processes:
            referee.close()
            player.close()
            opponent.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualify Greek bots against MzingaCpp.")
    parser.add_argument("--engine", type=Path, default=Path("build/genseki.exe"))
    parser.add_argument("--mzinga", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/mzinga_gauntlet.csv"))
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--move-ms", type=int, default=250)
    parser.add_argument("--bot")
    args = parser.parse_args()
    bots = [next(bot for bot in GREEK_BOTS if bot.letter == args.bot)] if args.bot else list(GREEK_BOTS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(Result.__dataclass_fields__)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for bot in bots:
            score = 0.0
            processes = (
                UhpProcess([str(args.engine.resolve())]),
                UhpProcess([
                    sys.executable, "-m", "genseki.player", bot.letter,
                    "--engine", str(args.engine.resolve()),
                ]),
                UhpProcess([str(args.mzinga.resolve())]),
            )
            try:
                for game in range(args.games):
                    result = play_game(
                        bot, game, args.engine.resolve(), args.mzinga.resolve(),
                        opening_seed=0x47454E53 + game // 2,
                        max_plies=args.max_plies,
                        time_limit=args.move_ms / 1000.0,
                        processes=processes,
                    )
                    writer.writerow(result.__dict__)
                    handle.flush()
                    score += result.score
                    print(
                        f"{bot.letter} {game + 1}/{args.games} score={score:g} "
                        f"result={result.result} reason={result.reason}",
                        flush=True,
                    )
            finally:
                for process in processes:
                    process.close()
            print(f"QUALIFY {bot.letter} score={score}/{args.games} pass={score > args.games / 2}")


if __name__ == "__main__":
    main()
