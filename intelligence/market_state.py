"""Compressed, broker-agnostic market state for the GPT-5.6 challenger."""
from __future__ import annotations

import math
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class MarketStateSnapshot:
    symbol: str
    ts: float
    price: float
    return_1: float
    momentum_fast: float
    momentum_slow: float
    realized_vol: float
    zscore: float
    order_flow_imbalance: float = 0.0
    spread_bps: float = 0.0
    funding_bps: float = 0.0
    open_interest_change: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(values: Iterable[float]) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v) and v > 0:
            out.append(v)
    return out


def build_market_state(
    symbol: str,
    prices: Iterable[float],
    *,
    microstructure: Mapping[str, float] | None = None,
    now: float | None = None,
) -> MarketStateSnapshot:
    """Compress a price history into deterministic, bounded features.

    No exchange, broker, execution or LLM code is imported here. A minimum of
    20 valid positive prices is required so the slow-window features are not
    fabricated from an undersized history.
    """
    px = _finite(prices)
    if len(px) < 20:
        raise ValueError("at least 20 finite positive prices are required")
    returns = [px[i] / px[i - 1] - 1.0 for i in range(1, len(px))]
    fast_n = min(5, len(px) - 1)
    slow_n = min(20, len(px) - 1)
    momentum_fast = px[-1] / px[-1 - fast_n] - 1.0
    momentum_slow = px[-1] / px[-1 - slow_n] - 1.0
    rv_window = returns[-min(20, len(returns)):]
    realized_vol = statistics.pstdev(rv_window) if len(rv_window) > 1 else 0.0
    level_window = px[-20:]
    level_mean = statistics.fmean(level_window)
    level_std = statistics.pstdev(level_window)
    zscore = 0.0 if level_std <= 0 else (px[-1] - level_mean) / level_std
    micro = dict(microstructure or {})

    def bounded(name: str, lo: float, hi: float) -> float:
        try:
            value = float(micro.get(name, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        return max(lo, min(hi, value))

    return MarketStateSnapshot(
        symbol=str(symbol).strip().upper(),
        ts=float(time.time() if now is None else now),
        price=px[-1],
        return_1=returns[-1],
        momentum_fast=momentum_fast,
        momentum_slow=momentum_slow,
        realized_vol=max(0.0, realized_vol),
        zscore=max(-8.0, min(8.0, zscore)),
        order_flow_imbalance=bounded("order_flow_imbalance", -1.0, 1.0),
        spread_bps=bounded("spread_bps", 0.0, 5000.0),
        funding_bps=bounded("funding_bps", -5000.0, 5000.0),
        open_interest_change=bounded("open_interest_change", -1.0, 10.0),
        metadata={k: v for k, v in micro.items() if k not in {
            "order_flow_imbalance", "spread_bps", "funding_bps", "open_interest_change"
        }},
    )
