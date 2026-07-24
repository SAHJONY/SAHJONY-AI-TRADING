import pytest

from execution.control_simulator import (
    ExecutionControlSimulator,
    IdempotencyConflict,
    SimulatorPolicy,
)
from execution.robinhood_review_gate import ReviewContext, ReviewRequest


def context(**overrides):
    values = {
        "identity_verified": True,
        "expected_last4": "1131",
        "data_ready": True,
        "funding_ready": True,
        "positions_reconciled": True,
        "quote_fresh": True,
        "market_open": True,
        "execution_authority": False,
        "trading_armed": False,
    }
    values.update(overrides)
    return ReviewContext(**values)


def request(**overrides):
    values = {"symbol": "VTI", "side": "buy", "quantity": 0.0025, "limit_price": 400.0}
    values.update(overrides)
    return ReviewRequest(**values)


def reviewed(simulator, **overrides):
    review_id, decision = simulator.review(request(**overrides), context())
    assert decision.allowed
    return review_id


def test_complete_simulated_lifecycle_has_no_live_route():
    sim = ExecutionControlSimulator()
    review_id = reviewed(sim)
    order = sim.place(review_id, "canary-1")
    assert order.status == "accepted"
    assert order.environment == "simulation"
    assert order.broker_route is None
    assert sim.status(order.order_id).order_id == order.order_id
    assert sim.cancel(order.order_id).status == "cancelled"
    assert sim.summary()["execution_authority"] is False
    assert sim.summary()["live"] is False
    assert sim.verify_audit_chain()


def test_rejected_review_cannot_be_placed():
    sim = ExecutionControlSimulator()
    review_id, decision = sim.review(request(symbol="NVDA"), context())
    assert not decision.allowed
    with pytest.raises(RuntimeError, match="review"):
        sim.place(review_id, "blocked-1")


def test_simulated_broker_rejection_is_terminal_and_audited():
    sim = ExecutionControlSimulator()
    review_id = reviewed(sim)
    sim.reject_next_order("stub rejected price")
    order = sim.place(review_id, "reject-1")
    assert order.status == "rejected"
    assert order.rejection_reason == "stub rejected price"
    assert sim.cancel(order.order_id).status == "rejected"
    assert {entry["event"] for entry in sim.audit_log()} >= {"placement", "cancel_noop"}


def test_duplicate_is_suppressed_and_returns_original_order():
    sim = ExecutionControlSimulator()
    review_id = reviewed(sim)
    first = sim.place(review_id, "stable-key")
    duplicate = sim.place(review_id, "stable-key")
    assert duplicate is first
    assert len(sim.summary()["orders"]) == 1
    assert sim.audit_log()[-1]["event"] == "duplicate_suppressed"


def test_idempotency_key_conflict_fails_closed():
    sim = ExecutionControlSimulator(simulator_policy=SimulatorPolicy(max_daily_orders=2))
    first_review = reviewed(sim)
    sim.place(first_review, "reused-key")
    second_review = reviewed(sim, quantity=0.002)
    with pytest.raises(IdempotencyConflict):
        sim.place(second_review, "reused-key")
    assert sim.audit_log()[-1]["event"] == "idempotency_conflict"


def test_kill_switch_blocks_new_placement_and_records_event():
    sim = ExecutionControlSimulator()
    review_id = reviewed(sim)
    sim.set_kill_switch(True)
    with pytest.raises(RuntimeError, match="kill switch"):
        sim.place(review_id, "halted-1")
    assert sim.summary()["kill_switch_active"] is True
    assert [entry["event"] for entry in sim.audit_log()] == [
        "review", "kill_switch", "placement_blocked",
    ]


def test_daily_and_open_order_limits_fail_closed():
    open_limited = ExecutionControlSimulator(
        simulator_policy=SimulatorPolicy(max_daily_orders=2, max_open_orders=1)
    )
    open_limited.place(reviewed(open_limited), "first")
    with pytest.raises(RuntimeError, match="open order"):
        open_limited.place(reviewed(open_limited), "second")

    daily_limited = ExecutionControlSimulator()
    first = daily_limited.place(reviewed(daily_limited), "first")
    daily_limited.cancel(first.order_id)
    with pytest.raises(RuntimeError, match="daily order"):
        daily_limited.place(reviewed(daily_limited), "second")


def test_audit_chain_detects_tampering():
    sim = ExecutionControlSimulator()
    sim.place(reviewed(sim), "audit-1")
    assert sim.verify_audit_chain()
    sim._audit[0]["detail"]["allowed"] = False
    assert not sim.verify_audit_chain()
