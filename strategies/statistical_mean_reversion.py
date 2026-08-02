"""Statistical mean-reversion strategy with z-score entry and exit.

Designed for liquid assets and research/paper validation first. It is a pure
strategy and cannot bypass the central account router or risk engine.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from strategies.base import OrderIntent, size_qty


class StatisticalMeanReversion:
    name = "statistical_mean_reversion"

    def __init__(self, lookback: int = 30, entry_z: float = -2.0, exit_z: float = -0.25):
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z

    def decide(self, symbol: str, closes, *, budget: float, state: dict[str, Any], fractional: bool = True) -> list[OrderIntent]:
        px = np.asarray(closes, dtype=float)
        if len(px) < self.lookback or px[-1] <= 0:
            return []
        window = px[-self.lookback:]
        mean = float(window.mean())
        std = float(window.std(ddof=1))
        if std <= 0:
            return []
        z = (float(px[-1]) - mean) / std
        position = (state.get("positions") or {}).get(symbol)

        if position is None and z <= self.entry_z:
            # Smaller size for more volatile deviations; no leverage-up behavior.
            dispersion = std / max(mean, 1e-9)
            scale = max(0.20, min(0.75, 0.03 / max(dispersion, 1e-6)))
            notional = budget * scale
            qty = size_qty(symbol, notional, float(px[-1]), 0, fractional=fractional)
            if qty <= 0:
                return []
            return [OrderIntent(
                symbol=symbol,
                strategy=self.name,
                kind="equity",
                purpose="mean_reversion_entry",
                reason=f"z-score {z:.2f} below entry threshold {self.entry_z:.2f}",
                side="buy",
                qty=qty,
                est_notional=qty * float(px[-1]),
                risk_check=True,
                set_position={"shares": qty, "entry": float(px[-1]), "strategy": self.name, "entry_z": z},
            )]

        if position is not None and z >= self.exit_z:
            qty = float(position.get("shares", position.get("qty", 0.0)) or 0.0)
            if qty <= 0:
                return []
            return [OrderIntent(
                symbol=symbol,
                strategy=self.name,
                kind="equity",
                purpose="mean_reversion_exit",
                reason=f"z-score normalized to {z:.2f}",
                side="sell",
                qty=qty,
                risk_check=False,
                clear_position=True,
            )]
        return []
