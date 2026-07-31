#!/usr/bin/env python3
"""Evaluate AI advisory providers from resolved JSONL observations.

Input rows must match intelligence.shadow_eval.ShadowObservation. The command is
read-only with respect to brokerage accounts and cannot submit orders.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Support both `python -m scripts.shadow_evaluate` and the documented direct
# invocation `python scripts/shadow_evaluate.py` from the repository.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from intelligence.shadow_eval import evaluate_all, observations_from_dicts
from intelligence.autonomous_learning import AutonomousLearningPipeline
from promotion import ShadowEvidenceProducer


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
    parser.add_argument("--evidence-queue", default="data/promotion_queue/shadow")
    parser.add_argument("--no-evidence", action="store_true",
                        help="Do not enqueue canonical promotion evidence")
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
    report["leaders"] = AutonomousLearningPipeline(
        min_observations=max(1, args.min_observations),
        min_sharpe=args.min_sharpe,
        max_drawdown=args.max_drawdown,
    )._leaders(load_jsonl(Path(args.input)))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    if not args.no_evidence:
        key = os.getenv("PROMOTION_ARTIFACT_SIGNING_KEY")
        key_id = os.getenv("PROMOTION_ARTIFACT_KEY_ID", "primary")
        producer = ShadowEvidenceProducer(
            queue_dir=args.evidence_queue,
            signing_keys={key_id: key} if key else None,
            active_key_id=key_id if key else "unsigned",
        )
        report["evidence_artifacts"] = []
        for score in report["providers"]:
            artifact = producer.emit(score["provider"], {
                "observations": score["observations"],
                "sharpe": score["annualized_sharpe"],
                "max_drawdown": score["max_drawdown"],
                "calibration_error": score["calibration_error"],
                "data_quality": score["schema_valid_rate"],
                "operational_health": max(0.0, 1.0 - score["fallback_rate"]),
            })
            report["evidence_artifacts"].append(artifact["artifact_id"])
        output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
