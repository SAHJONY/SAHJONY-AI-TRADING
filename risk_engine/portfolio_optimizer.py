"""Portfolio-level risk controls for institutional Kelly sizing.

Shadow-mode only. Does not place orders.
"""

from dataclasses import dataclass


@dataclass
class ExposureDecision:
    approved_fraction: float
    reason: str


def cap_correlated_exposure(kelly_fraction: float, correlation_score: float, max_fraction: float = 0.05) -> ExposureDecision:
    """Reduce sizing when correlated exposure increases.

    correlation_score: 0-1 where 1 represents extreme concentration.
    """
    if correlation_score < 0 or correlation_score > 1:
        return ExposureDecision(0.0, "invalid_correlation")

    adjusted = kelly_fraction * (1 - (0.5 * correlation_score))
    approved = min(max(adjusted, 0.0), max_fraction)

    return ExposureDecision(approved, "portfolio_limit_applied")
