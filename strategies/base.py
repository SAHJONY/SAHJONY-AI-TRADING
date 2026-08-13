"""Shared types for strategy decision engines.

Strategies are PURE: they read state + market + council and emit OrderIntents.
They never touch the broker or the DB — the workforce's Risk Officer and
Execution Trader do that. This keeps domain logic testable and I/O isolated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional


# crypto quote currencies recognized in the BASE-QUOTE spelling
_CRYPTO_QUOTES = ("USD", "USDT", "USDC", "USDD")


def is_crypto(symbol: str) -> bool:
    """True for a crypto pair in EITHER venue spelling.

    Alpaca and CCXT write BASE/QUOTE (BTC/USD); Robinhood writes BASE-QUOTE
    (BTC-USD), and any position adopted from a Robinhood holdings snapshot enters
    state in that form. Recognizing only the '/' form meant a BTC-USD position was
    treated as an equity: it was charged the 4bp equity fee instead of 60bp crypto
    (understating cost ~15x in realized P&L, the equity curve and Hermes'
    learning), and size_qty() rounded its fractional quantity down to zero whole
    "shares" — so the order was never placed at all.

    Hyphenated equity tickers are unaffected: 'BRK-B' ends in 'B', not a quote
    currency, so it stays an equity.
    """
    s = str(symbol or "").upper()
    if "/" in s:
        return True
    if "-" in s:
        return s.rsplit("-", 1)[-1] in _CRYPTO_QUOTES
    return False


def fee_cost(symbol: str, notional: float, cfg) -> float:
    """Estimated ROUND-TRIP transaction cost in dollars for `notional` traded.

    Commission-free venues are not cost-free: the spread/markup is the real fee,
    and on the small orders this desk places it can exceed a day-trade's target.
    Booking it against realized P&L keeps the equity curve, the scorecard and
    Hermes' learning honest instead of flattering gross numbers.
    """
    try:
        n = abs(float(notional or 0.0))
    except (TypeError, ValueError):
        return 0.0
    if n <= 0:
        return 0.0
    bps = float(getattr(cfg, "fee_bps_crypto", 0.0) if is_crypto(symbol)
                else getattr(cfg, "fee_bps_equity", 0.0) or 0.0)
    return max(0.0, n * bps / 10_000.0)


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

def validate_order_intent(intent: OrderIntent) -> str | None:
    """Return a blocker for malformed broker-bound orders, otherwise ``None``.

    This gate is intentionally independent of ``risk_check``: exits must remain
    possible during a risk halt, but malformed exits must never reach a broker.
    """
    if not intent.is_order:
        return "intent is not a broker order"
    if not str(intent.symbol or "").strip():
        return "missing symbol"

    allowed_sides = {
        "equity": {"buy", "sell"},
        "option": {"buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close"},
    }
    if intent.side not in allowed_sides[intent.kind]:
        return f"invalid {intent.kind} side"
    if intent.kind == "option" and not str(intent.contract or "").strip():
        return "missing option contract"

    for name in ("qty", "est_notional", "strike", "premium"):
        try:
            value = float(getattr(intent, name))
        except (TypeError, ValueError):
            return f"invalid {name.replace('_', ' ')}"
        if not math.isfinite(value):
            return f"invalid {name.replace('_', ' ')}"
        if name == "qty" and value <= 0:
            return "quantity must be positive"
        if name != "qty" and value < 0:
            return f"negative {name.replace('_', ' ')}"
    return None
