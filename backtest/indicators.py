"""Indicator primitives for the 5m BTC backtests — pure NumPy, no I/O.

Every function is causal: the value at index i uses only bars 0..i. The one
exception is `fractals`, which by construction needs `k` bars of hindsight — it
returns a confirmation index alongside each level so callers can avoid using a
level before the market could actually have known about it. See `fractals`.
"""
from __future__ import annotations

import numpy as np


# ── moving averages ───────────────────────────────────────────────────────────
def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(x.size, np.nan)
    if x.size < n:
        return out
    c = np.cumsum(np.insert(x.astype(float), 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    x = x.astype(float)
    out = np.full(x.size, np.nan)
    if x.size < n:
        return out
    k = 2.0 / (n + 1.0)
    out[n - 1] = x[:n].mean()
    for i in range(n, x.size):
        out[i] = x[i] * k + out[i - 1] * (1 - k)
    return out


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's smoothing (RMA) — the basis of ATR/RSI/ADX."""
    x = x.astype(float)
    out = np.full(x.size, np.nan)
    if x.size < n:
        return out
    out[n - 1] = np.nanmean(x[:n])
    for i in range(n, x.size):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(x.size, np.nan)
    if x.size < n:
        return out
    for i in range(n - 1, x.size):
        out[i] = x[i - n + 1:i + 1].std(ddof=0)
    return out


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        out[i] = x[i - n + 1:i + 1].max()
    return out


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        out[i] = x[i - n + 1:i + 1].min()
    return out


def rolling_pct_rank(x: np.ndarray, n: int) -> np.ndarray:
    """Percentile rank (0-1) of x[i] within its trailing n-bar window."""
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        w = x[i - n + 1:i + 1]
        if np.isnan(w).any():
            continue
        out[i] = (w <= x[i]).sum() / n
    return out


# ── volatility ────────────────────────────────────────────────────────────────
def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev = np.roll(close, 1)
    prev[0] = close[0]
    return np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))


def atr(high, low, close, n: int = 14) -> np.ndarray:
    return wilder(true_range(high, low, close), n)


def bollinger(close: np.ndarray, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = rolling_std(close, n)
    return mid, mid + k * sd, mid - k * sd


def keltner(high, low, close, n: int = 20, k: float = 1.5):
    mid = ema(close, n)
    a = atr(high, low, close, n)
    return mid, mid + k * a, mid - k * a


def donchian(high, low, n: int = 20):
    """Prior-bar Donchian: the channel as it stood *before* the current bar, so a
    breakout test against it is not comparing the bar to itself."""
    hi = rolling_max(high, n)
    lo = rolling_min(low, n)
    return np.roll(hi, 1), np.roll(lo, 1)


# ── oscillators ───────────────────────────────────────────────────────────────
def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(close, prepend=close[0])
    up = wilder(np.clip(d, 0, None), n)
    dn = wilder(np.clip(-d, 0, None), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = up / dn
    out = 100.0 - 100.0 / (1.0 + rs)
    out[dn == 0] = 100.0
    out[(up == 0) & (dn == 0)] = 50.0
    return out


def adx(high, low, close, n: int = 14):
    """Returns (adx, plus_di, minus_di)."""
    up_move = np.diff(high, prepend=high[0])
    dn_move = -np.diff(low, prepend=low[0])
    plus_dm = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
    tr_n = wilder(true_range(high, low, close), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * wilder(plus_dm, n) / tr_n
        mdi = 100.0 * wilder(minus_dm, n) / tr_n
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)
    return wilder(np.nan_to_num(dx, nan=0.0), n), pdi, mdi


def linreg_value(x: np.ndarray, n: int) -> np.ndarray:
    """Endpoint value of an n-bar least-squares fit — the TTM momentum histogram."""
    out = np.full(x.size, np.nan)
    t = np.arange(n, dtype=float)
    t_c = t - t.mean()
    denom = (t_c ** 2).sum()
    for i in range(n - 1, x.size):
        w = x[i - n + 1:i + 1]
        if np.isnan(w).any():
            continue
        slope = (t_c * (w - w.mean())).sum() / denom
        out[i] = w.mean() + slope * t_c[-1]
    return out


# ── session-anchored VWAP ─────────────────────────────────────────────────────
def anchored_vwap(high, low, close, volume, day_id: np.ndarray):
    """VWAP + volume-weighted sigma, re-anchored whenever `day_id` changes.

    Returns (vwap, sigma). Typical price is the HLC3 of each bar.
    """
    tp = (high + low + close) / 3.0
    n = tp.size
    vwap = np.full(n, np.nan)
    sigma = np.full(n, np.nan)
    cum_v = cum_pv = cum_pv2 = 0.0
    cur = None
    for i in range(n):
        if day_id[i] != cur:
            cur, cum_v, cum_pv, cum_pv2 = day_id[i], 0.0, 0.0, 0.0
        v = max(float(volume[i]), 1e-12)
        cum_v += v
        cum_pv += v * tp[i]
        cum_pv2 += v * tp[i] * tp[i]
        m = cum_pv / cum_v
        vwap[i] = m
        var = max(cum_pv2 / cum_v - m * m, 0.0)
        sigma[i] = np.sqrt(var)
    return vwap, sigma


# ── structure ─────────────────────────────────────────────────────────────────
def fractals(high: np.ndarray, low: np.ndarray, k: int = 3):
    """Williams fractals with a k-bar shoulder on each side.

    A fractal at index i can only be *known* at index i + k. The returned arrays
    are indexed by bar and hold the level of the most recent fractal that was
    confirmed at or before that bar — so reading them inside a loop at bar t is
    causal by construction.
    """
    n = high.size
    fh = np.full(n, np.nan)   # level of last confirmed fractal high
    fl = np.full(n, np.nan)
    fh_idx = np.full(n, -1, dtype=int)
    fl_idx = np.full(n, -1, dtype=int)
    last_h = last_l = np.nan
    last_hi = last_li = -1
    for t in range(n):
        c = t - k                     # candidate whose right shoulder just closed
        if c - k >= 0:
            w_h = high[c - k:c + k + 1]
            w_l = low[c - k:c + k + 1]
            if high[c] == w_h.max() and (w_h.argmax() == k):
                last_h, last_hi = high[c], c
            if low[c] == w_l.min() and (w_l.argmin() == k):
                last_l, last_li = low[c], c
        fh[t], fl[t] = last_h, last_l
        fh_idx[t], fl_idx[t] = last_hi, last_li
    return fh, fl, fh_idx, fl_idx
