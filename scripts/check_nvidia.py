"""Read-only NVIDIA API/model preflight.

Prints status, model and latency only. It never prints credentials, accesses a
broker, evaluates a strategy, or submits an order.
"""
from __future__ import annotations

import json

from config import load_config
from intelligence.ai_brain import AIBrain


def main() -> int:
    result = AIBrain(load_config()).nvidia_healthcheck()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
