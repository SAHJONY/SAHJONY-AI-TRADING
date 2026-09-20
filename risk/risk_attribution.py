"""Marginal / component VaR + Expected Shortfall risk attribution (ADVISORY ONLY).

What this is
------------
A diagnostic that decomposes the portfolio's tail risk into per-position
contributions so the owner can see *which position dominates the book's
worst-day exposure* ("the VaR hog") and what a candidate trade would *add* to
that exposure before it is ever placed.

What this is NOT
---------------
This module is advisory only. It never alters, bypasses, or duplicates any
risk gate. The frozen risk envelope ($10/order, 12% per position, 70% total
deployed, 10% daily-drawdown halt) keeps every real gate; this module has no
order emission, no credential access, no circuit-breaker or data-feed control,
and cannot change live trading behavior. `incremental_trade_check` is exposed
as a PURE function the Risk Officer *could* read — it is NOT wired into any
approval path by this module.

The math
--------
Parametric (delta-normal) VaR at confidence c, z = Phi^-1(c):

    VaR_total = z * equity * sqrt(w^T Sigma w)

where w are signed position weights (longs positive, shorts negative —
shorts from the pairs desk show up honestly) and Sigma is the return
covariance matrix (volatilities x correlation).

Component VaR (Euler allocation — sums exactly to total VaR):

    marginal_VaR_i = z * equity * (Sigma w)_i / sqrt(w^T Sigma w)
    component_VaR_i = w_i * marginal_VaR_i

Expected Shortfall (conditional VaR): the mean loss on the days VaR is
breached. ES is the more informative tail measure than VaR because VaR only
answers "how often do we cross the line" while ES answers "how bad is it when
we do" — VaR is blind to tail shape and can even be non-subadditive; ES is
coherent (subadditive) and penalizes fat tails instead of ignoring them.
Under normality the parametric ES is a fixed multiple of VaR:

    ES_total = VaR_total * phi(z) / ((1 - Phi(z)) * z)

and component ES is allocated proportionally to component VaR, which is the
exact Euler allocation under elliptical (normal) returns.

A simple historical-simulation ES is ALSO reported whenever enough aligned
return observations exist: the average portfolio loss on days worse than the
historical VaR. On crypto books the historical number is usually the more
honest one, because the parametric version assumes normally distributed
returns — and crypto returns are fat-tailed and skewed, which normality
understates. Both are reported; each is labeled for what it is.

Honest limits
-------------
On a 5-position, ~$67 book these numbers are EDUCATIONAL/DIAGNOSTIC, not
precise: tiny samples make every estimate noisy, volatilities and
correlations are regime-unstable, and parametric VaR systematically
understates crypto tail risk. Read the ranking ("which name is the hog")
as signal; read the dollar figures as order-of-magnitude.

Unknown = None: positions without a usable price or enough return history
are EXCLUDED from the math and listed with a reason — never filled in with
an invented volatility. Failures are recorded as status payloads; nothing
here ever raises.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from utils.logger import get_logger

log = get_logger("risk_attribution")

# History windows / minimums. Small by design for a tiny book, but the
# historical-simulation ES needs a real tail to average over, so it asks
# for more observations before reporting anything (else None, flagged).
LOOKBACK = 60            # closes used per symbol (matches intel/correlation.py)
MIN_HISTORY = 20         # min closes to admit a symbol into the VaR math
MIN_HIST_SIM_OBS = 50   # min aligned return obs before historical ES is reported
DEFAULT_CONFIDENCE = 0.95


# --------------------------------------------------------------------------
# Normal-distribution helpers (no scipy dependency — keyless stdlib+np only)
# --------------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_ppf(p: float) -> Optional[float]:
    """Acklam's inverse-normal approximation; None outside (0, 1)."""
    if not (0.0 < p < 1.0):
        return None
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


