"""Core computational engines — pure NumPy (no scipy).

These are honest, transparent implementations of standard quant primitives:
returns/vol, OLS alpha-beta, RSI/MACD, Black-Scholes + greeks + implied vol,
a bulk-volume VPIN estimator, a 2-state Gaussian regime model (EM), and an
Engle-Granger cointegration test. They are inputs to the agent council; none of
them is a guarantee of profit — they are estimators with well-known limitations.
"""
from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np

RISK_FREE = 0.04          # annualized, used for Black-Scholes
TRADING_DAYS = 252


# ── basic series helpers ─────────────────────────────────────────────────────
def to_array(x) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    return a[np.isfinite(a)]


def log_returns(prices) -> np.ndarray:
    p = to_array(prices)
    if p.size < 2:
        return np.array([])
    p = np.clip(p, 1e-9, None)
    return np.diff(np.log(p))


def annualized_vol(prices, periods_per_year: int = TRADING_DAYS) -> float:
    r = log_returns(prices)
    if r.size < 2:
        return 0.0
    return float(np.std(r, ddof=1) * math.sqrt(periods_per_year))


def zscore_last(series) -> float:
    a = to_array(series)
    if a.size < 2:
        return 0.0
    sd = np.std(a, ddof=1)
    if sd == 0:
        return 0.0
    return float((a[-1] - np.mean(a)) / sd)


def rsi(prices, period: int = 14) -> float:
    p = to_array(prices)
    if p.size < period + 1:
        return 50.0
    delta = np.diff(p)
    gains = np.clip(delta, 0, None)
    losses = -np.clip(delta, None, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, x.size):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def macd_hist(prices, fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    p = to_array(prices)
    if p.size < slow + signal:
        return 0.0
    macd = _ema(p, fast) - _ema(p, slow)
    sig = _ema(macd, signal)
    return float(macd[-1] - sig[-1])


def ols_alpha_beta(asset_returns: np.ndarray, bench_returns: np.ndarray) -> Dict[str, float]:
    """Regress asset on benchmark: r_a = alpha + beta*r_b + eps. Annualized alpha."""
    a = np.asarray(asset_returns, dtype=float)
    b = np.asarray(bench_returns, dtype=float)
    n = min(a.size, b.size)
    if n < 5:
        return {"alpha": 0.0, "beta": 1.0, "r2": 0.0, "resid_vol": 0.0}
    a, b = a[-n:], b[-n:]
    X = np.column_stack([np.ones(n), b])
    coef, *_ = np.linalg.lstsq(X, a, rcond=None)
    intercept, beta = float(coef[0]), float(coef[1])
    pred = X @ coef
    resid = a - pred
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((a - np.mean(a)) ** 2))
    r2 = 0.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    return {
        "alpha": intercept * TRADING_DAYS,            # annualized residual alpha
        "beta": beta,
        "r2": float(r2),
        "resid_vol": float(np.std(resid, ddof=1) * math.sqrt(TRADING_DAYS)),
    }


# ── Black-Scholes (options) ──────────────────────────────────────────────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S: float, K: float, T: float, sigma: float, kind: str = "put", r: float = RISK_FREE) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return max(0.0, (K - S) if kind == "put" else (S - K))
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_delta(S: float, K: float, T: float, sigma: float, kind: str = "put", r: float = RISK_FREE) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1) if kind == "call" else _norm_cdf(d1) - 1.0


def implied_vol(price: float, S: float, K: float, T: float, kind: str = "put", r: float = RISK_FREE) -> float:
    """Bisection IV solver. Returns 0.0 if it cannot bracket a solution."""
    if price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return 0.0
    lo, hi = 1e-4, 5.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        diff = bs_price(S, K, T, mid, kind, r) - price
        if abs(diff) < 1e-5:
            return float(mid)
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return float(0.5 * (lo + hi))


def iv_rank(current_vol: float, vol_history: np.ndarray) -> float:
    """Percentile rank of current vol within its own history (0-1)."""
    h = to_array(vol_history)
    if h.size < 5:
        return 0.5
    return float(np.mean(h <= current_vol))


