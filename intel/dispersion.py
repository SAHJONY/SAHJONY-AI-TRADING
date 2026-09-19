"""Disagreement-based conviction scaling.

When the council's agents disagree sharply, the "consensus" is fragile — this
module measures vote dispersion and scales conviction DOWN accordingly. When
historically-accurate agents align, full (already-capped) conviction is kept.

Hard safety rule: this scaler lives in [0.3, 1.0]. It can only REDUCE the
conviction the existing pipeline produced; it can never raise it, and it never
touches position caps, the $10/order ceiling, or the daily halt. Reductions
flow through the same RiskEngine gates as everything else.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

_SCALE_MIN = 0.3     # maximum disagreement haircut: keep at least 30%
_DISP_K = 2.5        # dispersion -> scale sensitivity


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def dispersion_scale(verdicts: List[Any],
                     weights: Optional[Dict[str, float]] = None,
                     accuracy: Optional[Dict[str, float]] = None,
                     k: Optional[float] = None
                     ) -> Tuple[float, Dict[str, Any]]:
    """Return (scale, detail). scale in [_SCALE_MIN, 1.0]. Never raises.

    `k` overrides the module default _DISP_K (the auto-tuner's `dispersion_k`);
    it is clamped to [0, 10] so tuning can only ever reduce conviction here.
    """
    try:
        weights = weights or {}
        accuracy = accuracy or {}
        rows = []
        for v in verdicts or []:
            name = str(getattr(v, "name", "?"))
            score = _finite(getattr(v, "score", 0.0))
            conf = _finite(getattr(v, "confidence", 0.0))
            w = _finite(weights.get(name), 1.0)
            rows.append((name, score, conf, w))
        if not rows:
            return 1.0, {"reason": "no verdicts", "dispersion": 0.0}
        wsum = sum(w * c for _, _, c, w in rows)
        if wsum <= 0:
            return 1.0, {"reason": "zero weight", "dispersion": 0.0}
        mean = sum(w * c * s for _, s, c, w in rows) / wsum
        var = sum(w * c * (s - mean) ** 2 for _, s, c, w in rows) / wsum
        dispersion = math.sqrt(max(0.0, var))

        # Alignment bonus: if agents with proven accuracy (>=55% hit-rate)
        # dominate the vote mass AND agree (low dispersion), keep full conviction.
        accurate_mass = sum(w * c for n, _, c, w in rows
                            if _finite(accuracy.get(n), 0.5) >= 0.55)
        aligned = accurate_mass / wsum >= 0.6 and dispersion < 0.25

        kk = _DISP_K if k is None else max(0.0, min(10.0, _finite(k, _DISP_K)))
        if aligned:
            scale = 1.0
            reason = "historically-accurate agents aligned"
        else:
            scale = max(_SCALE_MIN, 1.0 - dispersion * kk)
            reason = "disagreement haircut"
        return round(scale, 3), {
            "reason": reason,
            "dispersion": round(dispersion, 3),
            "accurate_mass_pct": round(accurate_mass / wsum, 3),
            "k": round(kk, 3),
        }
    except Exception:
        return 1.0, {"reason": "error → neutral", "dispersion": 0.0}
