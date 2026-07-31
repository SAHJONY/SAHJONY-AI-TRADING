from datetime import datetime, timedelta, timezone

import pytest

from execution.production_adapter import (
    ActivationConfig,
    LIVE_ACK,
    ProductionExecutionAdapter,
)
from execution.robinhood_review_gate import ReviewRequest
from execution.robinhood_review_transport import (
    ReviewOnlyGates,
    ReviewOnlyOperationRejected,
    RobinhoodReviewOnlyTransport,
)


NOW = datetime(2026, 7, 24, 15, 0, tzinfo=timezone.utc)


class Backend:
    def __init__(self):
        self.calls = []

    def check_tradability(self, payload):
        self.calls.append("check_tradability")
        return {"tradable": True}

    def review_order(self, payload):
        self.calls.append("review_order")
        return {"review_id": "review-1"}

    def get_order_status(self, order_id):
        self.calls.append("get_order_status")
        return {"order_id": order_id, "status": "submitted"}

    def discover_cancel_capability(self, order_id):
        self.calls.append("discover_cancel_capability")
        return {"order_id": order_id, "supported": True}


def request():
    return ReviewRequest(symbol="VTI", side="buy", quantity=0.0025, limit_price=400)


def gates(**overrides):
    values = {
        "identity_verified": True,
        "account_last4": "1131",
        "broker_evidence_verdict": "RECONCILED",
        "quote_fresh": True,
        "historical_data_healthy": True,
        "daily_order_count": 0,
        "open_order_count": 0,
        "kill_switch_clear": True,
        "human_canary_approved": True,
        "approval_expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "approval_order_binding_exact": True,
        "audit_chain_healthy": True,
    }
    values.update(overrides)
    return ReviewOnlyGates(**values)


def test_current_reconciliation_failure_is_deterministic_and_calls_no_backend():
    backend = Backend()
    subject = RobinhoodReviewOnlyTransport(backend, clock=lambda: NOW)
    assert subject.review_order(
        request(), gates(broker_evidence_verdict="RECONCILIATION_BLOCKED"), "review-key"
    ) == {
        "eligible": False,
        "stage": "review-only",
        "reason": "broker reconciliation is not RECONCILED",
        "execution_authority": False,
        "placement_available": False,
    }
    assert backend.calls == []


@pytest.mark.parametrize(
    "operation", ["place_order", "replace_order", "modify_order", "cancel_order"]
)
def test_mutating_operations_are_explicitly_rejected(operation):
    subject = RobinhoodReviewOnlyTransport(Backend(), clock=lambda: NOW)
    with pytest.raises(ReviewOnlyOperationRejected, match="review-only"):
        getattr(subject, operation)({})


def test_only_allowlisted_review_operations_reach_backend():
    backend = Backend()
    subject = RobinhoodReviewOnlyTransport(backend, clock=lambda: NOW)
    assert subject.check_tradability(request(), gates(), "key-1")["eligible"] is True
    assert subject.review_order(request(), gates(), "key-2")["eligible"] is True
    subject.get_order_status("order-1")
    subject.discover_cancel_capability("order-1")
    assert backend.calls == [
        "check_tradability",
        "review_order",
        "get_order_status",
        "discover_cancel_capability",
    ]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"quote_fresh": False}, "quotes are not fresh"),
        ({"historical_data_healthy": False}, "historical data is not healthy"),
        ({"daily_order_count": 1}, "daily order maximum reached"),
        ({"open_order_count": 1}, "open order maximum reached"),
        ({"kill_switch_clear": False}, "kill switch is not clear"),
        ({"human_canary_approved": False}, "Human Canary approval is missing or expired"),
        ({"approval_order_binding_exact": False}, "not exactly bound"),
        ({"audit_chain_healthy": False}, "audit chain is not healthy"),
    ],
)
def test_each_runtime_gate_fails_closed(overrides, reason):
    subject = RobinhoodReviewOnlyTransport(Backend(), clock=lambda: NOW)
    assert reason in subject.review_order(request(), gates(**overrides), "valid-key")["reason"]


def test_review_only_transport_cannot_grant_production_execution_authority(tmp_path):
    transport = RobinhoodReviewOnlyTransport(Backend(), clock=lambda: NOW)
    subject = ProductionExecutionAdapter(
        tmp_path / "orders.db",
        transport=transport,
        config=ActivationConfig(enabled=True, acknowledgement=LIVE_ACK),
        approval_verifier=lambda value: True,
        clock=lambda: NOW,
    )
    assert subject.execution_authority is False
    assert subject.health()["transport_configured"] is True
