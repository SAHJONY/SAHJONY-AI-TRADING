"""Fail-closed production execution controller.

The controller owns policy, approval binding, persistence, reconciliation, and
recovery. It deliberately contains no Robinhood/Alpaca SDK, HTTP client, or
public endpoint. A venue transport must be explicitly injected after a separate
activation review; default construction cannot place an order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Callable, Protocol

from database import Database
from execution.robinhood_review_gate import ReviewPolicy, ReviewRequest


ACTIVE_STATUSES = {"submitted", "acknowledged", "partially_filled", "pending_cancel"}
TERMINAL_STATUSES = {"filled", "cancelled", "rejected", "failed"}
KNOWN_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES
LIVE_ACK = "I_ACKNOWLEDGE_AGENTIC_1131_CANARY"


class ExecutionBlocked(RuntimeError):
    """A safety gate denied execution."""


class ExecutionUncertain(RuntimeError):
    """Broker state could not be established; the controller halted."""


class VenueTransport(Protocol):
    """Minimal injected order transport; implementations live outside this module."""

    def review_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_order(self, broker_order_id: str) -> dict[str, Any]: ...
    def cancel_order(self, broker_order_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ActivationConfig:
    enabled: bool = False
    acknowledgement: str = ""
    account_last4: str = "1131"
    max_notional: float = 1.0
    max_daily_orders: int = 1
    max_open_orders: int = 1
    allowed_symbols: tuple[str, ...] = ("VTI",)


@dataclass(frozen=True)
class GateSnapshot:
    identity: bool
    funding: bool
    quotes: bool
    historical_data: bool
    crypto_enumeration: bool
    reconciliation: bool
    risk_controls: bool
    kill_switch_tested: bool
    kill_switch_clear: bool
    execution_authority: bool
    trading_armed: bool

    def blockers(self) -> tuple[str, ...]:
        return tuple(name for name, passed in asdict(self).items() if not passed)


@dataclass(frozen=True)
class HumanCanaryApproval:
    approval_id: str
    account_last4: str
    symbol: str
    side: str
    quantity: float
    limit_price: float
    max_notional: float
    approved_at: str
    expires_at: str


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class ProductionExecutionAdapter:
    """Persistent Canary controller that fails closed on every uncertainty."""

    def __init__(
        self,
        state_path: str | Path,
        *,
        transport: VenueTransport | None = None,
        config: ActivationConfig | None = None,
        reconciler: Callable[[str, dict[str, Any]], bool] | None = None,
        approval_verifier: Callable[[HumanCanaryApproval], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or ActivationConfig()
        self.transport = transport
        self.reconciler = reconciler
        self.approval_verifier = approval_verifier
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.halted = False
        self.halt_reason = ""
        self.db = Database(str(state_path))
        self.conn = self.db.conn
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS production_orders (
               local_order_id TEXT PRIMARY KEY,
               idempotency_key TEXT NOT NULL UNIQUE,
               request_digest TEXT NOT NULL,
               request TEXT NOT NULL,
               approval TEXT NOT NULL,
               broker_order_id TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL,
               created_at TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               expires_at TEXT NOT NULL,
               detail TEXT NOT NULL DEFAULT '{}')"""
        )
        self.conn.commit()

    @property
    def execution_authority(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.acknowledgement == LIVE_ACK
            and self.transport is not None
            and self.approval_verifier is not None
            and not self.halted
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _audit(self, kind: str, payload: dict[str, Any]) -> None:
        safe = dict(payload)
        safe["execution_authority"] = self.execution_authority
        self.db.append_audit(kind, safe)

    def _halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = str(reason)[:300]
        self._audit("production_execution_halt", {"reason": self.halt_reason})

    def reset_halt(self) -> None:
        """Deliberately does not self-reset; restart with reviewed configuration."""
        raise ExecutionBlocked("halt reset requires an external human-reviewed restart")

    def _validate_request(self, request: ReviewRequest) -> dict[str, Any]:
        symbol = request.symbol.strip().upper()
        side = request.side.strip().lower()
        if request.account_last4 != self.config.account_last4:
            raise ExecutionBlocked("wrong account")
        if symbol not in {item.upper() for item in self.config.allowed_symbols}:
            raise ExecutionBlocked("symbol is not allowlisted")
        if side != "buy" or request.order_type.lower() != "limit":
            raise ExecutionBlocked("Canary requires a long-only limit order")
        if request.time_in_force.lower() != "gfd":
            raise ExecutionBlocked("Canary requires good-for-day")
        values = (request.quantity, request.limit_price, request.notional)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ExecutionBlocked("quantity, price, and notional must be finite and positive")
        if request.notional > self.config.max_notional:
            raise ExecutionBlocked("Canary notional exceeds configured cap")
        return {
            "account_last4": request.account_last4,
            "symbol": symbol,
            "side": side,
            "quantity": request.quantity,
            "limit_price": request.limit_price,
            "notional": request.notional,
            "order_type": "limit",
            "time_in_force": "gfd",
        }

    def _validate_approval(
        self, request: dict[str, Any], approval: HumanCanaryApproval
    ) -> dict[str, Any]:
        now = self._now()
        approved_at, expires_at = _utc(approval.approved_at), _utc(approval.expires_at)
        if not approval.approval_id.strip() or approved_at > now or expires_at <= now:
            raise ExecutionBlocked("Human Canary approval is missing, future-dated, or expired")
        if self.approval_verifier is None or self.approval_verifier(approval) is not True:
            raise ExecutionBlocked("Human Canary approval is not independently verified")
        exact = (
            approval.account_last4 == request["account_last4"]
            and approval.symbol.strip().upper() == request["symbol"]
            and approval.side.strip().lower() == request["side"]
            and approval.quantity == request["quantity"]
            and approval.limit_price == request["limit_price"]
            and approval.max_notional == self.config.max_notional
            and request["notional"] <= approval.max_notional
        )
        if not exact:
            raise ExecutionBlocked("order does not exactly match Human Canary approval")
        return asdict(approval)

    def _require_ready(self, gates: GateSnapshot) -> None:
        if not self.execution_authority:
            raise ExecutionBlocked("production execution adapter is disabled")
        blockers = gates.blockers()
        if blockers:
            raise ExecutionBlocked("activation gates blocked: " + ", ".join(blockers))

    def _reconcile(self, stage: str, payload: dict[str, Any]) -> None:
        if self.reconciler is None or self.reconciler(stage, payload) is not True:
            raise ExecutionBlocked(f"{stage} reconciliation failed")

    def _counts(self, day: str) -> tuple[int, int]:
        daily = self.conn.execute(
            "SELECT COUNT(*) AS n FROM production_orders WHERE substr(created_at,1,10)=?",
            (day,),
        ).fetchone()["n"]
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        opened = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM production_orders WHERE status IN ({placeholders})",
            tuple(ACTIVE_STATUSES),
        ).fetchone()["n"]
        return int(daily), int(opened)

    def submit(
        self,
        request: ReviewRequest,
        gates: GateSnapshot,
        approval: HumanCanaryApproval,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_ready(gates)
        normalized = self._validate_request(request)
        approval_payload = self._validate_approval(normalized, approval)
        if not idempotency_key or len(idempotency_key) > 200:
            raise ExecutionBlocked("bounded idempotency key required")
        request_digest = _digest(normalized)
        existing = self.conn.execute(
            "SELECT * FROM production_orders WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if existing:
            if existing["request_digest"] != request_digest:
                self._halt("idempotency conflict")
                raise ExecutionBlocked("idempotency conflict")
            self._audit("production_duplicate_suppressed", {
                "local_order_id": existing["local_order_id"],
            })
            return dict(existing)

        now = self._now()
        daily, opened = self._counts(now.date().isoformat())
        if daily >= self.config.max_daily_orders:
            raise ExecutionBlocked("daily order limit reached")
        if opened >= self.config.max_open_orders:
            raise ExecutionBlocked("open order limit reached")
        self._reconcile("pre_order", normalized)

        assert self.transport is not None  # established by execution_authority
        review = self.transport.review_order(normalized)
        if review.get("approved") is not True:
            self._audit("production_review_rejected", {
                "request_digest": request_digest,
                "reason": str(review.get("reason", "broker review rejected"))[:200],
            })
            raise ExecutionBlocked("broker review rejected")

        local_order_id = f"canary-{_digest([idempotency_key, request_digest])[:24]}"
        created = now.isoformat().replace("+00:00", "Z")
        self.conn.execute(
            """INSERT INTO production_orders
               (local_order_id,idempotency_key,request_digest,request,approval,status,
                created_at,updated_at,expires_at)
               VALUES (?,?,?,?,?,'submitting',?,?,?)""",
            (
                local_order_id, idempotency_key, request_digest, _canonical(normalized),
                _canonical(approval_payload), created, created, approval.expires_at,
            ),
        )
        self.conn.commit()
        self._audit("production_submit_started", {
            "local_order_id": local_order_id,
            "request_digest": request_digest,
            "approval_id": approval.approval_id,
        })
        broker_id = ""
        try:
            response = self.transport.place_order({
                **normalized,
                "client_order_id": local_order_id,
                "review_id": review.get("review_id"),
            })
            broker_id = str(response.get("order_id", "")).strip()
            status = str(response.get("status", "")).strip().lower()
            if not broker_id or status not in KNOWN_STATUSES:
                raise ExecutionUncertain("broker acknowledgement is incomplete")
            self.conn.execute(
                """UPDATE production_orders SET broker_order_id=?,status=?,updated_at=?,detail=?
                   WHERE local_order_id=?""",
                (broker_id, status, self._now().isoformat(), _canonical(response), local_order_id),
            )
            self.conn.commit()
            self._audit("production_order_acknowledged", {
                "local_order_id": local_order_id, "broker_order_id": broker_id, "status": status,
            })
            self._reconcile("post_order", {
                **normalized, "local_order_id": local_order_id,
                "broker_order_id": broker_id, "status": status,
            })
            return self.order(local_order_id)
        except Exception as exc:
            fallback_status = "failed"
            rollback: dict[str, Any] = {"attempted": False}
            if broker_id:
                fallback_status = "pending_cancel"
                rollback["attempted"] = True
                try:
                    cancel_response = self.transport.cancel_order(broker_id)
                    cancel_status = str(cancel_response.get("status", "")).lower()
                    if cancel_status in {"cancelled", "pending_cancel"}:
                        fallback_status = cancel_status
                    rollback["status"] = cancel_status or "unknown"
                except Exception as cancel_exc:
                    rollback["error"] = type(cancel_exc).__name__
            self.conn.execute(
                "UPDATE production_orders SET status=?,updated_at=?,detail=? WHERE local_order_id=?",
                (
                    fallback_status, self._now().isoformat(),
                    _canonical({"error": type(exc).__name__, "rollback": rollback}),
                    local_order_id,
                ),
            )
            self.conn.commit()
            self._audit("production_automatic_rollback", {
                "local_order_id": local_order_id,
                "broker_order_id": broker_id,
                "status": fallback_status,
                "rollback": rollback,
            })
            self._halt(f"submission failure: {type(exc).__name__}")
            raise

    def order(self, local_order_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM production_orders WHERE local_order_id=?", (local_order_id,)
        ).fetchone()
        if row is None:
            raise KeyError("unknown local order")
        return dict(row)

    def refresh(self, local_order_id: str) -> dict[str, Any]:
        row = self.order(local_order_id)
        if row["status"] in TERMINAL_STATUSES:
            return row
        if self.transport is None or not row["broker_order_id"]:
            self._halt("status uncertainty")
            raise ExecutionUncertain("cannot query broker order status")
        try:
            response = self.transport.get_order(row["broker_order_id"])
            status = str(response.get("status", "")).lower()
            if status not in KNOWN_STATUSES:
                raise ExecutionUncertain("broker returned unknown order status")
            self.conn.execute(
                "UPDATE production_orders SET status=?,updated_at=?,detail=? WHERE local_order_id=?",
                (status, self._now().isoformat(), _canonical(response), local_order_id),
            )
            self.conn.commit()
            self._audit("production_status", {
                "local_order_id": local_order_id, "status": status,
            })
            return self.order(local_order_id)
        except Exception as exc:
            self._halt(f"status failure: {type(exc).__name__}")
            raise

    def cancel(self, local_order_id: str) -> dict[str, Any]:
        row = self.refresh(local_order_id)
        if row["status"] in TERMINAL_STATUSES:
            return row
        assert self.transport is not None
        try:
            response = self.transport.cancel_order(row["broker_order_id"])
            status = str(response.get("status", "")).lower()
            if status not in {"cancelled", "pending_cancel"}:
                raise ExecutionUncertain("cancel was not acknowledged")
            self.conn.execute(
                "UPDATE production_orders SET status=?,updated_at=?,detail=? WHERE local_order_id=?",
                (status, self._now().isoformat(), _canonical(response), local_order_id),
            )
            self.conn.commit()
            self._audit("production_cancel", {
                "local_order_id": local_order_id, "status": status,
            })
            return self.order(local_order_id)
        except Exception as exc:
            self._halt(f"cancel failure: {type(exc).__name__}")
            raise

    def cancel_expired(self) -> list[str]:
        now = self._now()
        cancelled: list[str] = []
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        rows = self.conn.execute(
            f"SELECT local_order_id,expires_at FROM production_orders "
            f"WHERE status IN ({placeholders})",
            tuple(ACTIVE_STATUSES),
        ).fetchall()
        for row in rows:
            if _utc(row["expires_at"]) <= now:
                result = self.cancel(row["local_order_id"])
                if result["status"] in {"cancelled", "pending_cancel"}:
                    cancelled.append(row["local_order_id"])
        return cancelled

    def recover(self) -> list[dict[str, Any]]:
        """Reconcile every nonterminal persisted order after a restart."""
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES | {"submitting"})
        rows = self.conn.execute(
            f"SELECT local_order_id,status FROM production_orders "
            f"WHERE status IN ({placeholders})",
            tuple(ACTIVE_STATUSES | {"submitting"}),
        ).fetchall()
        recovered = []
        for row in rows:
            if row["status"] == "submitting":
                self._halt("restart found order with uncertain submission state")
                raise ExecutionUncertain("manual broker reconciliation required")
            recovered.append(self.refresh(row["local_order_id"]))
        return recovered

    def health(self) -> dict[str, Any]:
        audit = self.db.verify_audit_chain()
        return {
            "enabled": self.config.enabled,
            "execution_authority": self.execution_authority,
            "transport_configured": self.transport is not None,
            "approval_verifier_configured": self.approval_verifier is not None,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "audit_valid": audit["valid"],
            "open_orders": self._counts(self._now().date().isoformat())[1],
        }
