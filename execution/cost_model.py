"""Conservative deterministic transaction-cost model for simulation evidence."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class FillEstimate:
    reference_price: float
    fill_price: float
    slippage_cost: float
    commission: float

    @property
    def transaction_cost(self) -> float:
        return self.slippage_cost + self.commission


def estimate_equity_fill(reference_price: float, qty: float, side: str, *,
                         slippage_bps: float = 5.0,
                         commission_per_share: float = 0.005) -> FillEstimate:
    price, quantity = float(reference_price), float(qty)
    if not math.isfinite(price) or not math.isfinite(quantity) or price <= 0 or quantity <= 0:
        raise ValueError("price and quantity must be positive finite numbers")
    direction = 1.0 if str(side).lower() == "buy" else -1.0
    slip_fraction = max(0.0, float(slippage_bps)) / 10_000.0
    fill = price * (1.0 + direction * slip_fraction)
    slippage = abs(fill - price) * quantity
    commission = max(0.0, float(commission_per_share)) * quantity
    return FillEstimate(price, fill, slippage, commission)


def option_contract_fee(qty: int, *, fee_per_contract: float = 0.65) -> float:
    quantity = int(qty)
    if quantity <= 0:
        raise ValueError("option quantity must be positive")
    return quantity * max(0.0, float(fee_per_contract))
