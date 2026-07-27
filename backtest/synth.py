"""Synthetic 5m BTC-like bars — for exercising the harness, NOT for evaluation.

This generator produces a series with realistic *shape* (volatility clustering,
fat tails, intraday seasonality, trend/range alternation, volume correlated with
absolute returns) but it is a random process with no market microstructure in it.

Results computed on synthetic data measure whether the engine's plumbing works —
fills, fees, sizing, exits, accounting. They say **nothing** about whether a
strategy has edge, and must never be reported as if they did. Any edge that shows
up here is either luck or a bug in the harness.
"""
from __future__ import annotations

import numpy as np

from backtest.data import Bars

BAR_MS = 300_000


def make(days: int = 180, seed: int = 7, start_price: float = 65_000.0,
         start_ms: int = 1_735_689_600_000) -> Bars:
    rng = np.random.default_rng(seed)
    n = days * 288
    ts = start_ms + np.arange(n, dtype=np.int64) * BAR_MS

    # intraday seasonality: quiet Asia, active London/US
    mod = (ts % 86_400_000) // 60_000
    seas = 0.75 + 0.55 * np.exp(-0.5 * ((mod - 810) / 220.0) ** 2) \
                + 0.30 * np.exp(-0.5 * ((mod - 420) / 180.0) ** 2)

    # GARCH(1,1)-style conditional volatility with occasional jumps
    omega, alpha, beta = 1.2e-8, 0.08, 0.90
    var = np.empty(n)
    var[0] = omega / max(1e-9, 1 - alpha - beta)
    eps = np.empty(n)
    z = rng.standard_t(df=4.0, size=n) / np.sqrt(4.0 / 2.0)
    for i in range(n):
        if i:
            var[i] = omega + alpha * eps[i - 1] ** 2 + beta * var[i - 1]
        eps[i] = np.sqrt(var[i]) * seas[i] * z[i]
    jump = (rng.random(n) < 0.0006) * rng.normal(0, 0.010, n)

    # slow-moving drift so the series alternates between trend and range
    drift = np.zeros(n)
    k = 0
    while k < n:
        span = int(rng.integers(288, 288 * 9))
        drift[k:k + span] = rng.normal(0, 3.0e-5)
        k += span

    ret = eps + jump + drift
    close = start_price * np.exp(np.cumsum(ret))

    # build OHLC from a 6-step sub-bar path so wicks are internally consistent
    steps = 6
    sub = rng.normal(0, 1, (n, steps))
    sub -= sub.mean(axis=1, keepdims=True)
    prev = np.concatenate([[start_price], close[:-1]])
    path = prev[:, None] * np.exp(
        np.cumsum(sub * (np.abs(ret) * 0.55)[:, None], axis=1)
        + (np.log(close / prev) / steps)[:, None] * np.arange(1, steps + 1))
    path[:, -1] = close
    high = np.maximum(path.max(axis=1), np.maximum(prev, close))
    low = np.minimum(path.min(axis=1), np.minimum(prev, close))

    base_vol = 40.0 * seas
    volume = base_vol * (1.0 + 18.0 * np.abs(ret) / (np.abs(ret).mean() + 1e-12) ** 1.0
                         * 0.05) * rng.lognormal(0, 0.45, n)

    return Bars(ts=ts, open=prev, high=high, low=low, close=close,
                volume=np.maximum(volume, 0.1), symbol="SYNTH-BTC", tf_minutes=5)
