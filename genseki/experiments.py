from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .arena import mirrored_round_robin, write_pairings
from .bots import GREEK_BOTS, enabled_bots


def experiment_manifest() -> dict[str, object]:
    bots = enabled_bots()
    return {
        "project": "Genseki",
        "game": "Hive",
        "questions": [
            "Are NNUE evaluators stronger than dense or convolutional neural evaluators?",
        ],
        "active_bots": [bot.to_json() for bot in bots],
        "all_slots": len(GREEK_BOTS),
        "active_by_evaluator": Counter(bot.evaluator.value for bot in bots),
        "scheduled_games_per_round": len(mirrored_round_robin(bots)),
        "match_policy": {
            "pairing": "round-robin, mirrored colors",
            "primary_metric": "win rate and Elo-style rating by evaluator family",
            "promotion_rule": "no model is promoted without a frozen manifest and match report",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Print or write the Genseki experiment manifest.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    parser.add_argument("--pairings", type=Path, help="Optional mirrored round-robin pairings CSV.")
    args = parser.parse_args()

    manifest = experiment_manifest()
    if args.pairings:
        write_pairings(args.pairings, mirrored_round_robin())
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
