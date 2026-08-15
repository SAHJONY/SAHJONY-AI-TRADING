"""Deterministic champion/challenger promotion evidence.

The evaluator is deliberately advisory. It never changes strategy weights, risk
limits, feature flags, or execution permissions. It only turns measured evidence
into a promotion recommendation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Dict


@dataclass(frozen=True)
class PerformanceEvidence:
    observations: int
    net_sharpe: float
    sortino: float
    max_drawdown: float
    expectancy: float
    implementation_shortfall_bps: float
    risk_breaches: int = 0
    reconciliation_rate: float = 1.0
    attributable_fill_rate: float = 1.0

    def validate(self) -> None:
        if self.observations < 0 or self.risk_breaches < 0:
            raise ValueError("counts cannot be negative")
        vals = (
            self.net_sharpe,
            self.sortino,
            self.max_drawdown,
            self.expectancy,
            self.implementation_shortfall_bps,
            self.reconciliation_rate,
            self.attributable_fill_rate,
        )
        if not all(math.isfinite(float(v)) for v in vals):
            raise ValueError("performance evidence must be finite")
        if not 0 <= self.max_drawdown <= 1:
            raise ValueError("max_drawdown must be in [0,1]")
        if self.implementation_shortfall_bps < 0:
            raise ValueError("implementation_shortfall_bps cannot be negative")
        if not 0 <= self.reconciliation_rate <= 1:
            raise ValueError("reconciliation_rate must be in [0,1]")
        if not 0 <= self.attributable_fill_rate <= 1:
            raise ValueError("attributable_fill_rate must be in [0,1]")


@dataclass(frozen=True)
class PromotionPolicy:
    min_observations: int = 100
    min_sharpe_improvement: float = 0.10
    min_expectancy_improvement: float = 0.0
    max_drawdown_regression: float = 0.0
    max_shortfall_regression_bps: float = 0.0
    min_reconciliation_rate: float = 1.0
    min_attributable_fill_rate: float = 1.0


@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    reasons: tuple[str, ...]
    champion: Dict[str, float | int]
    challenger: Dict[str, float | int]
    execution_authority: bool = False


class ChampionChallengerEvaluator:
    def __init__(self, policy: PromotionPolicy | None = None):
        self.policy = policy or PromotionPolicy()

    def evaluate(self, champion: PerformanceEvidence, challenger: PerformanceEvidence) -> PromotionDecision:
        champion.validate()
        challenger.validate()
        p = self.policy
        reasons: list[str] = []

        if challenger.observations < p.min_observations:
            reasons.append("insufficient observations")
        if challenger.risk_breaches != 0:
            reasons.append("challenger has risk breaches")
        if challenger.reconciliation_rate < p.min_reconciliation_rate:
            reasons.append("reconciliation gate not met")
        if challenger.attributable_fill_rate < p.min_attributable_fill_rate:
            reasons.append("fill attribution gate not met")
        if challenger.net_sharpe < champion.net_sharpe + p.min_sharpe_improvement:
            reasons.append("net Sharpe improvement gate not met")
        if challenger.expectancy < champion.expectancy + p.min_expectancy_improvement:
            reasons.append("expectancy gate not met")
        if challenger.max_drawdown > champion.max_drawdown + p.max_drawdown_regression:
            reasons.append("drawdown regression")
        if challenger.implementation_shortfall_bps > (
            champion.implementation_shortfall_bps + p.max_shortfall_regression_bps
        ):
            reasons.append("execution shortfall regression")

        return PromotionDecision(
            eligible=not reasons,
            reasons=tuple(reasons) if reasons else ("objective promotion gates met",),
            champion=asdict(champion),
            challenger=asdict(challenger),
            execution_authority=False,
        )
