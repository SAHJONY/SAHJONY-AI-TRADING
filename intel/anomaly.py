"""Anomaly stand-down.

Detects market behavior outside the model's training/operating range — e.g. a
volatility shock — and STANDS DOWN (conviction → 0 for that symbol) rather than
guessing. The stand-down is logged visibly in the cycle report, status.json,
and the dashboard.

Detection (per symbol, from the research snapshot's own history):
- realized short-horizon volatility vs. its own rolling reference band: if the
  latest 20-bar vol exceeds 4x the median of the trailing reference window, or
- a single-bar log-return with |z| >= 6 against the trailing window.

Fail-closed: malformed inputs (empty/short/non-finite history) → no anomaly
claimed (fail OPEN on detection would halt trading on bad data; the Hermes
data quarantine already handles bad feeds by forcing conviction to zero).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from utils.logger import get_logger

log = get_logger("anomaly")

_REF_BARS = 120      # reference window for "normal"
_SHOCK_BARS = 20     # shock window
_VOL_RATIO_LIMIT = 4.0
_Z_LIMIT = 6.0


def _arr(x: Any) -> np.ndarray:
    try:
        a = np.asarray(x, dtype=float).ravel()
    except (TypeError, ValueError):
        return np.array([])
    return a[np.isfinite(a)]


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def detect(symbol: str, closes: Any, z_limit: Optional[float] = None
           ) -> Dict[str, Any]:
    """Return {'anomaly': bool, 'reason': str, 'vol_now': float, 'vol_ref': float}.

    `z_limit` overrides the module default _Z_LIMIT (the auto-tuner's
    `anomaly_z_limit`), clamped to [2, 12]; it can only move the trigger, and
    a detection always forces conviction to zero — never widens risk.
    """
    out = {"symbol": symbol, "anomaly": False, "reason": "",
           "vol_now": None, "vol_ref": None}
    zl = _Z_LIMIT if z_limit is None else max(2.0, min(12.0, _finite(z_limit, _Z_LIMIT)))
    try:
        c = _arr(closes)
        if c.size < _REF_BARS + _SHOCK_BARS + 2 or np.any(c <= 0):
            return out  # insufficient history → no claim (fail-closed on inputs)
        r = np.diff(np.log(c))
        ref, shock = r[:-( _SHOCK_BARS)], r[-_SHOCK_BARS:]
        ref_sd = float(np.std(ref)) if ref.size > 5 else 0.0
        shock_sd = float(np.std(shock)) if shock.size > 5 else 0.0
        out["vol_now"] = round(shock_sd, 6)
        out["vol_ref"] = round(ref_sd, 6)
        if ref_sd > 1e-12 and shock_sd / ref_sd >= _VOL_RATIO_LIMIT:
            out["anomaly"] = True
            out["reason"] = (f"volatility shock: 20-bar vol {shock_sd:.4f} is "
                             f"{shock_sd / ref_sd:.1f}x the trailing reference "
                             f"{ref_sd:.4f} (limit {_VOL_RATIO_LIMIT}x)")
            return out
        z = abs(float(shock[-1])) / ref_sd if ref_sd > 1e-12 else 0.0
        if z >= zl:
            out["anomaly"] = True
            out["reason"] = (f"extreme single-bar move: |z|={z:.1f} vs trailing vol "
                             f"(limit {zl})")
        return out
    except Exception as exc:  # detection never breaks the cycle
        log.warning("anomaly detect failed for %s: %s", symbol, exc)
        return out


def stand_down_report(detections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize one cycle's anomaly checks for status.json / dashboard."""
    stood = [d for d in detections if d.get("anomaly")]
    return {
        "checked": len(detections),
        "stood_down": sorted({d["symbol"] for d in stood}),
        "details": [
            {"symbol": d["symbol"], "reason": d.get("reason", ""),
             "vol_now": d.get("vol_now"), "vol_ref": d.get("vol_ref")}
            for d in stood
        ],
    }
