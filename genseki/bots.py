from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class EvaluatorKind(StrEnum):
    HANDCRAFTED = "handcrafted"
    NNUE = "nnue"
    DENSE = "dense"
    CONVOLUTIONAL = "convolutional"


@dataclass(frozen=True)
class BotSpec:
    letter: str
    evaluator: EvaluatorKind
    search_depth: int
    enabled: bool = False

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        data["evaluator"] = self.evaluator.value
        return data


GREEK_BOTS: tuple[BotSpec, ...] = (
    BotSpec("Alpha", EvaluatorKind.HANDCRAFTED, 1, True),
    BotSpec("Beta", EvaluatorKind.HANDCRAFTED, 2, True),
    BotSpec("Gamma", EvaluatorKind.NNUE, 1, True),
    BotSpec("Delta", EvaluatorKind.NNUE, 2, True),
    BotSpec("Epsilon", EvaluatorKind.DENSE, 1, True),
    BotSpec("Zeta", EvaluatorKind.DENSE, 2, True),
    BotSpec("Eta", EvaluatorKind.CONVOLUTIONAL, 1, True),
    BotSpec("Theta", EvaluatorKind.CONVOLUTIONAL, 2, True),
    BotSpec("Iota", EvaluatorKind.HANDCRAFTED, 3),
    BotSpec("Kappa", EvaluatorKind.NNUE, 3),
    BotSpec("Lambda", EvaluatorKind.DENSE, 3),
    BotSpec("Mu", EvaluatorKind.CONVOLUTIONAL, 3),
    BotSpec("Nu", EvaluatorKind.HANDCRAFTED, 4),
    BotSpec("Xi", EvaluatorKind.NNUE, 4),
    BotSpec("Omicron", EvaluatorKind.DENSE, 4),
    BotSpec("Pi", EvaluatorKind.CONVOLUTIONAL, 4),
    BotSpec("Rho", EvaluatorKind.HANDCRAFTED, 5),
    BotSpec("Sigma", EvaluatorKind.NNUE, 5),
    BotSpec("Tau", EvaluatorKind.DENSE, 5),
    BotSpec("Upsilon", EvaluatorKind.CONVOLUTIONAL, 5),
    BotSpec("Phi", EvaluatorKind.HANDCRAFTED, 6),
    BotSpec("Chi", EvaluatorKind.NNUE, 6),
    BotSpec("Psi", EvaluatorKind.DENSE, 6),
    BotSpec("Omega", EvaluatorKind.CONVOLUTIONAL, 6),
)


def enabled_bots() -> tuple[BotSpec, ...]:
    return tuple(bot for bot in GREEK_BOTS if bot.enabled)


def bot_by_letter(letter: str) -> BotSpec:
    for bot in GREEK_BOTS:
        if bot.letter == letter:
            return bot
    raise KeyError(f"unknown bot: {letter}")