# ── VPIN: bulk-volume order-flow toxicity (Persona 9) ───────────────────────
def vpin(prices, volumes, buckets: int = 20) -> float:
    """Simplified bulk-volume VPIN in [0,1]. Higher = more toxic/imbalanced flow."""
    p = to_array(prices)
    v = to_array(volumes)
    n = min(p.size, v.size)
    if n < buckets + 2:
        return 0.0
    p, v = p[-n:], v[-n:]
    dp = np.diff(p)
    sd = np.std(dp, ddof=1)
    if sd == 0:
        return 0.0
    # Bulk-volume classification: fraction of each bar's volume that is "buy".
    frac_buy = np.array([_norm_cdf(x / sd) for x in dp])
    vol = v[1:]
    buy = frac_buy * vol
    sell = (1 - frac_buy) * vol
    # aggregate into roughly equal-count buckets
    edges = np.array_split(np.arange(vol.size), buckets)
    imb = []
    for idx in edges:
        if idx.size == 0:
            continue
        vb, vs = float(buy[idx].sum()), float(sell[idx].sum())
        tot = vb + vs
        if tot > 0:
            imb.append(abs(vb - vs) / tot)
    return float(np.mean(imb)) if imb else 0.0


# ── 2-state Gaussian regime model via EM (Persona 11 — Medallion-style) ──────
def regime_model(returns: np.ndarray, iters: int = 50) -> Dict[str, object]:
    """Fit a 2-component Gaussian mixture to returns (EM), then derive a hard
    state path and its empirical transition matrix. State 0 = calm, 1 = stressed
    (ordered by variance). Returns current state + transition matrix."""
    r = to_array(returns)
    if r.size < 10:
        return {"state": 0, "p_stay_calm": 0.5, "p_stay_stress": 0.5,
                "transition": [[0.5, 0.5], [0.5, 0.5]], "stressed_prob": 0.0}
    mu = np.array([np.mean(r) - np.std(r), np.mean(r) + np.std(r)])
    var = np.array([np.var(r) * 0.5 + 1e-12, np.var(r) * 1.5 + 1e-12])
    pi = np.array([0.5, 0.5])
    for _ in range(iters):
        # E-step
        g = np.zeros((r.size, 2))
        for k in range(2):
            g[:, k] = pi[k] * np.exp(-0.5 * (r - mu[k]) ** 2 / var[k]) / math.sqrt(2 * math.pi * var[k])
        denom = g.sum(axis=1, keepdims=True)
        denom[denom == 0] = 1e-12
        g = g / denom
        # M-step
        nk = g.sum(axis=0)
        nk[nk == 0] = 1e-12
        mu = (g * r[:, None]).sum(axis=0) / nk
        var = (g * (r[:, None] - mu) ** 2).sum(axis=0) / nk + 1e-12
        pi = nk / r.size
    # order states by variance: 0 = calm, 1 = stressed
    order = np.argsort(var)
    g = g[:, order]
    path = g.argmax(axis=1)
    # empirical transition matrix
    trans = np.ones((2, 2)) * 1e-6
    for i in range(path.size - 1):
        trans[path[i], path[i + 1]] += 1
    trans = trans / trans.sum(axis=1, keepdims=True)
    return {
        "state": int(path[-1]),
        "stressed_prob": float(g[-1, 1]),
        "p_stay_calm": float(trans[0, 0]),
        "p_stay_stress": float(trans[1, 1]),
        "transition": trans.round(4).tolist(),
    }


# ── Engle-Granger cointegration (Persona 11) ─────────────────────────────────
def _adf_stat(series: np.ndarray) -> float:
    """Dickey-Fuller t-stat on a series (no constant/trend). More negative =
    more mean-reverting/stationary. Pure OLS, no scipy."""
    y = to_array(series)
    if y.size < 10:
        return 0.0
    dy = np.diff(y)
    ylag = y[:-1]
    X = ylag.reshape(-1, 1)
    coef, *_ = np.linalg.lstsq(X, dy, rcond=None)
    gamma = float(coef[0])
    resid = dy - X @ coef
    n = dy.size
    sigma2 = float(np.sum(resid ** 2) / max(1, n - 1))
    sxx = float(np.sum(ylag ** 2))
    if sxx <= 0 or sigma2 <= 0:
        return 0.0
    se = math.sqrt(sigma2 / sxx)
    return gamma / se if se > 0 else 0.0


def cointegration(y_prices, x_prices) -> Dict[str, float]:
    """Engle-Granger: regress y on x, ADF-test the residual spread.
    Returns hedge ratio, current spread z-score, and stationarity stat."""
    y = to_array(y_prices)
    x = to_array(x_prices)
    n = min(y.size, x.size)
    if n < 20:
        return {"hedge_ratio": 0.0, "spread_z": 0.0, "adf": 0.0, "cointegrated": 0.0}
    y, x = y[-n:], x[-n:]
    X = np.column_stack([np.ones(n), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    hedge = float(coef[1])
    spread = y - X @ coef
    adf = _adf_stat(spread)
    # ADF 5% critical value ~ -1.95 (no-constant case, asymptotic)
    return {
        "hedge_ratio": hedge,
        "spread_z": zscore_last(spread),
        "adf": adf,
        "cointegrated": 1.0 if adf < -1.95 else 0.0,
    }
