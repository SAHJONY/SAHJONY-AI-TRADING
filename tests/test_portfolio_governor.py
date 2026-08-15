from risk.portfolio_governor import (
    PortfolioRiskGovernor,
    PortfolioRiskInput,
    PortfolioRiskLimits,
)


def test_governor_only_reduces_proposed_risk():
    governor = PortfolioRiskGovernor(PortfolioRiskLimits(fractional_kelly=0.25))
    decision = governor.size(
        PortfolioRiskInput(
            equity=100_000,
            proposed_notional=10_000,
            raw_kelly_fraction=0.40,
            gross_exposure=20_000,
        )
    )
    assert decision.approved
    assert 0 < decision.final_notional <= 10_000
    assert decision.final_notional == 1_000


def test_governor_hard_drawdown_fails_closed():
    governor = PortfolioRiskGovernor()
    decision = governor.size(
        PortfolioRiskInput(
            equity=100_000,
            proposed_notional=5_000,
            raw_kelly_fraction=0.5,
            gross_exposure=10_000,
            drawdown=0.10,
        )
    )
    assert not decision.approved
    assert decision.final_notional == 0
    assert "hard drawdown" in decision.reason


def test_governor_respects_single_position_room():
    governor = PortfolioRiskGovernor(
        PortfolioRiskLimits(fractional_kelly=1.0, max_single_position_pct=0.10)
    )
    decision = governor.size(
        PortfolioRiskInput(
            equity=100_000,
            proposed_notional=10_000,
            raw_kelly_fraction=1.0,
            gross_exposure=20_000,
            existing_position_value=9_500,
        )
    )
    assert decision.approved
    assert decision.final_notional == 500


def test_governor_respects_gross_exposure_room():
    governor = PortfolioRiskGovernor(
        PortfolioRiskLimits(fractional_kelly=1.0, max_gross_exposure_pct=0.80)
    )
    decision = governor.size(
        PortfolioRiskInput(
            equity=100_000,
            proposed_notional=10_000,
            raw_kelly_fraction=1.0,
            gross_exposure=79_000,
        )
    )
    assert decision.approved
    assert decision.final_notional == 1_000


def test_governor_rejects_non_finite_input():
    governor = PortfolioRiskGovernor()
    decision = governor.size(
        PortfolioRiskInput(
            equity=float("nan"),
            proposed_notional=1_000,
            raw_kelly_fraction=0.5,
            gross_exposure=0,
        )
    )
    assert not decision.approved
    assert decision.final_notional == 0


def test_volatility_correlation_drawdown_can_only_derisk():
    governor = PortfolioRiskGovernor(
        PortfolioRiskLimits(
            fractional_kelly=1.0,
            target_vol_annual=0.15,
            max_pair_correlation=0.75,
            max_drawdown_soft=0.05,
            max_drawdown_hard=0.10,
        )
    )
    decision = governor.size(
        PortfolioRiskInput(
            equity=100_000,
            proposed_notional=10_000,
            raw_kelly_fraction=1.0,
            gross_exposure=10_000,
            realized_vol_annual=0.30,
            max_abs_correlation=0.90,
            drawdown=0.075,
        )
    )
    assert decision.approved
    assert 0 < decision.risk_scalar <= 0.5
    assert decision.final_notional <= 5_000
