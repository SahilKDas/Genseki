from __future__ import annotations

import csv
import itertools
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .bots import BotSpec, EvaluatorKind, bot_by_letter, enabled_bots


@dataclass(frozen=True)
class Pairing:
    white: str
    black: str


@dataclass(frozen=True)
class GameResult:
    white: str
    black: str
    result: str
    plies: int
    reason: str

    @property
    def white_score(self) -> float:
        if self.result == "1-0":
            return 1.0
        if self.result == "0-1":
            return 0.0
        if self.result == "1/2-1/2":
            return 0.5
        raise ValueError(f"unknown result: {self.result}")


@dataclass(frozen=True)
class FamilyScore:
    evaluator: EvaluatorKind
    games: int
    score: float

    @property
    def win_rate(self) -> float:
        return self.score / self.games if self.games else 0.0


def mirrored_round_robin(bots: tuple[BotSpec, ...] | None = None) -> tuple[Pairing, ...]:
    active = bots if bots is not None else enabled_bots()
    pairings: list[Pairing] = []
    for left, right in itertools.combinations(active, 2):
        pairings.append(Pairing(white=left.letter, black=right.letter))
        pairings.append(Pairing(white=right.letter, black=left.letter))
    return tuple(pairings)


def read_results(path: Path) -> tuple[GameResult, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return tuple(
            GameResult(
                white=row["white"],
                black=row["black"],
                result=row["result"],
                plies=int(row["plies"]),
                reason=row["reason"],
            )
            for row in reader
        )


def write_pairings(path: Path, pairings: tuple[Pairing, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["white", "black"])
        writer.writeheader()
        for pairing in pairings:
            writer.writerow({"white": pairing.white, "black": pairing.black})


def family_scores(results: tuple[GameResult, ...]) -> tuple[FamilyScore, ...]:
    games: dict[EvaluatorKind, int] = defaultdict(int)
    scores: dict[EvaluatorKind, float] = defaultdict(float)
    for result in results:
        white = bot_by_letter(result.white).evaluator
        black = bot_by_letter(result.black).evaluator
        white_score = result.white_score
        black_score = 1.0 - white_score
        games[white] += 1
        games[black] += 1
        scores[white] += white_score
        scores[black] += black_score
    return tuple(
        FamilyScore(evaluator=evaluator, games=games[evaluator], score=scores[evaluator])
        for evaluator in sorted(games, key=lambda item: item.value)
    )


def verdicts(scores: tuple[FamilyScore, ...]) -> dict[str, object]:
    by_eval = {score.evaluator: score for score in scores}
    nnue = by_eval.get(EvaluatorKind.NNUE)
    dense = by_eval.get(EvaluatorKind.DENSE)
    convolutional = by_eval.get(EvaluatorKind.CONVOLUTIONAL)
    handcrafted = by_eval.get(EvaluatorKind.HANDCRAFTED)
    if nnue is None:
        return {"ready": False, "reason": "no NNUE games"}
    neural_field_games = (dense.games if dense else 0) + (convolutional.games if convolutional else 0)
    neural_field_score = (dense.score if dense else 0.0) + (
        convolutional.score if convolutional else 0.0
    )
    neural_field_rate = neural_field_score / neural_field_games if neural_field_games else None
    handcrafted_rate = handcrafted.win_rate if handcrafted else None
    return {
        "ready": True,
        "nnue_win_rate": nnue.win_rate,
        "nnue_beats_dense_or_conv": None
        if neural_field_rate is None
        else nnue.win_rate > neural_field_rate,
        "dense_or_conv_win_rate": neural_field_rate,
        "nnue_beats_handcrafted": None
        if handcrafted_rate is None
        else nnue.win_rate > handcrafted_rate,
        "handcrafted_win_rate": handcrafted_rate,
    }
