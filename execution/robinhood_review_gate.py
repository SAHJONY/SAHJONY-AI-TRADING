"""Fail-closed policy gate for Robinhood Agentic pre-trade reviews.

This module has no broker, MCP, network, or order-placement imports.  It only
validates whether a proposed equity order is eligible to be sent to Robinhood's
``review_equity_order`` tool.  A successful review never grants execution
authority and never means the order may be placed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Iterable


_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_ALLOWED_SIDES = {"buy"}
_ALLOWED_ORDER_TYPES = {"limit"}


@dataclass(frozen=True)
class ReviewRequest:
    symbol: str
    side: str
    quantity: float
    limit_price: float
    account_last4: str = "1131"
    order_type: str = "limit"
    time_in_force: str = "gfd"

    @property
    def notional(self) -> float:
        return self.quantity * self.limit_price


@dataclass(frozen=True)
class ReviewContext:
    identity_verified: bool
    expected_last4: str
    data_ready: bool
    funding_ready: bool
    positions_reconciled: bool
    quote_fresh: bool
    market_open: bool
    execution_authority: bool
    trading_armed: bool


@dataclass(frozen=True)
class ReviewPolicy:
    max_notional: float = 1.00
    allowed_symbols: tuple[str, ...] = ("VTI",)
    require_market_open: bool = True


@dataclass(frozen=True)
class ReviewDecision:
    allowed: bool
    blockers: tuple[str, ...]
    request: dict
    execution_authority: bool = False
    can_place_order: bool = False
    stage: str = "review-only"


def _finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0


def evaluate_review_request(
    request: ReviewRequest,
    context: ReviewContext,
    policy: ReviewPolicy | None = None,
) -> ReviewDecision:
    """Validate eligibility for a pre-trade review, never order placement."""
    policy = policy or ReviewPolicy()
    blockers: list[str] = []

    symbol = request.symbol.strip().upper()
    side = request.side.strip().lower()
    order_type = request.order_type.strip().lower()
    tif = request.time_in_force.strip().lower()

    if not _SYMBOL.fullmatch(symbol):
        blockers.append("invalid symbol")
    if symbol not in {item.upper() for item in policy.allowed_symbols}:
        blockers.append("symbol is not in the review allowlist")
    if side not in _ALLOWED_SIDES:
        blockers.append("review-only canary permits long buys only")
    if order_type not in _ALLOWED_ORDER_TYPES:
        blockers.append("review-only canary permits limit orders only")
    if tif != "gfd":
        blockers.append("review-only canary requires good-for-day orders")
    if not _finite_positive(request.quantity):
        blockers.append("quantity must be finite and positive")
    if not _finite_positive(request.limit_price):
        blockers.append("limit price must be finite and positive")
    if not _finite_positive(request.notional) or request.notional > policy.max_notional:
        blockers.append(f"review notional exceeds ${policy.max_notional:.2f} cap")

    if not context.identity_verified:
        blockers.append("Agentic account identity is not verified")
    if request.account_last4 != context.expected_last4:
        blockers.append("request account does not match configured Agentic account")
    if not context.data_ready:
        blockers.append("broker data is not ready")
    if not context.funding_ready:
        blockers.append("account funding is not ready")
    if not context.positions_reconciled:
        blockers.append("positions are not reconciled")
    if not context.quote_fresh:
        blockers.append("quote is stale or unavailable")
    if policy.require_market_open and not context.market_open:
        blockers.append("market is closed")

    # Review mode must remain structurally non-executing.  An armed/execution
    # capable context is rejected so this gate cannot be reused as a placement
    # authorization shortcut.
    if context.execution_authority or context.trading_armed:
        blockers.append("review-only gate requires execution authority to remain disabled")

    normalized = asdict(request)
    normalized.update(
        symbol=symbol,
        side=side,
        order_type=order_type,
        time_in_force=tif,
        notional=round(request.notional, 8),
    )
    return ReviewDecision(
        allowed=not blockers,
        blockers=tuple(blockers),
        request=normalized,
    )


def assert_no_execution_authority(decision: ReviewDecision) -> None:
    if decision.execution_authority or decision.can_place_order:
        raise RuntimeError("review decision unexpectedly contains execution authority")
