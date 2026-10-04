from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import time
from dataclasses import asdict
from pathlib import Path

import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset

from .bots import GREEK_BOTS, BotSpec, EvaluatorKind


BUG_INDEX = {"Q": 0, "S": 1, "B": 2, "G": 3, "A": 4}
PIECE_COUNTS = {"Q": 1, "S": 2, "B": 2, "G": 3, "A": 3}


def piece_slot(token: str) -> int:
    color_offset = 0 if token[0] == "w" else 11
    bug = token[1]
    bug_offset = {"Q": 0, "S": 1, "B": 3, "G": 5, "A": 8}[bug]
    number = 0 if bug == "Q" else int(token[2]) - 1
    return color_offset + bug_offset + number


def encode_position(text: str) -> tuple[list[float], list[list[list[float]]]]:
    fields = text.split("|")
    if len(fields) != 6 or fields[0] != "G1":
        raise ValueError(f"invalid position: {text}")
    side, ply, white_turns, black_turns = fields[1:5]
    stacks: list[tuple[int, int, list[str]]] = []
    if fields[5]:
        for encoded in fields[5].split(";"):
            cell, pieces = encoded.split("=")
            q_text, r_text = cell.split(",")
            stacks.append((int(q_text), int(r_text), pieces.split(",")))

    vector = [0.0] * 128
    cells = {(q, r) for q, r, _ in stacks}
    coordinates: list[tuple[int, int]] = []
    white_top = black_top = white_covered = black_covered = 0
    max_height = 0
    queens: dict[str, tuple[int, int]] = {}
    for q, r, pieces in stacks:
        max_height = max(max_height, len(pieces))
        coordinates.append((q, r))
        for height, token in enumerate(pieces):
            slot = piece_slot(token)
            base = slot * 5
            vector[base : base + 5] = [
                1.0,
                max(-1.0, min(1.0, q / 8.0)),
                max(-1.0, min(1.0, r / 8.0)),
                height / 3.0,
                1.0 if height == len(pieces) - 1 else 0.0,
            ]
            if token[1] == "Q":
                queens[token[0]] = (q, r)
            if height == len(pieces) - 1:
                if token[0] == "w":
                    white_top += 1
                else:
                    black_top += 1
            elif token[0] == "w":
                white_covered += 1
            else:
                black_covered += 1

    directions = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))

    def pressure(color: str) -> float:
        if color not in queens:
            return 0.0
        q, r = queens[color]
        return sum((q + dq, r + dr) in cells for dq, dr in directions) / 6.0

    if coordinates:
        center_q = sum(q for q, _ in coordinates) / len(coordinates)
        center_r = sum(r for _, r in coordinates) / len(coordinates)
        spread_q = max(q for q, _ in coordinates) - min(q for q, _ in coordinates)
        spread_r = max(r for _, r in coordinates) - min(r for _, r in coordinates)
    else:
        center_q = center_r = spread_q = spread_r = 0.0
    vector[110:] = [
        1.0 if side == "w" else -1.0,
        min(int(ply), 96) / 96.0,
        int(white_turns) / 11.0,
        int(black_turns) / 11.0,
        pressure("w"),
        pressure("b"),
        len(stacks) / 22.0,
        max_height / 4.0,
        white_top / 11.0,
        black_top / 11.0,
        white_covered / 11.0,
        black_covered / 11.0,
        max(-1.0, min(1.0, center_q / 8.0)),
        max(-1.0, min(1.0, center_r / 8.0)),
        min(spread_q, 16) / 16.0,
        min(spread_r, 16) / 16.0,
        1.0,
        math.tanh((pressure("b") - pressure("w")) * 2.0),
    ]

    grid = [[[0.0 for _ in range(11)] for _ in range(11)] for _ in range(12)]
    origin_q = round(center_q) if coordinates else 0
    origin_r = round(center_r) if coordinates else 0
    for q, r, pieces in stacks:
        x = q - origin_q + 5
        y = r - origin_r + 5
        if not (0 <= x < 11 and 0 <= y < 11):
            continue
        for token in pieces:
            channel = (0 if token[0] == "w" else 5) + BUG_INDEX[token[1]]
            grid[channel][y][x] += 1.0
        grid[10][y][x] = 1.0 if pieces[-1][0] == "w" else -1.0
        grid[11][y][x] = len(pieces) / 4.0
    return vector, grid


