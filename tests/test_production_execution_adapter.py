from datetime import datetime, timedelta, timezone

import pytest

from execution.production_adapter import (
    ActivationConfig,
    ExecutionBlocked,
    ExecutionUncertain,
    GateSnapshot,
    HumanCanaryApproval,
    LIVE_ACK,
    ProductionExecutionAdapter,
)
from execution.robinhood_review_gate import ReviewRequest


NOW = datetime(2026, 7, 23, 15, 0, tzinfo=timezone.utc)


class VenueStub:
    def __init__(self):
        self.orders = {}
        self.place_calls = 0
        self.review_approved = True
        self.bad_ack = False
        self.cancel_ok = True

    def review_order(self, payload):
        return {"approved": self.review_approved, "review_id": "review-1"}

    def place_order(self, payload):
        self.place_calls += 1
        if self.bad_ack:
            return {"status": "submitted"}
        order = {"order_id": "broker-1", "status": "submitted", "payload": payload}
        self.orders["broker-1"] = order
        return order

    def get_order(self, broker_order_id):
        return self.orders[broker_order_id]

    def cancel_order(self, broker_order_id):
        if not self.cancel_ok:
            return {"order_id": broker_order_id, "status": "unknown"}
        self.orders[broker_order_id]["status"] = "cancelled"
        return {"order_id": broker_order_id, "status": "cancelled"}


def config(**overrides):
    values = {
        "enabled": True,
        "acknowledgement": LIVE_ACK,
        "account_last4": "1131",
    }
    values.update(overrides)
    return ActivationConfig(**values)


def gates(**overrides):
    values = {field: True for field in GateSnapshot.__dataclass_fields__}
    values.update(overrides)
    return GateSnapshot(**values)


def request(**overrides):
    values = {"symbol": "VTI", "side": "buy", "quantity": 0.0025, "limit_price": 400.0}
    values.update(overrides)
    return ReviewRequest(**values)


