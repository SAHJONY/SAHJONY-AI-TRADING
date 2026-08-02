"""Volatility breakout strategy with ATR-like range control.

Pure strategy; all orders remain subject to the central router and risk engine.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from strategies.base import OrderIntent, size_qty


class VolatilityBreakout:
    name = "volatility_breakout"

    def __init__(self, lookback: int = 20, exit_lookback: int = 10):
        self.lookback = lookback
        self.exit_lookback = exit_lookback

    def decide(self, symbol: str, closes, *, budget: float, state: dict[str, Any], fractional: bool = True) -> list[OrderIntent]:
        px = np.asarray(closes, dtype=float)
        if len(px) < self.lookback + 2 or px[-1] <= 0:
            return []
        prior = px[-(self.lookback + 1):-1]
        breakout = float(prior.max())
        exit_level = float(px[-(self.exit_lookback + 1):-1].min())
        returns = np.diff(np.log(px[-(self.lookback + 1):]))
        realized_vol = float(np.std(returns, ddof=1) * np.sqrt(252)) if len(returns) > 2 else 1.0
        position = (state.get("positions") or {}).get(symbol)

        if position is None and px[-1] > breakout:
            scale = max(0.20, min(1.0, 0.18 / max(realized_vol, 1e-6)))
            notional = budget * scale
            qty = size_qty(symbol, notional, float(px[-1]), 0, fractional=fractional)
            if qty <= 0:
                return []
            return [OrderIntent(
                symbol=symbol,
                strategy=self.name,
                kind="equity",
                purpose="volatility_breakout_entry",
                reason=f"close {px[-1]:.4f} above {self.lookback}d high {breakout:.4f}",
                side="buy",
                qty=qty,
                est_notional=qty * float(px[-1]),
                risk_check=True,
                set_position={"shares": qty, "entry": float(px[-1]), "strategy": self.name, "exit_level": exit_level},
            )]

        if position is not None and px[-1] < exit_level:
            qty = float(position.get("shares", position.get("qty", 0.0)) or 0.0)
            if qty <= 0:
                return []
            return [OrderIntent(
                symbol=symbol,
                strategy=self.name,
                kind="equity",
                purpose="volatility_breakout_exit",
                reason=f"close {px[-1]:.4f} below trailing exit {exit_level:.4f}",
                side="sell",
                qty=qty,
                risk_check=False,
                clear_position=True,
            )]
        return []
