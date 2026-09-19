"""Risk engine telemetry models.

Provides explainable shadow-mode risk decisions.
"""

from dataclasses import dataclass


@dataclass
class RiskTelemetry:
    symbol: str
    approved_fraction: float
    blocked_reason: str | None = None


def blocked(symbol: str, reason: str) -> RiskTelemetry:
    return RiskTelemetry(symbol=symbol, approved_fraction=0.0, blocked_reason=reason)
