"""Deterministic execution-quality and PnL attribution utilities.

The goal is to distinguish strategy alpha from execution leakage. No broker calls
are performed here; this module is safe for simulation, shadow, and post-trade
analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ExecutionAttribution:
    side: str
    quantity: float
    reference_price: float
    fill_price: float
    gross_pnl: float
    fees: float = 0.0
    spread_cost: float = 0.0
    adverse_selection_cost: float = 0.0

    def __post_init__(self) -> None:
        side = self.side.lower().strip()
        values = (
            self.quantity,
            self.reference_price,
            self.fill_price,
            self.gross_pnl,
            self.fees,
            self.spread_cost,
            self.adverse_selection_cost,
        )
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("all attribution inputs must be finite")
        if self.quantity <= 0 or self.reference_price <= 0 or self.fill_price <= 0:
            raise ValueError("quantity and prices must be positive")
        if self.fees < 0 or self.spread_cost < 0 or self.adverse_selection_cost < 0:
            raise ValueError("cost components cannot be negative")

    @property
    def slippage_cost(self) -> float:
        direction = 1.0 if self.side.lower().strip() == "buy" else -1.0
        # Positive means execution was worse than reference; price improvement is
        # reported as zero cost rather than a negative fee-like number.
        raw = direction * (self.fill_price - self.reference_price) * self.quantity
        return max(0.0, raw)

    @property
    def execution_cost(self) -> float:
        return self.slippage_cost + self.fees + self.spread_cost + self.adverse_selection_cost

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.execution_cost

    @property
    def implementation_shortfall_bps(self) -> float:
        reference_notional = self.reference_price * self.quantity
        if reference_notional <= 0:
            return 0.0
        return self.execution_cost / reference_notional * 10_000.0

    def as_dict(self) -> dict[str, float | str]:
        return {
            "side": self.side.lower().strip(),
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "fill_price": self.fill_price,
            "gross_pnl": self.gross_pnl,
            "slippage_cost": self.slippage_cost,
            "fees": self.fees,
            "spread_cost": self.spread_cost,
            "adverse_selection_cost": self.adverse_selection_cost,
            "execution_cost": self.execution_cost,
            "net_pnl": self.net_pnl,
            "implementation_shortfall_bps": self.implementation_shortfall_bps,
        }
