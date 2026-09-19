"""Institutional position sizing primitives.

Fail-closed risk layer. This module only calculates allocations; it never places orders.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class KellyInput:
    win_probability: float
    reward_risk: float
    confidence: float = 1.0
    fractional_kelly: float = 0.25


@dataclass(frozen=True)
class RiskDecision:
    kelly_fraction: float
    approved_fraction: float
    reason: str


def kelly_fraction(p: float, b: float) -> float:
    """Classic Kelly fraction with defensive bounds."""
    if not 0 < p < 1 or b <= 0:
        return 0.0
    value = ((p * b) - (1 - p)) / b
    return max(0.0, value)


def conservative_kelly(data: KellyInput, max_risk: float = 0.005) -> RiskDecision:
    """Return a capped risk fraction using fractional Kelly.

    max_risk is a portfolio safety ceiling, not a suggestion to trade.
    """
    raw = kelly_fraction(data.win_probability, data.reward_risk)
    adjusted = raw * max(0.0, min(data.confidence, 1.0)) * data.fractional_kelly
    approved = min(adjusted, max_risk)

    if approved <= 0:
        return RiskDecision(raw, 0.0, "negative_or_insufficient_edge")

    return RiskDecision(raw, approved, "approved_with_fractional_kelly")


def apply_drawdown_guard(risk_fraction: float, drawdown: float) -> float:
    """Reduce new risk as drawdown increases. Never increases exposure."""
    if drawdown >= 0.15:
        return 0.0
    if drawdown >= 0.10:
        return risk_fraction * 0.25
    if drawdown >= 0.05:
        return risk_fraction * 0.50
    return risk_fraction
