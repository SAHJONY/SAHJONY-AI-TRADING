"""Deterministic local quant ensemble for the GPT-5.6 challenger."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

from intelligence.market_state import MarketStateSnapshot


@dataclass(frozen=True)
class QuantEnsembleResult:
    direction: int
    score: float
    confidence: float
    components: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def evaluate_quant_ensemble(
    state: MarketStateSnapshot,
    *,
    weights: Mapping[str, float] | None = None,
) -> QuantEnsembleResult:
    """Return a normalized score in [-1, 1] using transparent local features."""
    w = {
        "momentum_fast": 0.25,
        "momentum_slow": 0.25,
        "mean_reversion": 0.15,
        "order_flow": 0.20,
        "volatility_breakout": 0.15,
    }
    if weights:
        for key, value in weights.items():
            if key in w:
                w[key] = max(0.0, float(value))
    total = sum(w.values()) or 1.0
    w = {k: v / total for k, v in w.items()}

    vol_scale = max(1e-6, state.realized_vol)
    fast = _clip(state.momentum_fast / (3.0 * vol_scale), -1.0, 1.0)
    slow = _clip(state.momentum_slow / (6.0 * vol_scale), -1.0, 1.0)
    mean_rev = _clip(-state.zscore / 3.0, -1.0, 1.0)
    order_flow = _clip(state.order_flow_imbalance, -1.0, 1.0)
    breakout = _clip(abs(state.return_1) / (2.5 * vol_scale), 0.0, 1.0)
    breakout *= 1.0 if state.return_1 >= 0 else -1.0

    components = {
        "momentum_fast": fast,
        "momentum_slow": slow,
        "mean_reversion": mean_rev,
        "order_flow": order_flow,
        "volatility_breakout": breakout,
    }
    score = sum(components[k] * w[k] for k in w)
    score = _clip(score, -1.0, 1.0)
    confidence = _clip(abs(score), 0.0, 1.0)
    direction = 1 if score > 0.05 else -1 if score < -0.05 else 0
    return QuantEnsembleResult(direction=direction, score=score, confidence=confidence,
                               components=components)
