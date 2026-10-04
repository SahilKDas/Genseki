from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import torch

from .bots import bot_by_letter
from .training import encode_position, make_model


class NativeEngine:
    def __init__(self, executable: Path) -> None:
        self.process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )
        self.read_response()

    def read_response(self) -> list[str]:
        assert self.process.stdout is not None
        lines: list[str] = []
        while True:
            line = self.process.stdout.readline()
            if line == "":
                raise RuntimeError("native Genseki engine exited")
            line = line.rstrip("\r\n")
            lines.append(line)
            if line == "ok":
                return lines

    def command(self, command: str) -> list[str]:
        assert self.process.stdin is not None
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        return self.read_response()

    def close(self) -> None:
        if self.process.poll() is None:
            assert self.process.stdin is not None
            self.process.stdin.write("exit\n")
            self.process.stdin.flush()
            self.process.wait(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="UHP player backed by a trained Greek evaluator.")
    parser.add_argument("bot")
    parser.add_argument("--engine", type=Path, default=Path("build/genseki.exe"))
    parser.add_argument("--models", type=Path, default=Path("models/frozen"))
    args = parser.parse_args()

    bot = bot_by_letter(args.bot)
    artifact = torch.load(args.models / f"{bot.letter.lower()}.pt", map_location="cpu", weights_only=True)
    model = make_model(bot)
    model.load_state_dict(artifact["state_dict"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    torch.set_num_threads(1)
    with torch.inference_mode():
        model(
            torch.zeros((1, 128), dtype=torch.float32, device=device),
            torch.zeros((1, 12, 11, 11), dtype=torch.float32, device=device),
        )
    if device.type == "cuda":
        torch.cuda.synchronize()
    native = NativeEngine(args.engine.resolve())
    current_game = "Base;NotStarted;White[1]"

    print(f"id Genseki-{bot.letter} v0.1.0", flush=True)
    print("ok", flush=True)
    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            command = line.split(" ", 1)[0] if line else ""
            if command == "exit":
                break
            if command == "info":
                print(f"id Genseki-{bot.letter} v0.1.0")
                print("ok", flush=True)
                continue
            if command == "bestmove":
                children = native.command("genseki-children")[:-1]
                moves: list[str] = []
                vectors = []
                grids = []
                for child in children:
                    move, position = child.split("\t", 1)
                    vector, grid = encode_position(position)
                    moves.append(move)
                    vectors.append(vector)
                    grids.append(grid)
                with torch.inference_mode():
                    values = model(
                        torch.tensor(vectors, dtype=torch.float32, device=device),
                        torch.tensor(grids, dtype=torch.float32, device=device),
                    )
                white = current_game.split(";")[2].startswith("White")
                selected = int(torch.argmax(values).item() if white else torch.argmin(values).item())
                print(moves[selected])
                print("ok", flush=True)
                continue
            response = native.command(line)
            for output in response:
                print(output)
            sys.stdout.flush()
            if command in {"newgame", "play", "pass", "undo"} and response[0].startswith("Base;"):
                current_game = response[0]
    finally:
        native.close()


if __name__ == "__main__":
    main()
