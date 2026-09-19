"""Correlation-aware risk (advisory only).

Five small crypto positions that all move together are one big position wearing
a disguise. This module computes the CORRELATION-ADJUSTED effective exposure of
the book from pairwise return correlations:

    effective_exposure = nominal_exposure / diversification_ratio

where diversification_ratio = weighted_avg_vol / portfolio_vol (>= 1; equals 1
when everything is perfectly correlated, higher when positions diversify).

The Risk Officer REPORTS the effective exposure and ADVISES reductions on
concentration. It never changes a hard cap — caps stay exactly where they are;
this is an intelligence input to the same RiskEngine gates, and a dashboard
number Juan can see.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from utils.logger import get_logger

log = get_logger("correlation")


def _arr(x: Any) -> np.ndarray:
    try:
        a = np.asarray(x, dtype=float).ravel()
    except (TypeError, ValueError):
        return np.array([])
    return a[np.isfinite(a)]


def effective_exposure(positions: Dict[str, Dict[str, Any]],
                       closes_by_symbol: Dict[str, Any],
                       prices: Optional[Dict[str, float]] = None
                       ) -> Dict[str, Any]:
    """Return correlation-adjusted exposure. Never raises; degrades gracefully."""
    try:
        prices = prices or {}
        syms = [s for s, p in (positions or {}).items()
                if abs(float((p or {}).get("shares", 0) or 0)) > 0]
        nominal = 0.0
        weights: Dict[str, float] = {}
        rets: Dict[str, np.ndarray] = {}
        for s in syms:
            px = float(prices.get(s) or (positions[s] or {}).get("cost_basis") or 0)
            if not (math.isfinite(px) and px > 0):
                continue
            val = abs(float(positions[s].get("shares", 0) or 0)) * px
            if val <= 0:
                continue
            c = _arr((closes_by_symbol or {}).get(s))
            if c.size < 30 or np.any(c <= 0):
                continue  # no usable history → excluded from the correlation math
            nominal += val
            weights[s] = val
            rets[s] = np.diff(np.log(c[-60:]))
        if nominal <= 0 or len(weights) < 2:
            return {"status": "insufficient" if nominal > 0 else "flat",
                    "nominal": round(nominal, 2), "effective": round(nominal, 2),
                    "diversification_ratio": 1.0, "avg_pairwise_corr": None,
                    "advice": "single-name or no history — no correlation adjustment"}
        # normalize weights, align return series
        tot = sum(weights.values())
        w = {s: v / tot for s, v in weights.items()}
        n = min(len(r) for r in rets.values())
        mat = np.column_stack([rets[s][-n:] for s in w])
        vols = np.std(mat, axis=0)
        wavg_vol = float(sum(w[s] * vols[i] for i, s in enumerate(w)))
        wvec = np.array([w[s] for s in w])
        cov = np.cov(mat, rowvar=False)
        port_var = float(wvec @ cov @ wvec)
        port_vol = math.sqrt(max(port_var, 0.0))
        div_ratio = (wavg_vol / port_vol) if port_vol > 1e-12 else 1.0
        div_ratio = max(1.0, min(4.0, div_ratio))  # bounded — never a fantasy number
        # average pairwise correlation (off-diagonal)
        corr = np.corrcoef(mat, rowvar=False)
        k = len(w)
        off = [corr[i, j] for i in range(k) for j in range(k) if i != j]
        avg_corr = float(np.mean(off)) if off else 0.0
        effective = nominal / div_ratio
        advice = ("book is diversified" if div_ratio >= 1.5 else
                  "moderate concentration — watch correlated drawdowns" if div_ratio >= 1.15 else
                  "HIGH concentration: positions move together — consider trimming")
        return {"status": "ok",
                "nominal": round(nominal, 2),
                "effective": round(effective, 2),
                "diversification_ratio": round(div_ratio, 3),
                "avg_pairwise_corr": round(avg_corr, 3),
                "names": sorted(w),
                "advice": advice}
    except Exception as exc:  # advisory math never breaks the desk
        log.warning("correlation exposure failed: %s", exc)
        return {"status": "error", "nominal": None, "effective": None,
                "advice": f"unavailable ({exc})"}
