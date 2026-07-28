"""Per-cycle market-data cache — one price per symbol per cycle.

A trading cycle is meant to be a single point-in-time decision, but the roles
that make it up each ask the broker for prices independently: the sleeve
valuation, the gross-exposure check, the strategy desks, and the execution
trader. Measured on an offline-sim cycle with three tickers, that was **33
market-data calls, with the same symbol priced four times**. In paper/live mode
every one of those is a network round trip.

Caching them is not only faster, it is more *correct*. Without it the desk can
value its equity at one price, size the position at a second, and fill against a
third, all inside one "instantaneous" decision. Pinning the price for the
duration of a cycle removes that inconsistency.

This wraps any adapter satisfying the broker contract (utils/broker.py) and
delegates everything it does not cache, so it works for Alpaca, IBKR, CCXT,
Robinhood and the simulator without any of them knowing about it. The cache is
cleared at the start of every cycle and whenever the simulator advances.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from utils.logger import get_logger

log = get_logger("quote_cache")


class CachedBroker:
    """Delegating broker wrapper with a per-cycle price/history cache."""

    def __init__(self, broker: Any):
        object.__setattr__(self, "_broker", broker)
        object.__setattr__(self, "_px", {})
        object.__setattr__(self, "_hist", {})
        object.__setattr__(self, "_stats", {"price_hits": 0, "price_calls": 0,
                                            "hist_hits": 0, "hist_calls": 0})

    # -- delegation ----------------------------------------------------------
    def __getattr__(self, name: str):
        return getattr(self._broker, name)

    def __setattr__(self, name: str, value) -> None:
        # keep the wrapper transparent: attribute writes land on the adapter
        if name in ("_broker", "_px", "_hist", "_stats"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._broker, name, value)

    # -- cache lifecycle -----------------------------------------------------
    def begin_cycle(self) -> None:
        """Drop everything cached. Called at the top of each trading cycle."""
        self._px.clear()
        self._hist.clear()

    def cache_stats(self) -> Dict[str, int]:
        return dict(self._stats)

    # -- cached reads --------------------------------------------------------
    def get_price(self, symbol: str) -> float:
        self._stats["price_calls"] += 1
        if symbol in self._px:
            self._stats["price_hits"] += 1
            return self._px[symbol]
        px = self._broker.get_price(symbol)
        # Never cache a failure: a 0.0 is the adapters' safe-degrade value, and
        # pinning it for a whole cycle would turn one bad quote into a cycle-wide
        # blackout (and a zero-priced equity curve).
        if px and px > 0:
            self._px[symbol] = px
        return px

    def get_history(self, symbol: str, days: int = 120):
        self._stats["hist_calls"] += 1
        key: Tuple[str, int] = (symbol, int(days))
        if key in self._hist:
            self._stats["hist_hits"] += 1
            return self._hist[key]
        hist = self._broker.get_history(symbol, days)
        try:
            if hist is not None and len(hist.get("closes", [])) > 0:
                self._hist[key] = hist
        except Exception:       # an adapter returning something odd must not crash
            pass
        return hist

    # -- writes that invalidate ---------------------------------------------
    def advance_sim(self, steps: int = 1) -> None:
        """The simulator moves prices, so anything cached is now stale."""
        self._broker.advance_sim(steps)
        self.begin_cycle()

    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        return self._broker.submit_equity_order(symbol, qty, side)

    def submit_option_order(self, contract: str, qty: int, side: str,
                            premium: float = 0.0) -> Dict:
        return self._broker.submit_option_order(contract, qty, side, premium)
