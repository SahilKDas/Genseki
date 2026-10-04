from __future__ import annotations

import argparse
import struct
from pathlib import Path

import torch

from .bots import EvaluatorKind, bot_by_letter


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a frozen Genseki NNUE for native search.")
    parser.add_argument("bot")
    parser.add_argument("--models", type=Path, default=Path("models/frozen"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    bot = bot_by_letter(args.bot)
    if bot.evaluator != EvaluatorKind.NNUE:
        raise SystemExit(f"{bot.letter} is not an NNUE bot")
    source = args.models / f"{bot.letter.lower()}.pt"
    output = args.output or args.models / f"{bot.letter.lower()}.nnue"
    payload = torch.load(source, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    accumulator_weight = state["accumulator.weight"].contiguous().float()
    accumulator_bias = state["accumulator.bias"].contiguous().float()
    output_weight = state["output.weight"].contiguous().float().reshape(-1)
    output_bias = state["output.bias"].contiguous().float()
    width = accumulator_weight.shape[0]
    if accumulator_weight.shape != (width, 128) or output_weight.shape != (width,):
        raise SystemExit("unsupported NNUE shape")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(b"GNNUE01\0")
        handle.write(struct.pack("<I", width))
        for tensor in (accumulator_weight, accumulator_bias, output_weight, output_bias):
            handle.write(tensor.numpy().tobytes(order="C"))
    print(f"{bot.letter}: {source} -> {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
