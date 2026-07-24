"""Deterministic, non-live execution-control simulator.

This module validates the order-control lifecycle without importing a broker
adapter or exposing a network route. Every order is synthetic and permanently
marked ``simulation``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from execution.robinhood_review_gate import (
    ReviewContext,
    ReviewDecision,
    ReviewPolicy,
    ReviewRequest,
    evaluate_review_request,
)


TERMINAL_STATUSES = {"cancelled", "filled", "rejected"}


class IdempotencyConflict(RuntimeError):
    """An idempotency key was reused for a materially different request."""


@dataclass(frozen=True)
class SimulatorPolicy:
    max_daily_orders: int = 1
    max_open_orders: int = 1


@dataclass
class SimulatedOrder:
    order_id: str
    review_id: str
    idempotency_key: str
    request: dict[str, Any]
    status: str
    created_at: str
    updated_at: str
    rejection_reason: str | None = None
    environment: str = "simulation"
    broker_route: str | None = None


class ExecutionControlSimulator:
    """In-memory Canary lifecycle simulator with a hash-chained audit ledger."""

    live = False
    execution_authority = False
    broker_route = None

    def __init__(
        self,
        *,
        review_policy: ReviewPolicy | None = None,
        simulator_policy: SimulatorPolicy | None = None,
    ) -> None:
        self.review_policy = review_policy or ReviewPolicy()
        self.simulator_policy = simulator_policy or SimulatorPolicy()
        self.kill_switch_active = False
        self._reviews: dict[str, ReviewDecision] = {}
        self._orders: dict[str, SimulatedOrder] = {}
        self._idempotency: dict[str, tuple[str, str]] = {}
        self._audit: list[dict[str, Any]] = []
        self._reject_next: str | None = None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _record(self, event: str, detail: dict[str, Any]) -> None:
        previous = self._audit[-1]["hash"] if self._audit else "0" * 64
        entry = {
            "sequence": len(self._audit) + 1,
            "timestamp": self._now(),
            "event": event,
            "detail": detail,
            "previous_hash": previous,
        }
        entry["hash"] = self._digest(entry)
        self._audit.append(entry)

    def review(self, request: ReviewRequest, context: ReviewContext) -> tuple[str, ReviewDecision]:
        decision = evaluate_review_request(request, context, self.review_policy)
        review_id = f"sim-review-{uuid4().hex}"
        self._reviews[review_id] = decision
        self._record("review", {
            "review_id": review_id,
            "allowed": decision.allowed,
            "blockers": list(decision.blockers),
            "request_digest": self._digest(decision.request),
        })
        return review_id, decision

    def reject_next_order(self, reason: str = "simulated broker rejection") -> None:
        self._reject_next = str(reason)[:200]

    def set_kill_switch(self, active: bool) -> None:
        self.kill_switch_active = bool(active)
        self._record("kill_switch", {"active": self.kill_switch_active})

    def _open_orders(self) -> int:
        return sum(order.status not in TERMINAL_STATUSES for order in self._orders.values())

    def place(self, review_id: str, idempotency_key: str) -> SimulatedOrder:
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("a bounded idempotency key is required")
        decision = self._reviews.get(review_id)
        if decision is None:
            raise ValueError("unknown review")
        request_digest = self._digest(decision.request)
        prior = self._idempotency.get(idempotency_key)
        if prior:
            prior_digest, order_id = prior
            if prior_digest != request_digest:
                self._record("idempotency_conflict", {"key_digest": self._digest(idempotency_key)})
                raise IdempotencyConflict("idempotency key conflicts with prior request")
            self._record("duplicate_suppressed", {"order_id": order_id})
            return self._orders[order_id]
        if not decision.allowed:
            self._record("placement_blocked", {"review_id": review_id, "reason": "review rejected"})
            raise RuntimeError("review is not eligible for simulated placement")
        if self.kill_switch_active:
            self._record("placement_blocked", {"review_id": review_id, "reason": "kill switch active"})
            raise RuntimeError("kill switch active")
        if len(self._orders) >= self.simulator_policy.max_daily_orders:
            self._record("placement_blocked", {"review_id": review_id, "reason": "daily order limit"})
            raise RuntimeError("daily order limit reached")
        if self._open_orders() >= self.simulator_policy.max_open_orders:
            self._record("placement_blocked", {"review_id": review_id, "reason": "open order limit"})
            raise RuntimeError("open order limit reached")

        now = self._now()
        rejection = self._reject_next
        self._reject_next = None
        order = SimulatedOrder(
            order_id=f"sim-order-{uuid4().hex}",
            review_id=review_id,
            idempotency_key=idempotency_key,
            request=dict(decision.request),
            status="rejected" if rejection else "accepted",
            created_at=now,
            updated_at=now,
            rejection_reason=rejection,
        )
        self._orders[order.order_id] = order
        self._idempotency[idempotency_key] = (request_digest, order.order_id)
        self._record("placement", {
            "order_id": order.order_id,
            "status": order.status,
            "environment": order.environment,
            "broker_route": order.broker_route,
        })
        return order

    def status(self, order_id: str) -> SimulatedOrder:
        try:
            order = self._orders[order_id]
        except KeyError as exc:
            raise ValueError("unknown simulated order") from exc
        self._record("status", {"order_id": order_id, "status": order.status})
        return order

    def cancel(self, order_id: str) -> SimulatedOrder:
        order = self.status(order_id)
        if order.status in TERMINAL_STATUSES:
            self._record("cancel_noop", {"order_id": order_id, "status": order.status})
            return order
        order.status = "cancelled"
        order.updated_at = self._now()
        self._record("cancel", {"order_id": order_id, "status": order.status})
        return order

    def audit_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(json.dumps(entry)) for entry in self._audit)

    def verify_audit_chain(self) -> bool:
        previous = "0" * 64
        for expected_sequence, stored in enumerate(self._audit, start=1):
            entry = dict(stored)
            digest = entry.pop("hash", "")
            if entry["sequence"] != expected_sequence or entry["previous_hash"] != previous:
                return False
            if self._digest(entry) != digest:
                return False
            previous = digest
        return True

    def summary(self) -> dict[str, Any]:
        return {
            "environment": "simulation",
            "live": False,
            "execution_authority": False,
            "broker_route": None,
            "kill_switch_active": self.kill_switch_active,
            "orders": [asdict(order) for order in self._orders.values()],
            "audit_valid": self.verify_audit_chain(),
        }
