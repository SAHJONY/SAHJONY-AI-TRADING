"""Shadow-only decision telemetry for Institutional Runtime V2.

This module records what the current champion decided and what challengers would
have decided from the same market snapshot. It performs no broker calls and has
no execution authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict


def _finite(name: str, value: float) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


@dataclass(frozen=True)
class ShadowDecisionEvent:
    symbol: str
    strategy: str
    champion_signal: float
    champion_confidence: float
    challenger_signal: float
    challenger_confidence: float
    reference_price: float
    regime: str = "unknown"
    features: Dict[str, float] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not self.strategy.strip():
            raise ValueError("strategy is required")
        for name in ("champion_signal", "challenger_signal"):
            value = _finite(name, getattr(self, name))
            if value < -1.0 or value > 1.0:
                raise ValueError(f"{name} must be in [-1,1]")
        for name in ("champion_confidence", "challenger_confidence"):
            value = _finite(name, getattr(self, name))
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be in [0,1]")
        if _finite("reference_price", self.reference_price) <= 0:
            raise ValueError("reference_price must be positive")
        for key, value in self.features.items():
            _finite(f"feature:{key}", value)

    @property
    def signal_delta(self) -> float:
        return self.challenger_signal - self.champion_signal

    @property
    def confidence_delta(self) -> float:
        return self.challenger_confidence - self.champion_confidence

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["signal_delta"] = self.signal_delta
        payload["confidence_delta"] = self.confidence_delta
        payload["execution_authority"] = False
        return payload
