"""Shared primitives for the venue layer: symbol normalization, the VenueSpec
record, and the per-venue live-ack gate helper.

A "venue" is one tradable market connection: an id (``robinhood_crypto``), an
asset kind (``crypto`` / ``stock`` / ``multi`` / ``sim``), a broker adapter
implementing the BrokerAdapter contract from utils/broker.py, the tickers it
owns, and its own risk caps.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List

# The exact real-money acknowledgement phrase, shared with config.py.
# Compared with == against the stripped env var; anything else fails closed.
ACK_PHRASE = "I_UNDERSTAND_REAL_MONEY"

_CRYPTO_QUOTES = {"USD", "USDT", "USDC"}


def normalize_symbol(symbol: str) -> str:
    """Canonical form for routing: upper-case, '-' and '/' treated alike."""
    return (symbol or "").strip().upper().replace("-", "/")


def is_crypto_like(symbol: str) -> bool:
    """Heuristic: BASE/QUOTE with a USD-family quote (BTC/USD, ETH-USDT)."""
    s = normalize_symbol(symbol)
    if "/" not in s:
        return False
    base, _, quote = s.partition("/")
    return bool(base) and quote in _CRYPTO_QUOTES


def venue_ack(var_name: str) -> bool:
    """True only when the named env var is exactly the real-money phrase."""
    return (os.getenv(var_name, "") or "").strip() == ACK_PHRASE


@dataclass
class VenueSpec:
    """One configured venue: adapter + routing metadata + per-venue caps."""
    venue_id: str
    adapter: Any                      # implements utils.broker.BrokerAdapter
    kind: str                         # "crypto" | "stock" | "multi" | "sim"
    tickers: List[str] = field(default_factory=list)   # normalized symbols
    max_order_usd: float = 25.0       # per-venue notional cap (router-enforced)
    live_requested: bool = False      # operator asked for :live in VENUES

    @property
    def live_armed(self) -> bool:
        return bool(getattr(self.adapter, "live_armed", False)
                    or getattr(self.adapter, "armed", False))

    def describe(self) -> dict:
        """Dashboard-safe snapshot. Never raises; unknown → zeros/False."""
        adapter = self.adapter
        try:
            acct = adapter.get_account() or {}
        except Exception:
            acct = {}
        try:
            online = bool(adapter.online)
        except Exception:
            online = False
        try:
            mode = str(getattr(adapter, "mode", "paper") or "paper")
        except Exception:
            mode = "paper"
        # Normalize the adapter's raw mode to the venue contract LIVE|paper.
        live = mode == "LIVE" or self.live_armed
        return {
            "id": self.venue_id,
            "kind": self.kind,
            "mode": "LIVE" if live else "paper",
            "detail": mode,
            "online": online,
            "live_armed": self.live_armed,
            "equity": round(float(acct.get("equity", 0.0) or 0.0), 2),
            "cash": round(float(acct.get("cash", 0.0) or 0.0), 2),
            "buying_power": round(float(acct.get("buying_power", 0.0) or 0.0), 2),
            "symbols": sorted(self.tickers),
            "symbol_count": len(self.tickers),
            "max_order_usd": round(float(self.max_order_usd or 0.0), 2),
            "live_requested": bool(self.live_requested),
        }
