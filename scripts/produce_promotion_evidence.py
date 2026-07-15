#!/usr/bin/env python3
"""Enqueue canonical evidence from a stage result JSON file; never executes trades."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion import (BacktestEvidenceProducer, CanaryEvidenceProducer,
                       PaperEvidenceProducer, ShadowEvidenceProducer,
                       WalkForwardEvidenceProducer)

PRODUCERS = {"backtest": BacktestEvidenceProducer,
             "walk_forward": WalkForwardEvidenceProducer,
             "paper": PaperEvidenceProducer, "shadow": ShadowEvidenceProducer,
             "canary": CanaryEvidenceProducer}


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce broker-free promotion evidence")
    parser.add_argument("stage", choices=sorted(PRODUCERS))
    parser.add_argument("candidate_id")
    parser.add_argument("metrics_json", type=Path)
    parser.add_argument("--queue", default="data/promotion_queue")
    args = parser.parse_args()
    metrics = json.loads(args.metrics_json.read_text())
    key, key_id = os.getenv("PROMOTION_ARTIFACT_SIGNING_KEY"), os.getenv("PROMOTION_ARTIFACT_KEY_ID", "primary")
    producer = PRODUCERS[args.stage](
        queue_dir=Path(args.queue) / args.stage,
        signing_keys={key_id: key} if key else None,
        active_key_id=key_id if key else "unsigned",
    )
    artifact = producer.emit(args.candidate_id, metrics)
    print(json.dumps(artifact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
