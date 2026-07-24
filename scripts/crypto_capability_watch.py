#!/usr/bin/env python3
"""Watch the read-only Robinhood crypto-position capability for transitions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import broker_diagnostics, broker_evidence

DEFAULT_STATE = ROOT / "data" / "crypto_capability_watch.json"
DEFAULT_PUBLIC = ROOT / "public" / "crypto_capability.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def probe() -> dict[str, Any]:
    cfg = broker_diagnostics._config()
    if not cfg["token"]:
        return {"supported": False, "reason": "gateway_token_missing",
                "position_count": 0, "observed_at": _now(), "probe_ok": False}
    status, payload = broker_diagnostics._get(
        cfg["url"], cfg["token"], "/capabilities/crypto-positions", timeout=120
    )
    if status != 200 or not isinstance(payload, dict):
        return {"supported": False, "reason": "probe_unavailable",
                "position_count": 0, "observed_at": _now(), "probe_ok": False}
    supported = payload.get("supported") is True
    positions = payload.get("positions")
    if not isinstance(positions, list):
        return {"supported": False, "reason": "invalid_probe_payload",
                "position_count": 0, "observed_at": _now(), "probe_ok": False}
    return {"supported": supported, "reason": str(payload.get("reason", "")),
            "position_count": len(positions), "observed_at": _now(),
            "probe_ok": True}


def run_once(*, state_path: Path = DEFAULT_STATE, public_path: Path = DEFAULT_PUBLIC,
             probe_fn: Callable[[], dict[str, Any]] = probe,
             reconcile_fn: Callable[..., Any] = broker_evidence.produce) -> dict[str, Any]:
    current = probe_fn()
    previous = None
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    changed = bool(previous is not None
                   and previous.get("supported") is not current.get("supported"))
    recovered = bool(previous is not None and not previous.get("probe_ok")
                     and current.get("probe_ok"))
    transition = None
    if changed:
        transition = {"from": bool(previous.get("supported")),
                      "to": bool(current["supported"]), "at": _now()}
    state = {**current, "last_transition": transition or (
        previous.get("last_transition") if isinstance(previous, dict) else None
    )}
    _write(state_path, state)
    if previous is None or changed or recovered:
        _write(public_path, {**state, "changed": changed, "read_only": True,
                             "execution_authority": False, "trading_ready": False})
    reconciliation_rerun = False
    if changed and current["supported"] and current["position_count"] > 0:
        reconcile_fn()
        reconciliation_rerun = True
    result = {**state, "changed": changed, "reconciliation_rerun": reconciliation_rerun}
    if changed:
        print(json.dumps({"event": "crypto_capability_transition", **result}, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch authenticated crypto enumeration support")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    interval = max(60, args.interval_seconds)
    while True:
        run_once()
        if not args.watch:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
