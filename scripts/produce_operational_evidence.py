#!/usr/bin/env python3
"""Produce and ingest genuine shadow/paper evidence; never calls a broker."""
from __future__ import annotations

import argparse
from math import sqrt
import json
import os
from pathlib import Path
from statistics import mean, pstdev
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from database.db import Database
from intelligence.promotion_pipeline import PromotionPipeline
from intelligence.shadow_eval import evaluate_all, observations_from_dicts
from promotion import PaperEvidenceProducer, ShadowEvidenceProducer


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _max_drawdown(returns: list[float]) -> float:
    equity = peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        worst = max(worst, 1.0 - equity / peak)
    return worst


def paper_metrics(db: Database) -> dict | None:
    rows = db.conn.execute("SELECT equity FROM equity_curve WHERE mode IN ('paper','offline-sim') ORDER BY id").fetchall()
    values = [float(row["equity"]) for row in rows if float(row["equity"] or 0) > 0]
    if len(values) < 2:
        return None
    returns = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    vol = pstdev(returns) if len(returns) > 1 else 0.0
    return {"observations": len(returns), "sharpe": mean(returns) / vol * sqrt(252) if vol else 0.0,
            "max_drawdown": _max_drawdown(returns), "data_quality": len(values) / len(rows),
            "operational_health": 1.0}


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce genuine resolved promotion evidence")
    parser.add_argument("--queue", default="data/promotion_queue")
    parser.add_argument("--shadow-input", default="data/ai_shadow_observations.jsonl")
    args = parser.parse_args()
    env = {**dotenv_values(".env"), **os.environ}
    key = env.get("PROMOTION_ARTIFACT_SIGNING_KEY")
    key_id = env.get("PROMOTION_ARTIFACT_KEY_ID", "primary")
    if not key:
        print(json.dumps({"healthy": False, "error": "signing key unavailable", "execution_authority": False}))
        return 3
    db = Database()
    pipeline = PromotionPipeline(db, artifact_signing_keys={key_id: key}, require_signatures=True)
    emitted = []
    shadow_rows = _rows(Path(args.shadow_input))
    if shadow_rows:
        report = evaluate_all(observations_from_dicts(shadow_rows), min_observations=20)
        producer = ShadowEvidenceProducer(queue_dir=Path(args.queue) / "shadow",
                                          signing_keys={key_id: key}, active_key_id=key_id)
        for score in report["providers"]:
            if not score["observations"]:
                continue
            candidate = score["provider"]
            pipeline.register(candidate, candidate.title(), "model")
            item = producer.emit(candidate, {"observations": score["observations"],
                "sharpe": score["annualized_sharpe"], "max_drawdown": score["max_drawdown"],
                "calibration_error": score["calibration_error"], "data_quality": score["schema_valid_rate"],
                "operational_health": max(0.0, 1.0 - score["fallback_rate"])})
            producer.deliver(item, pipeline.ingest_artifact)
            emitted.append(item["artifact_id"])
    metrics = paper_metrics(db)
    if metrics:
        producer = PaperEvidenceProducer(queue_dir=Path(args.queue) / "paper",
                                         signing_keys={key_id: key}, active_key_id=key_id)
        pipeline.register("paper-portfolio", "Paper Portfolio", "portfolio")
        item = producer.emit("paper-portfolio", metrics)
        producer.deliver(item, pipeline.ingest_artifact)
        emitted.append(item["artifact_id"])
    db.close()
    print(json.dumps({"emitted": emitted, "resolved_shadow_rows": len(shadow_rows),
                      "paper_ready": metrics is not None, "execution_authority": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
