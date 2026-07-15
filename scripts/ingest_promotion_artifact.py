#!/usr/bin/env python3
"""Verify and ingest one promotion evidence artifact. No execution authority."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database
from intelligence.promotion_pipeline import PromotionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest an immutable or HMAC-signed evidence artifact")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--actor", default="research-ci")
    args = parser.parse_args()
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    database = Database()
    try:
        pipeline = PromotionPipeline(
            database,
            artifact_signing_key=os.getenv("PROMOTION_ARTIFACT_SIGNING_KEY") or None,
            require_signatures=args.require_signature,
        )
        result = pipeline.ingest_artifact(artifact, actor=args.actor)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if not result["breaches"] else 2
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
