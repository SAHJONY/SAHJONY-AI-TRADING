#!/usr/bin/env python3
"""Evaluate AI advisory providers from resolved JSONL observations.

Input rows must match intelligence.shadow_eval.ShadowObservation. The command is
read-only with respect to brokerage accounts and cannot submit orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from intelligence.shadow_eval import evaluate_all, observations_from_dicts


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {number}: {exc}") from exc
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Score AI providers in shadow mode")
    parser.add_argument("--input", default="data/ai_shadow_observations.jsonl")
    parser.add_argument("--output", default="public/ai_shadow.json")
    parser.add_argument("--min-observations", type=int, default=100)
    parser.add_argument("--min-sharpe", type=float, default=0.25)
    parser.add_argument("--max-drawdown", type=float, default=0.10)
    args = parser.parse_args()

    rows = observations_from_dicts(load_jsonl(Path(args.input)))
    report = evaluate_all(
        rows,
        min_observations=max(1, args.min_observations),
        min_sharpe=args.min_sharpe,
        max_drawdown=args.max_drawdown,
    )
    report["observations"] = len(rows)
    report["source"] = args.input

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