class Handcrafted(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.linear = nn.Linear(128, 1)

    def forward(self, vector: Tensor, grid: Tensor) -> Tensor:
        del grid
        return torch.tanh(self.linear(vector)).squeeze(1)


class Nnue(nn.Module):
    def __init__(self, width: int = 64) -> None:
        super().__init__()
        self.accumulator = nn.Linear(128, width)
        self.output = nn.Linear(width, 1)

    def forward(self, vector: Tensor, grid: Tensor) -> Tensor:
        del grid
        hidden = torch.clamp(self.accumulator(vector), 0.0, 1.0)
        return torch.tanh(self.output(hidden)).squeeze(1)


class Dense(nn.Module):
    def __init__(self, width: int = 96) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(128, width),
            nn.GELU(),
            nn.Linear(width, width // 2),
            nn.GELU(),
            nn.Linear(width // 2, 1),
            nn.Tanh(),
        )

    def forward(self, vector: Tensor, grid: Tensor) -> Tensor:
        del grid
        return self.network(vector).squeeze(1)


class Convolutional(nn.Module):
    def __init__(self, width: int = 24) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(12, width, 3, padding=1),
            nn.GELU(),
        )
        self.output = nn.Linear(width * 2, 1)

    def forward(self, vector: Tensor, grid: Tensor) -> Tensor:
        del vector
        features = self.features(grid)
        pooled = torch.cat((features.mean((2, 3)), features.amax((2, 3))), dim=1)
        return torch.tanh(self.output(pooled)).squeeze(1)


def make_model(bot: BotSpec) -> nn.Module:
    if bot.evaluator == EvaluatorKind.HANDCRAFTED:
        return Handcrafted()
    if bot.evaluator == EvaluatorKind.NNUE:
        return Nnue(48 + bot.search_depth * 8)
    if bot.evaluator == EvaluatorKind.DENSE:
        return Dense(64 + bot.search_depth * 8)
    return Convolutional(8 + bot.search_depth)


def load_dataset(path: Path) -> tuple[TensorDataset, TensorDataset, dict[str, object]]:
    train_vectors: list[list[float]] = []
    train_grids: list[list[list[list[float]]]] = []
    train_labels: list[float] = []
    test_vectors: list[list[float]] = []
    test_grids: list[list[list[list[float]]]] = []
    test_labels: list[float] = []
    finishes: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            vector, grid = encode_position(row["position"])
            target = float(row["label"])
            finishes[row["finish"]] = finishes.get(row["finish"], 0) + 1
            target_lists = (
                (test_vectors, test_grids, test_labels)
                if int(row["game"]) % 5 == 0
                else (train_vectors, train_grids, train_labels)
            )
            target_lists[0].append(vector)
            target_lists[1].append(grid)
            target_lists[2].append(target)

    def tensors(vectors: list, grids: list, labels: list) -> TensorDataset:
        return TensorDataset(
            torch.tensor(vectors, dtype=torch.float32),
            torch.tensor(grids, dtype=torch.float32),
            torch.tensor(labels, dtype=torch.float32),
        )

    metadata = {
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "train_positions": len(train_labels),
        "test_positions": len(test_labels),
        "finishes": finishes,
    }
    return tensors(train_vectors, train_grids, train_labels), tensors(
        test_vectors, test_grids, test_labels
    ), metadata


@torch.no_grad()
def evaluate(model: nn.Module, dataset: TensorDataset, device: torch.device) -> dict[str, float]:
    loader = DataLoader(dataset, batch_size=1024, shuffle=False)
    squared = absolute = correct = count = 0.0
    model.eval()
    for vector, grid, target in loader:
        prediction = model(vector.to(device), grid.to(device))
        target = target.to(device)
        squared += torch.square(prediction - target).sum().item()
        absolute += torch.abs(prediction - target).sum().item()
        correct += ((prediction >= 0) == (target >= 0)).sum().item()
        count += target.numel()
    return {
        "mse": squared / count,
        "mae": absolute / count,
        "sign_accuracy": correct / count,
    }


def train_bot(
    bot: BotSpec,
    train: TensorDataset,
    test: TensorDataset,
    output: Path,
    device: torch.device,
    epochs: int,
    batch_size: int,
) -> dict[str, object]:
    seed = 1729 + GREEK_BOTS.index(bot) * 104729
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    model = make_model(bot).to(device)
    generator = torch.Generator().manual_seed(seed)
    effective_batch_size = (
        len(train) if bot.evaluator == EvaluatorKind.CONVOLUTIONAL else batch_size
    )
    loader = DataLoader(
        train,
        batch_size=effective_batch_size,
        shuffle=True,
        generator=generator,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=0.0015 if bot.evaluator != EvaluatorKind.HANDCRAFTED else 0.004,
        weight_decay=0.0001 * bot.search_depth,
    )
    loss_function = nn.SmoothL1Loss()
    started = time.perf_counter()
    model.train()
    for _ in range(epochs):
        for vector, grid, target in loader:
            optimizer.zero_grad(set_to_none=True)
            prediction = model(vector.to(device), grid.to(device))
            loss = loss_function(prediction, target.to(device))
            loss.backward()
            optimizer.step()
    metrics = evaluate(model, test, device)
    output.parent.mkdir(parents=True, exist_ok=True)
    cpu_state = {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    payload = {
        "format": "genseki-evaluator-v1",
        "bot": bot.letter,
        "evaluator": bot.evaluator.value,
        "search_depth": bot.search_depth,
        "seed": seed,
        "architecture": model.__class__.__name__,
        "state_dict": cpu_state,
        "metrics": metrics,
    }
    torch.save(payload, output)
    reloaded = torch.load(output, map_location="cpu", weights_only=True)
    if reloaded["format"] != "genseki-evaluator-v1" or reloaded["bot"] != bot.letter:
        raise RuntimeError(f"artifact reload failed for {bot.letter}")
    return {
        "bot": bot.letter,
        "evaluator": bot.evaluator.value,
        "search_depth": bot.search_depth,
        "seed": seed,
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "epochs": epochs,
        "batch_size": effective_batch_size,
        "seconds": time.perf_counter() - started,
        "artifact": output.as_posix(),
        **metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train every Genseki Greek bot evaluator.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("models/frozen"))
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=384)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is unavailable")
    device = torch.device(args.device)
    train, test, dataset_metadata = load_dataset(args.dataset)
    results = []
    for bot in GREEK_BOTS:
        artifact = args.output / f"{bot.letter.lower()}.pt"
        result = train_bot(bot, train, test, artifact, device, args.epochs, args.batch_size)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    manifest = {
        "format": "genseki-training-manifest-v1",
        "device": str(device),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "dataset": dataset_metadata,
        "bots": results,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": manifest_path.as_posix(), "bots": len(results)}))


if __name__ == "__main__":
    main()
