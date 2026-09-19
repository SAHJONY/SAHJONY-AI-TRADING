"""Advisory-only strategy supervisor contracts for Institutional Runtime V2.

The supervisor is intentionally outside the execution path. It may summarize regime
conditions, recommend investigation, reduce-risk posture, or propose a challenger,
but it cannot submit orders, widen risk, alter credentials, or self-promote a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping, Sequence

_ALLOWED_ACTIONS = {
    "observe",
    "investigate",
    "reduce_risk",
    "pause_strategy",
    "propose_challenger",
}


@dataclass(frozen=True)
class SupervisorContext:
    regime: str
    portfolio_drawdown: float
    gross_exposure_pct: float
    reconciliation_ok: bool
    data_fresh: bool
    risk_breaches: int = 0
    metrics: Mapping[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        values = (self.portfolio_drawdown, self.gross_exposure_pct)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("supervisor context must be finite")
        if not 0.0 <= self.portfolio_drawdown <= 1.0:
            raise ValueError("portfolio_drawdown outside [0,1]")
        if self.gross_exposure_pct < 0.0:
            raise ValueError("gross_exposure_pct cannot be negative")
        if int(self.risk_breaches) < 0:
            raise ValueError("risk_breaches cannot be negative")
        for key, value in self.metrics.items():
            if not str(key).strip() or not math.isfinite(float(value)):
                raise ValueError("invalid supervisor metric")


@dataclass(frozen=True)
class SupervisorRecommendation:
    action: str
    rationale: str
    confidence: float
    risk_multiplier: float = 1.0
    affected_strategies: Sequence[str] = ()
    execution_authority: bool = False
    production_promotion_authority: bool = False

    def __post_init__(self) -> None:
        action = self.action.strip().lower()
        if action not in _ALLOWED_ACTIONS:
            raise ValueError(f"unsupported supervisor action: {action}")
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        if not math.isfinite(float(self.confidence)) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence outside [0,1]")
        if not math.isfinite(float(self.risk_multiplier)) or not 0.0 <= self.risk_multiplier <= 1.0:
            raise ValueError("risk_multiplier must be reduction-only in [0,1]")
        if self.execution_authority:
            raise ValueError("strategy supervisor cannot have execution authority")
        if self.production_promotion_authority:
            raise ValueError("strategy supervisor cannot self-promote to production")

    def as_dict(self) -> dict:
        return {
            "action": self.action.strip().lower(),
            "rationale": self.rationale.strip(),
            "confidence": float(self.confidence),
            "risk_multiplier": float(self.risk_multiplier),
            "affected_strategies": list(self.affected_strategies),
            "execution_authority": False,
            "production_promotion_authority": False,
        }


def enforce_supervisor_safety(
    recommendation: SupervisorRecommendation,
    context: SupervisorContext,
) -> SupervisorRecommendation:
    """Apply deterministic safety overrides to any upstream model recommendation.

    If reconciliation or data freshness is broken, the only permissible posture is
    risk reduction. Existing execution/risk systems remain authoritative downstream.
    """
    context.validate()
    if (not context.reconciliation_ok) or (not context.data_fresh) or context.risk_breaches:
        return SupervisorRecommendation(
            action="reduce_risk",
            rationale="deterministic safety override: reconciliation/data/risk gate not clean",
            confidence=1.0,
            risk_multiplier=0.0,
            affected_strategies=recommendation.affected_strategies,
        )
    return recommendation
