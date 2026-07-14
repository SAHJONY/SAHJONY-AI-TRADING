"""Shared types for strategy decision engines.

Strategies are PURE: they read state + market + council and emit OrderIntents.
They never touch the broker or the DB — the workforce's Risk Officer and
Execution Trader do that. This keeps domain logic testable and I/O isolated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


def is_crypto(symbol: str) -> bool:
    """Alpaca crypto pairs are written BASE/QUOTE, e.g. BTC/USD."""
    return "/" in symbol


def size_qty(symbol: str, budget: float, price: float, max_units: int,
             fractional: bool = False) -> float:
    """Position size in units. Crypto is always fractional. Equities are whole
    shares unless `fractional` is set (dollar-based investing), which lets a small
    account buy a slice of an expensive name instead of rounding down to zero.
    A positive `max_units` caps the size; a non-positive one means 'no unit cap'."""
    if price <= 0 or budget <= 0:
        return 0.0
    raw = budget / price
    if max_units and max_units > 0:
        raw = min(raw, float(max_units))
    if is_crypto(symbol) or fractional:
        return round(raw, 6)
    return float(int(raw))


@dataclass
class OrderIntent:
    symbol: str
    strategy: str                 # 'wheel' | 'ladder'
    kind: str                     # 'equity' | 'option' | 'state'
    purpose: str                  # e.g. 'open_csp', 'ladder_entry', 'trail_exit'
    reason: str = ""
    side: str = ""                # 'buy' | 'sell' | 'sell_to_open' | 'buy_to_close'
    qty: float = 0.0              # shares/contracts (equity/option) or coins (crypto, fractional)
    contract: str = ""
    strike: float = 0.0
    premium: float = 0.0          # per-share option premium
    est_notional: float = 0.0     # capital at risk this order (for the gatekeeper)
    risk_check: bool = False      # gate through the Risk Engine?
    # how to mutate persistent state once the order fills:
    set_position: Optional[Dict] = None     # replace the symbol's position record
    merge_position: Optional[Dict] = field(default=None)  # shallow-merge into it
    clear_position: bool = False            # remove the position (back to flat)
    premium_delta: float = 0.0              # add to cumulative premium collected
    realized_delta: float = 0.0             # add to cumulative realized P&L

    @property
    def is_order(self) -> bool:
        return self.kind in ("equity", "option")
