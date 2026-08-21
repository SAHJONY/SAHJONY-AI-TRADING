"""Shadow-only TimesFM challenger adapter.

This module deliberately does not import or initialize TimesFM. A forecasting
backend is injected as a callable so tests and paper/shadow evaluation remain
fully deterministic and no model can gain execution authority by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Sequence


@dataclass(frozen=True)
class ChallengerForecast:
    symbol: str
    horizon_steps: int
    point_forecast: float
    lower: float
    upper: float
    expected_return: float
    confidence: float
    model_name: str = "timesfm-challenger"
    execution_authority: bool = False

    def __post_init__(self) -> None:
        vals = (self.point_forecast, self.lower, self.upper, self.expected_return, self.confidence)
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if int(self.horizon_steps) <= 0:
            raise ValueError("horizon_steps must be positive")
        if not all(math.isfinite(float(v)) for v in vals):
            raise ValueError("forecast outputs must be finite")
        if self.lower <= 0 or self.point_forecast <= 0 or self.upper <= 0:
            raise ValueError("forecast prices must be positive")
        if self.lower > self.point_forecast or self.point_forecast > self.upper:
            raise ValueError("forecast interval must contain point forecast")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence outside [0,1]")
        if self.execution_authority:
            raise ValueError("challenger forecast cannot have execution authority")

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "horizon_steps": self.horizon_steps,
            "point_forecast": self.point_forecast,
            "lower": self.lower,
            "upper": self.upper,
            "expected_return": self.expected_return,
            "confidence": self.confidence,
            "model_name": self.model_name,
            "execution_authority": False,
        }


def _validate_history(history: Sequence[float], min_context: int) -> list[float]:
    values = [float(x) for x in history]
    if len(values) < int(min_context):
        raise ValueError(f"insufficient context: need at least {min_context} observations")
    if not all(math.isfinite(x) and x > 0 for x in values):
        raise ValueError("history must contain finite positive prices")
    return values


def build_timesfm_challenger(
    *,
    symbol: str,
    history: Sequence[float],
    horizon_steps: int,
    predictor: Callable[[Sequence[float], int], tuple[float, float, float]],
    min_context: int = 64,
) -> ChallengerForecast:
    """Run an injected forecasting backend and normalize it into challenger telemetry."""
    values = _validate_history(history, min_context)
    if int(horizon_steps) <= 0:
        raise ValueError("horizon_steps must be positive")

    point, lower, upper = (float(x) for x in predictor(values, int(horizon_steps)))
    if not all(math.isfinite(x) for x in (point, lower, upper)):
        raise ValueError("predictor returned non-finite values")

    last = values[-1]
    expected_return = point / last - 1.0
    width = max(0.0, upper - lower)
    relative_width = width / max(point, 1e-12)
    confidence = max(0.0, min(1.0, 1.0 - relative_width))

    return ChallengerForecast(
        symbol=symbol.strip().upper(),
        horizon_steps=int(horizon_steps),
        point_forecast=point,
        lower=lower,
        upper=upper,
        expected_return=expected_return,
        confidence=confidence,
    )