# --------------------------------------------------------------------------
# Data preparation
# --------------------------------------------------------------------------
def _finite_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _prepare(positions: Dict[str, Dict[str, Any]],
             closes_by_symbol: Dict[str, Any],
             prices: Optional[Dict[str, float]],
             equity: Any
             ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Build signed weights + aligned return matrix.

    Returns (bundle, excluded) where bundle is None when the book cannot be
    measured. `excluded` lists symbols left out, each with a reason.
    """
    excluded: List[str] = []
    eq = _finite_float(equity)
    if eq is None or eq <= 0:
        return None, [("book", "non-positive or unknown equity")]
    prices = prices or {}
    closes_by_symbol = closes_by_symbol or {}
    vals: Dict[str, float] = {}
    for s, p in (positions or {}).items():
        shares = _finite_float((p or {}).get("shares"))
        if shares is None or shares == 0:
            continue
        px = _finite_float(prices.get(s)) or \
            _finite_float((p or {}).get("cost_basis"))
        if px is None or px <= 0:
            excluded.append((s, "no usable price"))
            continue
        vals[s] = shares * px  # signed: shorts stay negative
    if not vals:
        return None, excluded or [("book", "flat — no positions")]
    rets: Dict[str, np.ndarray] = {}
    for s in list(vals):
        try:
            c = np.asarray(closes_by_symbol.get(s), dtype=float).ravel()
        except (TypeError, ValueError):
            c = np.array([])
        c = c[np.isfinite(c)]
        if c.size < MIN_HISTORY or np.any(c <= 0):
            excluded.append((s, f"need >= {MIN_HISTORY} closes, have {int(c.size)}"))
            del vals[s]
            continue
        rets[s] = np.diff(np.log(c[-LOOKBACK:]))
    if len(vals) < 2:
        excluded.append(("book", "need >= 2 names with history for attribution"))
        return None, excluded
    names = sorted(vals)
    w = np.array([vals[s] / eq for s in names], dtype=float)  # signed equity weights
    n = min(len(rets[s]) for s in names)
    mat = np.column_stack([rets[s][-n:] for s in names])
    return ({"names": names, "weights": w, "returns": mat, "equity": eq,
             "n_obs": n, "values": {s: vals[s] for s in names}},
            excluded)


def _parametric(port: Dict[str, Any], z: float) -> Optional[Dict[str, Any]]:
    """Delta-normal VaR + component VaR + parametric ES."""
    w = port["weights"]
    eq = port["equity"]
    cov = np.cov(port["returns"], rowvar=False)
    sig = np.sqrt(np.maximum(np.diag(cov), 0.0))
    corr = np.zeros_like(cov)
    for i in range(len(sig)):
        for j in range(len(sig)):
            corr[i, j] = (cov[i, j] / (sig[i] * sig[j])
                          if sig[i] > 0 and sig[j] > 0 else (1.0 if i == j else 0.0))
    sigma_w = cov @ w
    port_var = float(w @ sigma_w)
    port_vol = math.sqrt(max(port_var, 0.0))
    var_total = z * eq * port_vol
    if port_vol < 1e-12 or var_total < 1e-12:
        marginal = np.zeros_like(w)
    else:
        marginal = z * eq * sigma_w / port_vol          # dVaR/dw_i
    comp_var = w * marginal                             # Euler: sums to VaR
    # Parametric ES = fixed multiple of VaR under normality; component ES is
    # the exact Euler allocation there (linear scaling of component VaR).
    tail = 1.0 - _norm_cdf(z)
    es_mult = (_norm_pdf(z) / (tail * z)) if tail > 0 and z > 0 else 1.0
    es_total = var_total * es_mult
    comp_es = comp_var * (es_mult if var_total > 1e-12 else 1.0)
    names = port["names"]
    vols = {s: round(float(sig[i]), 6) for i, s in enumerate(names)}
    components = []
    for i, s in enumerate(names):
        share = (float(comp_var[i] / var_total) if var_total > 1e-12 else 0.0)
        components.append({
            "symbol": s,
            "weight_pct": round(float(w[i]) * 100.0, 3),
            "value": round(float(port["values"][s]), 2),
            "vol_daily": vols[s],
            "component_var": round(float(comp_var[i]), 4),
            "component_es": round(float(comp_es[i]), 4),
            "share_of_var_pct": round(share * 100.0, 2),
        })
    components.sort(key=lambda c: c["component_var"], reverse=True)
    return {
        "var_total": round(float(var_total), 4),
        "es_total": round(float(es_total), 4),
        "es_multiple_of_var": round(float(es_mult), 4),
        "avg_pairwise_corr": round(float(np.mean(
            [corr[i, j] for i in range(len(names))
             for j in range(len(names)) if i != j])), 4) if len(names) > 1 else 0.0,
        "components": components,
        "var_hog": components[0]["symbol"] if components else None,
    }


def _historical_es(port: Dict[str, Any], confidence: float) -> Optional[Dict[str, Any]]:
    """Simple historical-simulation ES from the aligned portfolio return series.

    Returns None when there are not enough observations to average a real
    tail — a handful of points would make the number theater, not signal.
    """
    n = int(port["n_obs"])
    if n < MIN_HIST_SIM_OBS:
        return None
    rp = port["returns"] @ port["weights"]          # portfolio daily returns
    losses = -rp
    var_q = float(np.quantile(losses, confidence))  # historical VaR (return units)
    tail = losses[losses >= var_q]
    if tail.size == 0:
        return None
    es_ret = float(np.mean(tail))
    eq = port["equity"]
    return {
        "var": round(var_q * eq, 4),
        "es": round(es_ret * eq, 4),
        "observations": n,
        "tail_days": int(tail.size),
        "method": "historical_simulation",
    }


# --------------------------------------------------------------------------
# Public API — all advisory, all fault-isolated, none wired into any gate.
# --------------------------------------------------------------------------
def attribution_report(positions: Dict[str, Dict[str, Any]],
                       closes_by_symbol: Dict[str, Any],
                       prices: Optional[Dict[str, float]] = None,
                       equity: Any = None,
                       confidence: float = 0.95) -> Dict[str, Any]:
    """Decompose portfolio tail risk per position. Never raises.

    Returns a status payload: "ok" with component VaR / ES / VaR hog, or
    "flat" / "insufficient" / "invalid" / "error" with reasons — and never
    invented numbers (unknown legs are excluded, listed, and flagged).
    """
    try:
        z = _norm_ppf(confidence)
        if z is None:
            return {"status": "invalid",
                    "advice": f"confidence {confidence} not in (0, 1)"}
        port, excluded = _prepare(positions, closes_by_symbol, prices, equity)
        excl_list = [{"symbol": s, "reason": r} for s, r in excluded]
        if port is None:
            reasons = "; ".join(f"{s}: {r}" for s, r in excluded) or "no data"
            status = "flat" if any(r.startswith("flat") for _, r in excluded) \
                else ("invalid" if any("equity" in r for _, r in excluded)
                      else "insufficient")
            return {"status": status, "var_total": None, "es_total": None,
                    "components": [], "var_hog": None,
                    "excluded": excl_list,
                    "advice": f"attribution unavailable — {reasons}"}
        param = _parametric(port, z)
        hist = _historical_es(port, confidence)
        if param is None:
            return {"status": "error", "var_total": None, "es_total": None,
                    "components": [], "var_hog": None, "excluded": excl_list,
                    "advice": "parametric math failed on real data"}
        hist_es = hist["es"] if hist else None
        hog = param["var_hog"]
        advice = (f"VaR hog: {hog} — {param['components'][0]['share_of_var_pct']}% "
                  f"of portfolio tail risk. " if hog and param["components"] else "")
        advice += ("Tiny book — treat dollar figures as order-of-magnitude; "
                   "the ranking is the signal. Parametric VaR assumes normal "
                   "returns, which crypto violates (fat tails) — the "
                   "historical-simulation ES is the more honest tail read."
                   if hist else
                   "Tiny book — treat dollar figures as order-of-magnitude; "
                   f"only {port['n_obs']} aligned observations, below the "
                   f"{MIN_HIST_SIM_OBS} needed for a historical-simulation ES — "
                   "parametric numbers only.")
        return {
            "status": "ok",
            "confidence": confidence,
            "method": "parametric_delta_normal",
            "var_total": param["var_total"],
            "es_total": param["es_total"],
            "es_multiple_of_var": param["es_multiple_of_var"],
            "historical_simulation": hist,
            "historical_es": hist_es,
            "components": param["components"],
            "var_hog": hog,
            "avg_pairwise_corr": param["avg_pairwise_corr"],
            "names": param["components"] and [c["symbol"] for c in param["components"]] or [],
            "excluded": excl_list,
            "n_observations": port["n_obs"],
            "equity": round(float(port["equity"]), 2),
            "advice": advice,
        }
    except Exception as exc:  # advisory math never breaks the desk
        log.warning("risk attribution failed: %s", exc)
        return {"status": "error", "var_total": None, "es_total": None,
                "components": [], "var_hog": None, "excluded": [],
                "advice": f"unavailable ({exc})"}


def incremental_trade_check(symbol: str,
                            side: str,
                            notional_usd: Any,
                            positions: Dict[str, Dict[str, Any]],
                            closes_by_symbol: Dict[str, Any],
                            prices: Optional[Dict[str, float]] = None,
                            equity: Any = None,
                            confidence: float = 0.95) -> Dict[str, Any]:
    """Pre-trade incremental tail-risk check. Pure function. Never raises.

    Answers: "if this trade were added to the book as-is, how much VaR / ES
    would the portfolio gain?" A diversifying trade can show a SMALLER
    incremental VaR than its standalone risk; adding to the VaR hog shows a
    LARGER one.

    This is exposed for the Risk Officer to READ as an advisory input. It is
    NOT wired into any approval gate by this module — gates stay exactly as
    the frozen envelope defines them.

    `side`: "buy"/"long" adds positive exposure, "sell"/"short" negative.
    `notional_usd`: intended trade size in dollars (validated like the
    $10/order cap would see it — but this function does NOT enforce caps;
    it only measures).
    """
    try:
        sym = str(symbol or "").strip()
        if not sym:
            return {"status": "invalid", "advice": "missing symbol"}
        notional = _finite_float(notional_usd)
        if notional is None or notional <= 0:
            return {"status": "invalid",
                    "advice": f"notional {notional_usd!r} is not a positive number"}
        prices = dict(prices or {})
        s = side.lower() if isinstance(side, str) else ""
        sign = 1.0 if s in ("buy", "long", "add") else \
            (-1.0 if s in ("sell", "short", "reduce") else None)
        if sign is None:
            return {"status": "invalid",
                    "advice": f"side {side!r} not understood (buy/sell)"}
        if sym not in prices or _finite_float(prices.get(sym)) in (None,) or \
                (prices.get(sym) or 0) <= 0:
            # fall back to the existing position's cost basis if we hold it
            held = (positions or {}).get(sym) or {}
            cb = _finite_float(held.get("cost_basis"))
            if cb is not None and cb > 0:
                prices[sym] = cb
        before = attribution_report(positions, closes_by_symbol, prices,
                                    equity, confidence)
        # Build the hypothetical post-trade book (shallow copy; no state mutated)
        post = {k: dict(v or {}) for k, v in (positions or {}).items()}
        px = _finite_float(prices.get(sym))
        if px is None or px <= 0:
            return {"status": "insufficient",
                    "advice": f"{sym}: no usable price — incremental risk unknown, "
                              "not invented"}
        delta_shares = sign * notional / px
        cur = post.get(sym) or {}
        cur_shares = _finite_float(cur.get("shares")) or 0.0
        cur["shares"] = cur_shares + delta_shares
        if "cost_basis" not in cur or not _finite_float(cur.get("cost_basis")):
            cur["cost_basis"] = px
        post[sym] = cur
        after = attribution_report(post, closes_by_symbol, prices, equity, confidence)
        if before.get("status") != "ok" or after.get("status") != "ok":
            return {"status": "insufficient",
                    "before": before.get("status"), "after": after.get("status"),
                    "advice": "book not measurable before/after — "
                              "incremental risk unknown, not invented"}
        d_var = after["var_total"] - before["var_total"]
        d_es = after["es_total"] - before["es_total"]
        d_hist = None
        if before.get("historical_es") is not None and \
                after.get("historical_es") is not None:
            d_hist = round(after["historical_es"] - before["historical_es"], 4)
        return {
            "status": "ok",
            "symbol": sym,
            "side": side,
            "notional_usd": round(notional, 2),
            "var_before": before["var_total"],
            "var_after": after["var_total"],
            "incremental_var": round(d_var, 4),
            "es_before": before["es_total"],
            "es_after": after["es_total"],
            "incremental_es": round(d_es, 4),
            "incremental_historical_es": d_hist,
            "var_hog_before": before["var_hog"],
            "var_hog_after": after["var_hog"],
            "advice": (f"{sym} {side} ${notional:,.2f} adds "
                       f"${d_var:,.2f} VaR / ${d_es:,.2f} ES "
                       f"({before['confidence']:.0%} confidence). Advisory only — "
                       "no gate reads this number."),
        }
    except Exception as exc:  # advisory math never breaks the desk
        log.warning("incremental trade check failed: %s", exc)
        return {"status": "error", "advice": f"unavailable ({exc})"}
