#!/usr/bin/env python3
"""Resolve due AI shadow observations and refresh the public leaderboard.

No orders are created or submitted. The selected broker is used for read-only
prices only. Run from cron/launchd every few minutes.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import load_config
from intelligence.shadow_eval import evaluate_all, observations_from_dicts
from intelligence.shadow_pipeline import ShadowPipeline
from utils.broker import get_broker


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def main() -> int:
    cfg = load_config()
    broker = get_broker(cfg)
    pipeline = ShadowPipeline()
    result = pipeline.resolve_due(broker.get_price)
    rows = observations_from_dicts(read_jsonl(pipeline.resolved_path))
    report = evaluate_all(rows, min_observations=20)
    report["pipeline"] = {**pipeline.counts(), **result}
    report["safety"] = {
        "shadow_only": True,
        "orders_enabled": False,
        "live_flags_ignored": True,
    }
    target = Path("public/ai_shadow.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
