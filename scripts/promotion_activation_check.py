#!/usr/bin/env python3
"""Secret-safe readiness check for promotion evidence automation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from database.db import Database
from scripts.produce_operational_evidence import paper_metrics

REQUIRED_LOCAL = ("PROMOTION_ARTIFACT_SIGNING_KEY", "PROMOTION_ARTIFACT_KEY_ID",
                  "PROMOTION_STATUS_PUBLISH_TOKEN", "PROMOTION_STATUS_URL",
                  "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN")


def main() -> int:
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    checks = {name: bool(env.get(name)) and "<" not in str(env.get(name)) for name in REQUIRED_LOCAL}
    db = Database()
    paper_ready = paper_metrics(db) is not None
    db.close()
    resolved = ROOT / "data/ai_shadow_observations.jsonl"
    resolved_count = sum(1 for line in resolved.read_text().splitlines() if line.strip()) if resolved.exists() else 0
    try:
        loaded = subprocess.run(["launchctl", "list", "com.sahjony.promotion-evidence-producer"],
                                capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        loaded = False
    hosted = None
    if checks["PROMOTION_STATUS_URL"]:
        try:
            with request.urlopen(str(env["PROMOTION_STATUS_URL"]), timeout=8) as response:
                hosted = response.status == 200
        except Exception:
            hosted = False
    blockers = [f"missing local configuration: {name}" for name, ok in checks.items() if not ok]
    if not loaded:
        blockers.append("evidence producer LaunchAgent is not loaded")
    if hosted is False:
        blockers.append("hosted status endpoint is not ready")
    payload = {"ready": not blockers, "configuration": checks, "paper_evidence_ready": paper_ready,
               "resolved_shadow_observations": resolved_count, "producer_launch_agent_loaded": loaded,
               "hosted_status_ready": hosted, "blockers": blockers,
               "canary_enabled": False, "production_enabled": False,
               "execution_authority": False}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
