"""Normalized market-data event schema for Institutional Runtime V2.

Pure data contracts only: no sockets, broker calls, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math


@dataclass(frozen=True)
class QuoteEvent:
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    ts_exchange: datetime | None = None
    ts_received: datetime | None = None
    venue: str = ""

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol is required")
        vals = (self.bid, self.ask, self.bid_size, self.ask_size)
        if not all(math.isfinite(float(v)) for v in vals):
            raise ValueError("quote values must be finite")
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError("bid and ask must be positive")
        if self.ask < self.bid:
            raise ValueError("crossed quote")
        if self.bid_size < 0 or self.ask_size < 0:
            raise ValueError("sizes cannot be negative")

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> float:
        return self.spread / self.mid * 10_000.0

    @property
    def age_ms(self) -> float | None:
        if self.ts_exchange is None or self.ts_received is None:
            return None
        ex = self.ts_exchange
        rx = self.ts_received
        if ex.tzinfo is None:
            ex = ex.replace(tzinfo=timezone.utc)
        if rx.tzinfo is None:
            rx = rx.replace(tzinfo=timezone.utc)
        return max(0.0, (rx - ex).total_seconds() * 1000.0)


@dataclass(frozen=True)
class TradeEvent:
    symbol: str
    price: float
    size: float
    side: str = "unknown"  # buy/sell/unknown aggressor
    ts_exchange: datetime | None = None
    venue: str = ""

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol is required")
        if not math.isfinite(float(self.price)) or not math.isfinite(float(self.size)):
            raise ValueError("trade values must be finite")
        if self.price <= 0 or self.size <= 0:
            raise ValueError("price and size must be positive")
        if self.side not in {"buy", "sell", "unknown"}:
            raise ValueError("side must be buy, sell, or unknown")
