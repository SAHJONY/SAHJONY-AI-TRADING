import pytest

from supervisor.strategy_supervisor import (
    SupervisorContext,
    SupervisorRecommendation,
    enforce_supervisor_safety,
)


def test_supervisor_recommendation_is_advisory_only():
    rec = SupervisorRecommendation(
        action="observe",
        rationale="no material anomaly",
        confidence=0.8,
        risk_multiplier=1.0,
    )
    assert rec.as_dict()["execution_authority"] is False
    assert rec.as_dict()["production_promotion_authority"] is False


def test_supervisor_cannot_widen_risk():
    with pytest.raises(ValueError):
        SupervisorRecommendation(
            action="observe",
            rationale="invalid risk expansion",
            confidence=0.7,
            risk_multiplier=1.1,
        )


def test_supervisor_cannot_have_execution_authority():
    with pytest.raises(ValueError):
        SupervisorRecommendation(
            action="investigate",
            rationale="bad authority",
            confidence=0.7,
            execution_authority=True,
        )


def test_bad_reconciliation_forces_zero_risk_posture():
    rec = SupervisorRecommendation(
        action="propose_challenger",
        rationale="candidate looks promising",
        confidence=0.7,
        risk_multiplier=1.0,
        affected_strategies=("momentum",),
    )
    ctx = SupervisorContext(
        regime="stress",
        portfolio_drawdown=0.03,
        gross_exposure_pct=0.5,
        reconciliation_ok=False,
        data_fresh=True,
    )
    safe = enforce_supervisor_safety(rec, ctx)
    assert safe.action == "reduce_risk"
    assert safe.risk_multiplier == 0.0
    assert safe.confidence == 1.0


def test_clean_context_preserves_recommendation():
    rec = SupervisorRecommendation(
        action="observe",
        rationale="system healthy",
        confidence=0.9,
        risk_multiplier=0.8,
    )
    ctx = SupervisorContext(
        regime="normal",
        portfolio_drawdown=0.01,
        gross_exposure_pct=0.3,
        reconciliation_ok=True,
        data_fresh=True,
    )
    assert enforce_supervisor_safety(rec, ctx) == rec