def approval(**overrides):
    values = {
        "approval_id": "human-approval-1",
        "account_last4": "1131",
        "symbol": "VTI",
        "side": "buy",
        "quantity": 0.0025,
        "limit_price": 400.0,
        "max_notional": 1.0,
        "approved_at": (NOW - timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    values.update(overrides)
    return HumanCanaryApproval(**values)


def adapter(tmp_path, venue=None, reconciler=None, **config_overrides):
    return ProductionExecutionAdapter(
        tmp_path / "orders.db",
        transport=venue,
        config=config(**config_overrides),
        reconciler=reconciler or (lambda stage, payload: True),
        approval_verifier=lambda value: True,
        clock=lambda: NOW,
    )


def test_default_adapter_has_no_transport_or_authority(tmp_path):
    subject = ProductionExecutionAdapter(tmp_path / "disabled.db")
    assert subject.execution_authority is False
    assert subject.health()["transport_configured"] is False
    assert subject.health()["approval_verifier_configured"] is False
    with pytest.raises(ExecutionBlocked, match="disabled"):
        subject.submit(request(), gates(), approval(), "key-1")


@pytest.mark.parametrize("field", list(GateSnapshot.__dataclass_fields__))
def test_every_activation_gate_independently_blocks(tmp_path, field):
    subject = adapter(tmp_path, VenueStub())
    with pytest.raises(ExecutionBlocked, match=field):
        subject.submit(request(), gates(**{field: False}), approval(), "key-" + field)


def test_exact_human_approval_binding_and_expiry(tmp_path):
    subject = adapter(tmp_path, VenueStub())
    with pytest.raises(ExecutionBlocked, match="exactly"):
        subject.submit(request(), gates(), approval(symbol="SPY"), "wrong-symbol")
    with pytest.raises(ExecutionBlocked, match="expired"):
        subject.submit(
            request(), gates(),
            approval(expires_at=(NOW - timedelta(seconds=1)).isoformat()),
            "expired",
        )


def test_unverified_human_approval_blocks_submission(tmp_path):
    subject = ProductionExecutionAdapter(
        tmp_path / "unverified.db",
        transport=VenueStub(),
        config=config(),
        reconciler=lambda stage, payload: True,
        approval_verifier=lambda value: False,
        clock=lambda: NOW,
    )
    assert subject.execution_authority is True
    with pytest.raises(ExecutionBlocked, match="independently verified"):
        subject.submit(request(), gates(), approval(), "unverified")


def test_submit_persists_lifecycle_and_suppresses_duplicate(tmp_path):
    venue = VenueStub()
    stages = []
    subject = adapter(tmp_path, venue, lambda stage, payload: stages.append(stage) or True)
    first = subject.submit(request(), gates(), approval(), "stable-key")
    duplicate = subject.submit(request(), gates(), approval(), "stable-key")
    assert first["local_order_id"] == duplicate["local_order_id"]
    assert first["status"] == "submitted"
    assert venue.place_calls == 1
    assert stages == ["pre_order", "post_order"]
    assert subject.health()["audit_valid"] is True


def test_idempotency_conflict_halts_adapter(tmp_path):
    subject = adapter(tmp_path, VenueStub(), max_daily_orders=2)
    subject.submit(request(), gates(), approval(), "same-key")
    with pytest.raises(ExecutionBlocked, match="idempotency"):
        subject.submit(
            request(quantity=0.002),
            gates(),
            approval(quantity=0.002),
            "same-key",
        )
    assert subject.halted
    assert subject.execution_authority is False


def test_pre_reconciliation_blocks_before_transport(tmp_path):
    venue = VenueStub()
    subject = adapter(tmp_path, venue, lambda stage, payload: False)
    with pytest.raises(ExecutionBlocked, match="pre_order"):
        subject.submit(request(), gates(), approval(), "pre-fail")
    assert venue.place_calls == 0


def test_post_reconciliation_failure_halts_and_persists_failure(tmp_path):
    venue = VenueStub()
    subject = adapter(tmp_path, venue, lambda stage, payload: stage == "pre_order")
    with pytest.raises(ExecutionBlocked, match="post_order"):
        subject.submit(request(), gates(), approval(), "post-fail")
    assert subject.halted
    assert subject.execution_authority is False
    assert venue.orders["broker-1"]["status"] == "cancelled"
    row = subject.conn.execute("SELECT * FROM production_orders").fetchone()
    assert row["status"] == "cancelled"
    assert {entry["kind"] for entry in subject.conn.execute("SELECT kind FROM audit_ledger")} >= {
        "production_automatic_rollback", "production_execution_halt",
    }


def test_post_reconciliation_cancel_uncertainty_remains_visible(tmp_path):
    venue = VenueStub()
    venue.cancel_ok = False
    subject = adapter(tmp_path, venue, lambda stage, payload: stage == "pre_order")
    with pytest.raises(ExecutionBlocked, match="post_order"):
        subject.submit(request(), gates(), approval(), "post-cancel-uncertain")
    row = subject.conn.execute("SELECT * FROM production_orders").fetchone()
    assert row["status"] == "pending_cancel"
    assert subject.halted


def test_incomplete_broker_acknowledgement_halts(tmp_path):
    venue = VenueStub()
    venue.bad_ack = True
    subject = adapter(tmp_path, venue)
    with pytest.raises(ExecutionUncertain):
        subject.submit(request(), gates(), approval(), "bad-ack")
    assert subject.halted


def test_status_cancel_and_restart_recovery(tmp_path):
    venue = VenueStub()
    subject = adapter(tmp_path, venue)
    created = subject.submit(request(), gates(), approval(), "recoverable")
    restarted = adapter(tmp_path, venue)
    recovered = restarted.recover()
    assert recovered[0]["local_order_id"] == created["local_order_id"]
    assert restarted.cancel(created["local_order_id"])["status"] == "cancelled"


def test_cancel_failure_halts(tmp_path):
    venue = VenueStub()
    subject = adapter(tmp_path, venue)
    created = subject.submit(request(), gates(), approval(), "cancel-fail")
    venue.cancel_ok = False
    with pytest.raises(ExecutionUncertain):
        subject.cancel(created["local_order_id"])
    assert subject.halted


def test_expired_open_order_is_cancelled(tmp_path):
    venue = VenueStub()
    current = [NOW]
    subject = ProductionExecutionAdapter(
        tmp_path / "expiry.db",
        transport=venue,
        config=config(),
        reconciler=lambda stage, payload: True,
        approval_verifier=lambda value: True,
        clock=lambda: current[0],
    )
    created = subject.submit(request(), gates(), approval(), "expires")
    current[0] = NOW + timedelta(minutes=6)
    assert subject.cancel_expired() == [created["local_order_id"]]
    assert subject.order(created["local_order_id"])["status"] == "cancelled"


def test_daily_and_open_order_caps_are_enforced(tmp_path):
    first_venue = VenueStub()
    open_limited = adapter(tmp_path / "open", first_venue, max_daily_orders=2)
    open_limited.submit(request(), gates(), approval(), "first")
    with pytest.raises(ExecutionBlocked, match="open order"):
        open_limited.submit(request(), gates(), approval(approval_id="two"), "second")

    daily_venue = VenueStub()
    daily_limited = adapter(tmp_path / "daily", daily_venue)
    created = daily_limited.submit(request(), gates(), approval(), "first")
    daily_limited.cancel(created["local_order_id"])
    with pytest.raises(ExecutionBlocked, match="daily order"):
        daily_limited.submit(request(), gates(), approval(approval_id="two"), "second")


def test_uncertain_submitting_state_halts_recovery(tmp_path):
    venue = VenueStub()
    subject = adapter(tmp_path, venue)
    subject.conn.execute(
        """INSERT INTO production_orders
           (local_order_id,idempotency_key,request_digest,request,approval,status,
            created_at,updated_at,expires_at)
           VALUES ('local','key','digest','{}','{}','submitting',?,?,?)""",
        (NOW.isoformat(), NOW.isoformat(), (NOW + timedelta(minutes=5)).isoformat()),
    )
    subject.conn.commit()
    with pytest.raises(ExecutionUncertain, match="manual"):
        subject.recover()
    assert subject.halted
