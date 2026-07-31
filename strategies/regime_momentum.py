"""Regime-aware momentum strategy.

Pure strategy module: consumes a close series and emits OrderIntent objects. It
never talks to a broker. The workforce/risk engine remains the execution gate.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from strategies.base import OrderIntent, size_qty


class RegimeMomentum:
    name = "regime_momentum"

    def __init__(self, fast: int = 20, slow: int = 80, vol_lookback: int = 30):
        self.fast = fast
        self.slow = slow
        self.vol_lookback = vol_lookback

    def decide(
        self,
        symbol: str,
        closes,
        *,
        budget: float,
        state: dict[str, Any],
        fractional: bool = True,
    ) -> list[OrderIntent]:
        px = np.asarray(closes, dtype=float)
        if len(px) < self.slow + 2 or px[-1] <= 0:
            return []
        fast = float(px[-self.fast :].mean())
        slow = float(px[-self.slow :].mean())
        rets = np.diff(np.log(px[-(self.vol_lookback + 1) :]))
        ann_vol = float(np.std(rets, ddof=1) * np.sqrt(252)) if len(rets) > 2 else 1.0
        trend = fast / slow - 1.0
        position = (state.get("positions") or {}).get(symbol)

        # Require a meaningful trend and reduce size as volatility rises.
        if trend > 0.01 and position is None:
            risk_scale = max(0.25, min(1.0, 0.20 / max(ann_vol, 1e-6)))
            notional = max(0.0, budget * risk_scale)
            qty = size_qty(symbol, notional, float(px[-1]), 0, fractional=fractional)
            if qty <= 0:
                return []
            return [OrderIntent(
                symbol=symbol,
                strategy=self.name,
                kind="equity",
                purpose="regime_momentum_entry",
                reason=f"fast/slow trend {trend:+.2%}; annualized vol {ann_vol:.1%}",
                side="buy",
                qty=qty,
                est_notional=qty * float(px[-1]),
                risk_check=True,
                set_position={"shares": qty, "entry": float(px[-1]), "strategy": self.name},
            )]

        if position is not None and trend < -0.005:
            qty = float(position.get("shares", position.get("qty", 0.0)) or 0.0)
            if qty <= 0:
                return []
            return [OrderIntent(
                symbol=symbol,
                strategy=self.name,
                kind="equity",
                purpose="regime_momentum_exit",
                reason=f"trend reversal {trend:+.2%}",
                side="sell",
                qty=qty,
                est_notional=0.0,
                risk_check=False,
                clear_position=True,
            )]
        return []
