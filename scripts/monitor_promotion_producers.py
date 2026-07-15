#!/usr/bin/env python3
"""Publish promotion-producer health and optionally alert on failures.

Safe for cron/launchd. This process has no broker or execution authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion.producer_monitor import publish_status, send_webhook


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor signed promotion evidence producers")
    parser.add_argument("--queue-dir", default=os.getenv("PROMOTION_ARTIFACT_QUEUE_DIR", "data/promotion_queue"))
    parser.add_argument("--status", default=os.getenv("PROMOTION_PRODUCER_STATUS_PATH", "public/promotion_producers.json"))
    parser.add_argument("--max-pending", type=int, default=int(os.getenv("PROMOTION_MAX_PENDING", "25")))
    parser.add_argument("--max-freshness-seconds", type=int,
                        default=int(os.getenv("PROMOTION_MAX_FRESHNESS_SECONDS", "3600")))
    parser.add_argument("--max-delivery-lag-seconds", type=int,
                        default=int(os.getenv("PROMOTION_MAX_DELIVERY_LAG_SECONDS", "3600")))
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args()

    webhook = os.getenv("PROMOTION_ALERT_WEBHOOK_URL", "").strip()
    sink = (lambda payload: send_webhook(payload, webhook)) if webhook else None
    try:
        payload = publish_status(
            queue_dir=args.queue_dir,
            status_path=args.status,
            alert_sink=sink,
            max_pending=max(0, args.max_pending),
            max_freshness_seconds=max(60, args.max_freshness_seconds),
            max_delivery_lag_seconds=max(60, args.max_delivery_lag_seconds),
        )
    except Exception as exc:
        print(json.dumps({"healthy": False, "error": f"{type(exc).__name__}: {exc}",
                          "execution_authority": False}, indent=2))
        return 3
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 2 if args.fail_on_critical and not payload["healthy"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
