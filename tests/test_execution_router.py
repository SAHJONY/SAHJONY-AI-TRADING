from dataclasses import replace

import pytest

from accounts.orchestrator import AccountProfile
from execution.router import ExecutionRouter
from strategies.base import OrderIntent


class OrchestratorStub:
    def __init__(self, account):
        self.account = account

    def enabled_accounts(self):
        return [self.account]

    def can_execute(self, account_id):
        return account_id == self.account.id


@pytest.fixture
def account():
    return AccountProfile(
        id="crypto-live",
        display_name="Crypto",
        institution="test",
        account_type="cash",
        account_number_last4="1234",
        enabled=True,
        broker="test",
        asset_class="crypto",
        strategy="crypto",
        execution_mode="api",
        live_requested=True,
        adapter_ready=True,
        symbols=["BTC/USD"],
        max_risk=0.05,
        max_position=0.05,
        max_daily_loss=0.02,
        paper=False,
    )


def valid_intent(**changes):
    values = {
        "symbol": "BTC/USD",
        "strategy": "crypto",
        "kind": "equity",
        "purpose": "entry",
        "side": "buy",
        "qty": 0.01,
        "est_notional": 1_000,
        "risk_check": True,
    }
    values.update(changes)
    return OrderIntent(**values)


def test_router_approves_valid_intent(account):
    decision = ExecutionRouter(OrchestratorStub(account)).decide(
        valid_intent(), equity=100_000, buying_power=100_000,
    )

    assert decision.approved is True
    assert decision.account_id == account.id


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"qty": float("nan")}, "invalid qty"),
        ({"qty": 0}, "quantity must be positive"),
        ({"side": "buy_to_open"}, "invalid equity side"),
        ({"est_notional": -1}, "negative est notional"),
    ],
)
def test_router_rejects_malformed_intent_before_account_selection(account, changes, reason):
    decision = ExecutionRouter(OrchestratorStub(account)).decide(
        valid_intent(**changes), equity=100_000, buying_power=100_000,
    )

    assert decision.approved is False
    assert decision.reason == reason
    assert decision.account_id is None


@pytest.mark.parametrize("field", ["max_risk", "max_position", "max_daily_loss"])
def test_router_rejects_invalid_account_risk_policy(account, field):
    malformed = replace(account, **{field: float("nan")})
    decision = ExecutionRouter(OrchestratorStub(malformed)).decide(
        valid_intent(), equity=100_000, buying_power=100_000,
    )

    assert decision.approved is False
    assert decision.reason == f"invalid account {field}"
