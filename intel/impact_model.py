"""Pre-trade market-impact estimation — the square-root law.

Canonical form (Almgren–Chriss lineage, practitioner standard):

    expected_impact ≈ k · σ · sqrt(Q / ADV)

    - Q:    order quantity in shares (same units as ADV)
    - ADV:  average daily volume in shares (same units as Q)
    - σ:    daily volatility of the instrument, as a fraction (0.02 = 2%/day)
    - k:    dimensionless calibration constant (see below)

The result is expressed in basis points of the order's arrival price and is
SIGN-INDEPENDENT magnitude: it is the adverse cost a taker order is expected
to pay versus arrival, before any real execution is observed. It is the
forward-looking counterpart to intel/execution_quality.py, which measures
what actually happened (arrival vs fill). Units match: basis points.

Calibration and sources
-----------------------
The square-root dependence of market impact on the participation rate Q/ADV is
the most replicated empirical regularity in execution research:

* Almgren, R. & Chriss, N. (2000), "Optimal Execution of Portfolio
  Transactions" — the canonical framework this model's lineage follows.
* Bouchaud, J.-P., Farmer, J.D. & Lillo, F. (2009), "How Markets Slowly Digest
  Changes in Supply and Demand" — square-root law across markets.
* Frazzini, A., Israel, R. & Moskowitz, T.J. (2018), "Trading Costs" —
  practitioner calibration: k ≈ 1 (in units of daily σ per sqrt(participation))
  across thousands of institutional meta-orders; the default adopted here.

We keep k = 1.0 as a fixed, documented constant rather than fitting it,
because this desk's fill history is far too thin to estimate it and fitting
on noise would be worse than the industry prior.

WHAT THIS IS NOT — read before using
------------------------------------
Advisory and measurement ONLY. This module:
  * never emits orders, never sizes positions, never touches credentials;
  * never changes execution, routing, or order types;
  * never promises profit, edge, or capacity.

BLUNT TRUTH FOR THE OWNER: at $10 per order, Q/ADV is on the order of
one-in-a-million for anything liquid. The model will report expected impact
≈ 0.000 bps — that IS the result, and it is the point. It kills the excuse
that "slippage ate the edge": execution is provably not the bottleneck at
this scale. This model does NOT design better execution schedules at $10 —
there is nothing to schedule — and its what-if numbers must NEVER be used
to justify larger order sizes. Bigger sizes are a risk-envelope decision,
never an execution insight.

Input honesty: unknown = None. Q, ADV, and σ must come from the desk's real
data (positions, market-data bars, or the recorded venue tapes). Any missing
or non-physical input returns None — never an invented estimate. Failures are
recorded in the result's data_quality flag, never raised.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# Practitioner calibration: k ≈ 1 in units of daily σ per sqrt(participation).
# Fixed and documented; NOT fitted (see module docstring).
K_SQRT = 1.0

# Basis-points conversion: 1 bps = 1/10_000.
_BPS = 10_000.0


def _finite_positive(x: Any) -> Optional[float]:
    """Return x as a finite float > 0, else None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _finite_nonneg(x: Any) -> Optional[float]:
    """Return x as a finite float >= 0, else None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v >= 0 else None


def estimate_impact(
    symbol: str,
    qty: Any,
    adv: Any,
    sigma_daily: Any,
    *,
    price: Any = None,
    k: float = K_SQRT,
    provenance: str = "observed",
) -> Optional[Dict[str, Any]]:
    """Expected pre-trade market impact in basis points.

    Parameters
    ----------
    symbol: instrument identifier (echoed, never parsed).
    qty: order size in shares (> 0). Use abs(quantity) for shorts before
        calling; the model is directionless by construction.
    adv: average daily volume in shares (> 0), same units as qty.
    sigma_daily: daily volatility as a fraction (e.g. 0.02 = 2%/day; >= 0).
    price: optional reference price — only used to convert bps into an
        estimated dollar cost; never required.
    k: dimensionless calibration constant; defaults to K_SQRT (documented
        practitioner prior). Exposed for sensitivity analysis only.
    provenance: "observed" (default) for real desk data, or the caller's own
        marker (e.g. "estimated") when an input is derived. Echoed verbatim.

    Returns None when any required input is missing or non-physical — unknown
    is None, never invented. Pure function: no network, no file or global
    state access, no mutation of its arguments.
    """
    q = _finite_positive(qty)
    v = _finite_positive(adv)
    sig = _finite_nonneg(sigma_daily)
    if q is None or v is None or sig is None:
        return None
    try:
        kk = float(k)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(kk) or kk < 0:
        return None

    participation = q / v
    impact_frac = kk * sig * math.sqrt(participation)
    impact_bps = impact_frac * _BPS

    p = _finite_positive(price)
    est_cost_usd = round(impact_frac * p * q, 6) if p is not None else None

    return {
        "symbol": str(symbol),
        "expected_impact_bps": round(impact_bps, 4),
        "participation_rate": participation,
        "est_cost_usd": est_cost_usd,
        "inputs": {
            "qty": q,
            "adv": v,
            "sigma_daily": sig,
            "k": kk,
            "price": p,
        },
        "data_quality": "complete",
        "provenance": provenance,
        "model": "square_root_law",
        "note": "advisory measurement only — never sizes orders, never executes",
    }


def what_if_size(
    symbol: str,
    hypothetical_qty: Any,
    adv: Any,
    sigma_daily: Any,
    *,
    price: Any = None,
    k: float = K_SQRT,
    provenance: str = "observed",
) -> Optional[Dict[str, Any]]:
    """What would the model have predicted for a HYPOTHETICAL larger size?

    Measurement-only stress probe for the backtest/analysis path: "had the
    order been this size, what impact would the square-root law have
    predicted?" The result is tagged hypothetical and must never feed back
    into sizing, routing, or capacity decisions — it is a what-if gauge, not
    permission. Same input honesty as estimate_impact: missing/invalid inputs
    return None.
    """
    res = estimate_impact(symbol, hypothetical_qty, adv, sigma_daily,
                          price=price, k=k, provenance=provenance)
    if res is None:
        return None
    res["hypothetical"] = True
    res["note"] = ("what-if measurement only — must never feed sizing, "
                   "routing, or capacity decisions")
    return res


def batch_estimate(entries: List[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Estimate impact for many symbols at once; missing inputs → None entry.

    entries: list of dicts with keys symbol, qty, adv, sigma_daily (plus
    optional price, k, provenance). Returns {symbol: result-or-None}. Pure:
    the input list and its dicts are never mutated.
    """
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        sym = str(e.get("symbol", ""))
        out[sym] = estimate_impact(
            sym,
            e.get("qty"),
            e.get("adv"),
            e.get("sigma_daily"),
            price=e.get("price"),
            k=e.get("k", K_SQRT),
            provenance=e.get("provenance", "observed"),
        )
    return out
