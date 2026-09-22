"""Synthetic L2 market-data feed (research only — no real market data).

:class:`FeedHandler` is the consumer abstraction: anything that wants market
data implements :meth:`FeedHandler.on_event`.

:class:`SyntheticL2Feed` is a deterministic, seeded generator that emits a
busy limit order book in *simulation time*:

* midprice follows a Gaussian random walk (configurable volatility),
* spread is stochastic (1–4 ticks),
* depth is stochastic across the top ``depth_levels`` levels,
* a fraction of events are trade prints with a Lee-Ready-style aggressor
  sign (print at/through the ask = buyer-initiated, at/below the bid =
  seller-initiated; here the generator simply tags the side it printed
  against).

Events are generated in vectorized per-second chunks with numpy, so
thousands of events per sim-second stay cheap. Timestamps are integer
nanoseconds, strictly increasing. Nothing here touches a network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

from .book import BUY, SELL

LEVEL = "level"  # quote update: new total non-self qty at (side, price)
TRADE = "trade"  # trade print: aggressor side took qty at price


@dataclass(frozen=True)
class FeedEvent:
    kind: str  # LEVEL or TRADE
    ts_ns: int
    side: int  # BUY/SELL; for LEVEL = book side, for TRADE = aggressor side
    price: int  # integer ticks
    qty: int  # for LEVEL: new total qty at the level; for TRADE: print size


class FeedHandler:
    """Base class for market-data consumers."""

    def on_event(self, event: FeedEvent) -> None:
        raise NotImplementedError


class SyntheticL2Feed:
    """Deterministic synthetic L2 feed.

    Parameters
    ----------
    seed: RNG seed — same seed reproduces the identical event stream.
    sim_seconds: length of the simulation in seconds (sim time).
    events_per_sec: mean event rate (quotes + trades). A busy-book feel
        needs this in the thousands.
    start_mid_ticks: starting midprice in integer ticks.
    tick_vol: random-walk sigma of the midprice per sqrt(second), in ticks.
    trade_fraction: share of events that are trade prints.
    depth_levels: number of price levels per side that receive updates.
    """

    def __init__(
        self,
        seed: int = 0,
        sim_seconds: float = 60.0,
        events_per_sec: int = 2000,
        start_mid_ticks: int = 10_000,
        tick_vol: float = 2.0,
        trade_fraction: float = 0.15,
        depth_levels: int = 10,
    ) -> None:
        if sim_seconds <= 0:
            raise ValueError("sim_seconds must be positive")
        if events_per_sec <= 0:
            raise ValueError("events_per_sec must be positive")
        if not 0.0 <= trade_fraction <= 1.0:
            raise ValueError("trade_fraction must be in [0, 1]")
        self.seed = seed
        self.sim_seconds = sim_seconds
        self.events_per_sec = events_per_sec
        self.start_mid = int(start_mid_ticks)
        self.tick_vol = float(tick_vol)
        self.trade_fraction = float(trade_fraction)
        self.depth_levels = int(depth_levels)
        self._rng = np.random.default_rng(seed)

    def estimate_event_count(self) -> int:
        return int(self.sim_seconds * self.events_per_sec)

    def __iter__(self) -> Iterator[FeedEvent]:
        rng = self._rng
        n_per_sec = self.events_per_sec
        dt_ns = 1_000_000_000 // n_per_sec
        mid = float(self.start_mid)
        step_sigma = self.tick_vol / np.sqrt(n_per_sec)
        full_seconds = int(self.sim_seconds)
        t0 = 0

        for _ in range(full_seconds):
            n = n_per_sec
            # --- timestamps: evenly spaced + small jitter, strictly increasing
            times = t0 + np.arange(n, dtype=np.int64) * dt_ns
            times = times + rng.integers(0, max(1, dt_ns // 2), n, dtype=np.int64)
            # --- midprice random walk (one step per event)
            mid = mid + np.cumsum(rng.normal(0.0, step_sigma, n))
            mid_i = np.maximum(10, np.rint(mid)).astype(np.int64)
            # --- stochastic spread 1..4 ticks
            spread = rng.integers(1, 5, n).astype(np.int64)
            best_bid = mid_i - spread // 2
            best_ask = best_bid + spread
            # --- event kinds
            is_trade = rng.random(n) < self.trade_fraction
            kind = np.where(is_trade, TRADE, LEVEL)
            # --- sides: for levels, book side; for trades, aggressor side
            side_raw = rng.integers(0, 2, n)  # 0 -> BUY, 1 -> SELL
            side = np.where(side_raw == 0, BUY, SELL)
            # --- levels for quote events
            lvl = rng.integers(0, self.depth_levels, n).astype(np.int64)
            lvl_price = np.where(
                side_raw == 0, best_bid - lvl, best_ask + lvl
            )
            lvl_qty = (rng.integers(1, 120, n) // (lvl + 1)) + 1
            # --- trades: print at the touch, Lee-Ready-style sign = touch side
            trd_price = np.where(side_raw == 0, best_ask, best_bid)
            trd_qty = rng.integers(1, 25, n)
            price = np.where(is_trade, trd_price, lvl_price).astype(np.int64)
            qty = np.where(is_trade, trd_qty, lvl_qty).astype(np.int64)

            for i in range(n):
                yield FeedEvent(
                    kind=str(kind[i]),
                    ts_ns=int(times[i]),
                    side=int(side[i]),
                    price=int(price[i]),
                    qty=int(qty[i]),
                )
            t0 += 1_000_000_000
