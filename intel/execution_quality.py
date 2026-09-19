"""Execution quality intelligence — arrival-price vs fill-price measurement.

For every order the desk places we record the ARRIVAL price (the market price
the moment the intent was formed) and, when the fill is known, the FILL price.
Slippage in basis points:

    slippage_bps = side_sign * (fill - arrival) / arrival * 10000

Positive = paid more than arrival (adverse for a buy). Persisted to JSONL,
summarized for the dashboard. MEASUREMENT AND REPORTING ONLY — this module
never changes routing, never touches order types, and maker/limit placement
policy stays exactly where the execution path already enforces it (limit
orders on the Robinhood review gate).

Where fills are not observable (paper/sim fills are synthetic), the module
records what it can and marks the provenance — real vs simulated — so the
dashboard never presents synthetic fills as measured quality.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from paths import home
from utils.logger import get_logger

log = get_logger("exec_quality")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class ExecutionQuality:
    """Arrival-vs-fill slippage ledger."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(home(), "data", "execution_quality.jsonl")
        self.enabled = str(os.getenv("EXECUTION_QUALITY_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")
        self._pending: Dict[str, Dict[str, Any]] = {}   # intent_id -> intent record
        self._fills: List[Dict[str, Any]] = []          # measured fills (memory mirror)

    # ── capture ───────────────────────────────────────────────────────────────
    def record_intent(self, intent_id: str, *, symbol: str, side: str, qty: float,
                      arrival_price: float, limit_price: Optional[float] = None,
                      provenance: str = "live") -> None:
        try:
            a = _finite(arrival_price)
            if a is None or a <= 0:
                return
            self._pending[str(intent_id)] = {
                "intent_id": str(intent_id), "symbol": str(symbol),
                "side": str(side), "qty": _finite(qty) or 0.0,
                "arrival_price": a, "limit_price": _finite(limit_price),
                "ts": _now(), "provenance": provenance,
            }
        except Exception as exc:
            log.warning("intent record failed: %s", exc)

    def record_fill(self, intent_id: str, fill_price: float,
                    fill_qty: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Match a fill to its intent; compute slippage. Returns the fill record."""
        try:
            intent = self._pending.pop(str(intent_id), None)
            f = _finite(fill_price)
            if intent is None or f is None or f <= 0:
                return None
            arrival = intent["arrival_price"]
            sign = 1.0 if str(intent["side"]).startswith("buy") else -1.0
            slip_bps = sign * (f - arrival) / arrival * 10000.0
            rec = {**intent, "fill_price": f,
                   "fill_qty": _finite(fill_qty) if fill_qty is not None else intent["qty"],
                   "slippage_bps": round(slip_bps, 2),
                   "fill_ts": _now()}
            del rec["limit_price"]  # keep the ledger compact; limit kept on intent side
            self._fills.append(rec)
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            except Exception as exc:
                log.warning("fill persist failed (kept in memory): %s", exc)
            return rec
        except Exception as exc:
            log.warning("fill record failed: %s", exc)
            return None

    # ── reporting ─────────────────────────────────────────────────────────────
    def _all(self) -> List[Dict[str, Any]]:
        if self._fills:
            return list(self._fills)
        rows: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except (json.JSONDecodeError, ValueError):
                            continue
        except OSError:
            pass
        self._fills = rows
        return list(rows)

    def summary(self, last_n: int = 100) -> Dict[str, Any]:
        rows = self._all()[-max(1, int(last_n)):]
        slips = [_finite(r.get("slippage_bps")) for r in rows]
        slips = [s for s in slips if s is not None]
        by_sym: Dict[str, List[float]] = {}
        for r in rows:
            s = _finite(r.get("slippage_bps"))
            if s is not None:
                by_sym.setdefault(str(r.get("symbol")), []).append(s)
        return {
            "fills_measured": len(rows),
            "avg_slippage_bps": round(sum(slips) / len(slips), 2) if slips else None,
            "worst_slippage_bps": round(max(slips, key=abs), 2) if slips else None,
            "adverse_fills": sum(1 for s in slips if s > 0),
            "by_symbol": {s: round(sum(v) / len(v), 2) for s, v in by_sym.items()},
            "provenance": sorted({str(r.get("provenance") or "unknown") for r in rows}),
            "note": ("synthetic fills are marked by provenance; "
                     "only 'live' rows are measured execution quality"),
        }
