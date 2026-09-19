"""Monte Carlo risk validation foundation.

Used for strategy validation only. No execution authority.
"""

from dataclasses import dataclass


@dataclass
class MonteCarloResult:
    ruin_probability: float
    max_drawdown_estimate: float
    approved: bool


def validate_risk(ruin_probability: float, max_drawdown: float) -> MonteCarloResult:
    """Fail closed when simulated risk exceeds limits."""
    approved = ruin_probability < 0.01 and max_drawdown < 0.15
    return MonteCarloResult(ruin_probability, max_drawdown, approved)
