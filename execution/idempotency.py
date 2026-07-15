"""Stable execution-intent identities for crash-safe duplicate prevention."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def intent_payload(intent: Any, cycle: int) -> dict[str, Any]:
    return {
        "cycle": int(cycle), "symbol": str(intent.symbol).upper(),
        "strategy": str(intent.strategy), "kind": str(intent.kind),
        "purpose": str(intent.purpose), "side": str(intent.side),
        "qty": float(intent.qty), "contract": str(intent.contract),
        "strike": float(intent.strike), "premium": float(intent.premium),
        "est_notional": float(intent.est_notional),
    }


def execution_intent_id(intent: Any, cycle: int) -> tuple[str, dict[str, Any]]:
    payload = intent_payload(intent, cycle)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), payload
