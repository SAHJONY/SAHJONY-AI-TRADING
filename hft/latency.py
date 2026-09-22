"""Latency model for the simulator (research only).

Real HFT venues operate in single-digit microseconds with hardware
timestamps. This module models the *idea* of latency — a configurable
one-way exchange delay plus lognormal jitter — so strategies can be tested
for latency sensitivity in simulation. All timestamps are integer
nanoseconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass(frozen=True)
class LatencyConfig:
    one_way_ns: int = 250_000  # 250 microseconds one-way
    jitter_sigma: float = 0.25  # lognormal sigma on the delay; 0 = deterministic
    seed: int = 0

    def __post_init__(self) -> None:
        if self.one_way_ns < 0:
            raise ValueError("one_way_ns must be non-negative")
        if self.jitter_sigma < 0:
            raise ValueError("jitter_sigma must be non-negative")


class LatencyModel:
    """Delays actions and market data by a sampled one-way latency."""

    def __init__(self, config: Optional[LatencyConfig] = None) -> None:
        self.config = config or LatencyConfig()
        if self.config.one_way_ns < 0:
            raise ValueError("one_way_ns must be non-negative")
        if self.config.jitter_sigma < 0:
            raise ValueError("jitter_sigma must be non-negative")
        self._rng = np.random.default_rng(self.config.seed)

    def _sample_delay_ns(self) -> int:
        base = self.config.one_way_ns
        if self.config.jitter_sigma == 0:
            return base
        # lognormal jitter centred so the median delay equals one_way_ns
        sample = float(self._rng.lognormal(mean=0.0, sigma=self.config.jitter_sigma))
        return base + int(base * sample)

    def apply(self, action_ts_ns: int) -> int:
        """Return the exchange-receipt timestamp for an action sent at
        ``action_ts_ns`` (decision time -> exchange time)."""
        if not isinstance(action_ts_ns, int) or action_ts_ns < 0:
            raise ValueError("action_ts_ns must be a non-negative integer")
        return action_ts_ns + self._sample_delay_ns()

    def apply_market_data(self, exchange_ts_ns: int) -> int:
        """Return the strategy-receipt timestamp for market data stamped at
        the exchange (exchange time -> decision time)."""
        if not isinstance(exchange_ts_ns, int) or exchange_ts_ns < 0:
            raise ValueError("exchange_ts_ns must be a non-negative integer")
        return exchange_ts_ns + self._sample_delay_ns()

    def round_trip_ns(self) -> int:
        """One sampled round-trip (action + market-data leg)."""
        return self._sample_delay_ns() + self._sample_delay_ns()


class TickToTradeTracker:
    """Measures simulated tick-to-trade latency: signal time -> fill time."""

    def __init__(self) -> None:
        self._samples: List[int] = []

    def record(self, signal_ts_ns: int, fill_ts_ns: int) -> None:
        if fill_ts_ns < signal_ts_ns:
            raise ValueError("fill cannot precede signal")
        self._samples.append(fill_ts_ns - signal_ts_ns)

    def stats(self) -> dict:
        if not self._samples:
            return {"count": 0}
        a = np.asarray(self._samples, dtype=np.float64)
        return {
            "count": int(a.size),
            "mean_ns": float(a.mean()),
            "p50_ns": float(np.percentile(a, 50)),
            "p95_ns": float(np.percentile(a, 95)),
            "p99": float(np.percentile(a, 99)),
            "max_ns": float(a.max()),
            "mean_us": float(a.mean() / 1_000.0),
        }
