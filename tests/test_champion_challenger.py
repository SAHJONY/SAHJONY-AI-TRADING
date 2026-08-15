import pytest

from intelligence.champion_challenger import (
    ChampionChallengerEvaluator,
    PerformanceEvidence,
    PromotionPolicy,
)


def ev(**kw):
    base = dict(
        observations=150,
        net_sharpe=1.0,
        sortino=1.4,
        max_drawdown=0.08,
        expectancy=0.20,
        implementation_shortfall_bps=6.0,
        risk_breaches=0,
        reconciliation_rate=1.0,
        attributable_fill_rate=1.0,
    )
    base.update(kw)
    return PerformanceEvidence(**base)


def test_stronger_challenger_can_be_recommended_but_never_gets_execution_authority():
    champion = ev(net_sharpe=1.0, expectancy=0.20, max_drawdown=0.08, implementation_shortfall_bps=6.0)
    challenger = ev(net_sharpe=1.25, expectancy=0.25, max_drawdown=0.07, implementation_shortfall_bps=5.0)
    d = ChampionChallengerEvaluator().evaluate(champion, challenger)
    assert d.eligible is True
    assert d.execution_authority is False


def test_risk_breach_blocks_promotion_even_with_higher_sharpe():
    d = ChampionChallengerEvaluator().evaluate(ev(), ev(net_sharpe=3.0, risk_breaches=1))
    assert d.eligible is False
    assert "risk breaches" in " ".join(d.reasons)


def test_incomplete_reconciliation_blocks_promotion():
    d = ChampionChallengerEvaluator().evaluate(ev(), ev(net_sharpe=2.0, reconciliation_rate=0.999))
    assert d.eligible is False
    assert "reconciliation" in " ".join(d.reasons)


def test_drawdown_regression_blocks_by_default():
    d = ChampionChallengerEvaluator().evaluate(ev(max_drawdown=0.08), ev(net_sharpe=2.0, max_drawdown=0.081))
    assert d.eligible is False
    assert "drawdown" in " ".join(d.reasons)


def test_minimum_sample_gate():
    p = PromotionPolicy(min_observations=200)
    d = ChampionChallengerEvaluator(p).evaluate(ev(), ev(observations=199, net_sharpe=2.0))
    assert d.eligible is False
    assert "insufficient observations" in d.reasons


def test_nonfinite_evidence_fails_closed():
    with pytest.raises(ValueError):
        ChampionChallengerEvaluator().evaluate(ev(), ev(net_sharpe=float("nan")))
