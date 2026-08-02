"""Review-only Robinhood venue boundary.

This module deliberately has no broker client, MCP, HTTP, or order-placement
imports.  A separately supplied backend may expose only non-mutating
tradability, review, status, and cancel-capability discovery operations.
Placement and every order mutation are structurally rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from typing import Any, Protocol

from execution.robinhood_review_gate import ReviewRequest


_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_RECONCILED = "RECONCILED"


class ReviewOnlyOperationRejected(RuntimeError):
    """An operation is outside the review-only venue boundary."""


class ReviewOnlyBackend(Protocol):
    """The complete backend surface accepted by this transport."""

    def check_tradability(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def review_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_order_status(self, order_id: str) -> dict[str, Any]: ...
    def discover_cancel_capability(self, order_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReviewOnlyGates:
    """Evidence required before a broker-side order review may be requested."""

    identity_verified: bool
    account_last4: str
    broker_evidence_verdict: str
    quote_fresh: bool
    historical_data_healthy: bool
    daily_order_count: int
    open_order_count: int
    kill_switch_clear: bool
    human_canary_approved: bool
    approval_expires_at: str
    approval_order_binding_exact: bool
    audit_chain_healthy: bool


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "eligible": False,
        "stage": "review-only",
        "reason": reason,
        "execution_authority": False,
        "placement_available": False,
    }


def _approval_unexpired(value: str, now: datetime) -> bool:
    try:
        expires_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if expires_at.tzinfo is None:
        return False
    return expires_at.astimezone(timezone.utc) > now


class RobinhoodReviewOnlyTransport:
    """Fail-closed venue transport that can never mutate an order."""

    stage = "review-only"
    execution_authority = False
    placement_available = False
    allowed_operations = frozenset({
        "check_tradability",
        "review_order",
        "get_order_status",
        "discover_cancel_capability",
    })
    rejected_operations = frozenset({
        "place_order",
        "replace_order",
        "modify_order",
        "cancel_order",
    })

    def __init__(
        self,
        backend: ReviewOnlyBackend | None = None,
        *,
        allowed_etfs: tuple[str, ...] = ("VTI",),
        max_notional: float = 1.0,
        clock: Any = None,
    ) -> None:
        self._backend = backend
        self._allowed_etfs = frozenset(symbol.strip().upper() for symbol in allowed_etfs)
        self._max_notional = max_notional
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def backend_injected(self) -> bool:
        return self._backend is not None

    def eligibility(
        self,
        request: ReviewRequest,
        gates: ReviewOnlyGates,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Evaluate every review gate without contacting the venue backend."""
        now = self._clock()
        if now.tzinfo is None:
            return _blocked("review clock is not timezone-aware")
        now = now.astimezone(timezone.utc)

        if not gates.identity_verified or gates.account_last4 != "1131":
            return _blocked("Agentic account ***1131 is not verified")
        if request.account_last4 != gates.account_last4:
            return _blocked("review order is not bound to Agentic account ***1131")
        if gates.broker_evidence_verdict != _RECONCILED:
            return _blocked("broker reconciliation is not RECONCILED")
        if not gates.quote_fresh:
            return _blocked("quotes are not fresh")
        if not gates.historical_data_healthy:
            return _blocked("historical data is not healthy")

        symbol = request.symbol.strip().upper()
        if symbol not in self._allowed_etfs:
            return _blocked("symbol is not in the ETF allowlist")
        if request.side.strip().lower() != "buy":
            return _blocked("review-only canary permits long buys only")
        if request.order_type.strip().lower() != "limit":
            return _blocked("review-only canary permits limit orders only")
        if request.time_in_force.strip().lower() != "gfd":
            return _blocked("review-only canary requires good-for-day orders")
        if not math.isfinite(request.quantity) or request.quantity <= 0:
            return _blocked("quantity must be finite and positive")
        if not math.isfinite(request.limit_price) or request.limit_price <= 0:
            return _blocked("limit price must be finite and positive")
        notional = request.notional
        if not math.isfinite(notional) or notional <= 0 or notional > self._max_notional:
            return _blocked("notional exceeds $1 review-only cap")
        if gates.daily_order_count < 0:
            return _blocked("daily order count is invalid")
        if gates.daily_order_count >= 1:
            return _blocked("daily order maximum reached")
        if gates.open_order_count < 0:
            return _blocked("open order count is invalid")
        if gates.open_order_count >= 1:
            return _blocked("open order maximum reached")
        if not gates.kill_switch_clear:
            return _blocked("kill switch is not clear")
        if (
            not gates.human_canary_approved
            or not _approval_unexpired(gates.approval_expires_at, now)
        ):
            return _blocked("Human Canary approval is missing or expired")
        if not gates.approval_order_binding_exact:
            return _blocked("Human Canary approval is not exactly bound to the order")
        if not _IDEMPOTENCY_KEY.fullmatch(str(idempotency_key)):
            return _blocked("idempotency key is invalid")
        if not gates.audit_chain_healthy:
            return _blocked("audit chain is not healthy")
        if self._backend is None:
            return _blocked("review-only venue transport is not injected")
        return {
            "eligible": True,
            "stage": self.stage,
            "reason": "",
            "execution_authority": False,
            "placement_available": False,
        }

    def check_tradability(
        self,
        request: ReviewRequest,
        gates: ReviewOnlyGates,
        idempotency_key: str,
    ) -> dict[str, Any]:
        decision = self.eligibility(request, gates, idempotency_key)
        if not decision["eligible"]:
            return decision
        assert self._backend is not None
        return {**decision, "venue": self._backend.check_tradability(self._payload(request))}

    def review_order(
        self,
        request: ReviewRequest,
        gates: ReviewOnlyGates,
        idempotency_key: str,
    ) -> dict[str, Any]:
        decision = self.eligibility(request, gates, idempotency_key)
        if not decision["eligible"]:
            return decision
        assert self._backend is not None
        return {**decision, "venue": self._backend.review_order(self._payload(request))}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        if self._backend is None:
            return _blocked("review-only venue transport is not injected")
        return {
            "eligible": False,
            "stage": self.stage,
            "reason": "status observation does not confer order eligibility",
            "execution_authority": False,
            "placement_available": False,
            "venue": self._backend.get_order_status(order_id),
        }

    def discover_cancel_capability(self, order_id: str) -> dict[str, Any]:
        if self._backend is None:
            return _blocked("review-only venue transport is not injected")
        return {
            "eligible": False,
            "stage": self.stage,
            "reason": "capability discovery does not authorize cancellation",
            "execution_authority": False,
            "placement_available": False,
            "venue": self._backend.discover_cancel_capability(order_id),
        }

    @staticmethod
    def _payload(request: ReviewRequest) -> dict[str, Any]:
        return {
            "account_last4": request.account_last4,
            "symbol": request.symbol.strip().upper(),
            "side": request.side.strip().lower(),
            "quantity": request.quantity,
            "limit_price": request.limit_price,
            "notional": request.notional,
            "order_type": request.order_type.strip().lower(),
            "time_in_force": request.time_in_force.strip().lower(),
        }

    @staticmethod
    def _reject(operation: str) -> None:
        raise ReviewOnlyOperationRejected(
            f"{operation} is unavailable at the review-only venue boundary"
        )

    def place_order(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("place_order")

    def replace_order(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("replace_order")

    def modify_order(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("modify_order")

    def cancel_order(self, *_args: Any, **_kwargs: Any) -> None:
        self._reject("cancel_order")
