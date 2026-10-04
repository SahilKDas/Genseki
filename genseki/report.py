from __future__ import annotations

import argparse
import json
from pathlib import Path

from .arena import family_scores, read_results, verdicts


def build_report(results_path: Path) -> dict[str, object]:
    results = read_results(results_path)
    scores = family_scores(results)
    return {
        "results_path": str(results_path),
        "games": len(results),
        "family_scores": [
            {
                "evaluator": score.evaluator.value,
                "games": score.games,
                "score": score.score,
                "win_rate": score.win_rate,
            }
            for score in scores
        ],
        "verdicts": verdicts(scores),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Genseki arena results.")
    parser.add_argument("results", type=Path, help="CSV with white,black,result,plies,reason.")
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()

    report = build_report(args.results)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
