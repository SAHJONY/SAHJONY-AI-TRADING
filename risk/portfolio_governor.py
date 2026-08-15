"""Portfolio-aware risk governor for Institutional Runtime V2.

This module is deliberately independent from broker execution. It can only reduce
or reject a proposed position size; it never increases risk beyond the caller's
proposal. That makes it safe to introduce as a shadow/challenger component before
wiring it into live execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PortfolioRiskLimits:
    fractional_kelly: float = 0.25
    max_single_position_pct: float = 0.10
    max_gross_exposure_pct: float = 0.80
    target_vol_annual: float = 0.15
    max_pair_correlation: float = 0.75
    max_drawdown_soft: float = 0.05
    max_drawdown_hard: float = 0.10
    min_risk_scalar: float = 0.25


@dataclass(frozen=True)
class PortfolioRiskInput:
    equity: float
    proposed_notional: float
    raw_kelly_fraction: float
    gross_exposure: float
    existing_position_value: float = 0.0
    realized_vol_annual: float = 0.0
    max_abs_correlation: float = 0.0
    drawdown: float = 0.0
    liquidity_cap_notional: float | None = None


@dataclass(frozen=True)
class PortfolioRiskDecision:
    approved: bool
    final_notional: float
    risk_scalar: float
    reason: str


class PortfolioRiskGovernor:
    """Fail-closed, reduction-only portfolio sizing layer."""

    def __init__(self, limits: PortfolioRiskLimits | None = None):
        self.limits = limits or PortfolioRiskLimits()

    @staticmethod
    def _finite(*values: float) -> bool:
        return all(math.isfinite(float(value)) for value in values)

    def _validate(self, item: PortfolioRiskInput) -> str | None:
        numeric = (
            item.equity,
            item.proposed_notional,
            item.raw_kelly_fraction,
            item.gross_exposure,
            item.existing_position_value,
            item.realized_vol_annual,
            item.max_abs_correlation,
            item.drawdown,
        )
        if not self._finite(*numeric):
            return "non-finite portfolio risk input"
        if item.liquidity_cap_notional is not None and not self._finite(item.liquidity_cap_notional):
            return "non-finite liquidity cap"
        if item.equity <= 0:
            return "non-positive equity"
        if item.proposed_notional <= 0:
            return "non-positive proposed notional"
        if item.gross_exposure < 0 or item.existing_position_value < 0:
            return "negative exposure"
        if item.realized_vol_annual < 0:
            return "negative realized volatility"
        if item.max_abs_correlation < 0 or item.max_abs_correlation > 1:
            return "correlation outside [0,1]"
        if item.drawdown < 0 or item.drawdown > 1:
            return "drawdown outside [0,1]"
        if item.liquidity_cap_notional is not None and item.liquidity_cap_notional < 0:
            return "negative liquidity cap"
        return None

    def size(self, item: PortfolioRiskInput) -> PortfolioRiskDecision:
        problem = self._validate(item)
        if problem:
            return PortfolioRiskDecision(False, 0.0, 0.0, problem)

        limits = self.limits
        if item.drawdown >= limits.max_drawdown_hard:
            return PortfolioRiskDecision(False, 0.0, 0.0, "hard drawdown stop")

        # Fractional Kelly can only reduce the caller's proposal.
        raw_kelly = max(0.0, min(1.0, item.raw_kelly_fraction))
        kelly_scalar = min(1.0, raw_kelly * max(0.0, limits.fractional_kelly))
        if kelly_scalar <= 0:
            return PortfolioRiskDecision(False, 0.0, 0.0, "kelly allocation is zero")

        # Volatility targeting de-risks when realized volatility exceeds target.
        vol_scalar = 1.0
        if limits.target_vol_annual > 0 and item.realized_vol_annual > limits.target_vol_annual:
            vol_scalar = max(
                limits.min_risk_scalar,
                min(1.0, limits.target_vol_annual / item.realized_vol_annual),
            )

        # Penalize crowded/highly correlated additions instead of pretending they
        # are independent bets. Above the limit, risk falls linearly toward the
        # minimum scalar at correlation=1.
        corr_scalar = 1.0
        if item.max_abs_correlation > limits.max_pair_correlation:
            excess = item.max_abs_correlation - limits.max_pair_correlation
            span = max(1e-9, 1.0 - limits.max_pair_correlation)
            corr_scalar = max(limits.min_risk_scalar, 1.0 - excess / span)

        # Soft drawdown throttle from the soft rail to the hard stop.
        dd_scalar = 1.0
        if item.drawdown > limits.max_drawdown_soft:
            span = max(1e-9, limits.max_drawdown_hard - limits.max_drawdown_soft)
            progress = (item.drawdown - limits.max_drawdown_soft) / span
            dd_scalar = max(limits.min_risk_scalar, 1.0 - progress)

        risk_scalar = min(1.0, kelly_scalar, vol_scalar, corr_scalar, dd_scalar)
        sized = item.proposed_notional * risk_scalar

        # Absolute portfolio rails.
        single_cap = item.equity * limits.max_single_position_pct
        single_room = max(0.0, single_cap - item.existing_position_value)
        gross_cap = item.equity * limits.max_gross_exposure_pct
        gross_room = max(0.0, gross_cap - item.gross_exposure)
        sized = min(sized, single_room, gross_room)

        if item.liquidity_cap_notional is not None:
            sized = min(sized, item.liquidity_cap_notional)

        if sized <= 0:
            return PortfolioRiskDecision(False, 0.0, risk_scalar, "no portfolio risk capacity")

        return PortfolioRiskDecision(True, sized, risk_scalar, "approved by portfolio governor")
