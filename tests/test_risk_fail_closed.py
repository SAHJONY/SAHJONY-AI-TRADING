"""Regression tests for malformed numeric inputs at execution risk boundaries."""
from types import SimpleNamespace

import pytest

from config import Config
from risk.account_risk import AccountRiskEngine
from risk.risk_engine import RiskEngine


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field",
    ["equity", "deployed_value", "intended_notional", "conviction"],
)
def test_portfolio_risk_rejects_non_finite_values(field, bad):
    values = {
        "equity": 100_000.0,
        "deployed_value": 0.0,
        "intended_notional": 1_000.0,
        "conviction": 1.0,
    }
    values[field] = bad

    decision = RiskEngine(Config()).approve(symbol="SPY", **values)

    assert decision.approved is False
    assert decision.reason.startswith("invalid ")


def test_portfolio_risk_rejects_negative_exposure_and_missing_symbol():
    engine = RiskEngine(Config())

    assert not engine.approve(100_000, -1, 1_000, 1.0, "SPY").approved
    assert not engine.approve(100_000, 0, -1, 1.0, "SPY").approved
    assert not engine.approve(100_000, 0, 1_000, 1.0, " ").approved


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["equity", "proposed_notional", "daily_pnl"])
def test_account_risk_rejects_non_finite_values(field, bad):
    account = SimpleNamespace(
        id="paper",
        enabled=True,
        max_daily_loss=0.05,
        max_position=0.10,
        max_risk=0.10,
        paper=True,
    )
    values = {
        "equity": 100_000.0,
        "proposed_notional": 1_000.0,
        "daily_pnl": 0.0,
    }
    values[field] = bad

    decision = AccountRiskEngine().approve(account, **values)

    assert decision.approved is False
    assert decision.reason.startswith("invalid ")


def test_account_risk_rejects_non_positive_equity_and_negative_notional():
    account = SimpleNamespace(
        id="paper",
        enabled=True,
        max_daily_loss=0.05,
        max_position=0.10,
        max_risk=0.10,
        paper=True,
    )
    engine = AccountRiskEngine()

    assert not engine.approve(account, 0, 0).approved
    assert not engine.approve(account, 100_000, -1).approved


@pytest.mark.parametrize("field", ["max_risk", "max_position", "max_daily_loss"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.01, 0.0, 1.01])
def test_account_risk_rejects_invalid_policy_limits(field, bad):
    account = SimpleNamespace(
        id="paper",
        enabled=True,
        max_daily_loss=0.05,
        max_position=0.10,
        max_risk=0.10,
        paper=True,
    )
    setattr(account, field, bad)

    decision = AccountRiskEngine().approve(account, 100_000, 1_000)

    assert decision.approved is False
    assert decision.reason == f"invalid account {field}"
