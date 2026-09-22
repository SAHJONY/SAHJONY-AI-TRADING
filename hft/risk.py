"""Pre-trade risk gateway (research simulator).

Fail-closed by construction:

* any malformed input (non-positive qty, non-positive limit price, NaN,
  unknown action, non-string symbol) is **rejected**, never defaulted to
  permissive;
* the kill switch, once tripped, rejects every new order until explicitly
  reset;
* breaching the daily loss limit trips the kill switch automatically.

Checks, in order: kill switch -> input sanity -> duplicate order id ->
global order-rate limit -> per-symbol order-rate limit -> per-minute
notional limit -> fat-finger price sanity -> max open orders ->
order-to-trade ratio guard -> max order notional -> max position
(projected) -> daily loss limit. Cancels always pass (a cancel reduces
risk).

The gateway tracks open orders (ids approved but not yet closed via
: meth:`note_order_closed`) and fills (via :meth:`note_fill`) to power the
max-open-orders limit and the order-to-trade ratio guard. :meth:`kill`
trips the switch and *returns* the open order ids so the caller/driver
can cancel them itself — the gateway never touches the matching engine.

Optional auditing: pass an :class:`hft.audit.AuditLog` to the constructor;
every :meth:`check_new_order` decision is then logged as a
``"risk_decision"`` event. No other behavior changes.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

from .book import BUY, SELL

try:  # optional at import time; only needed when audit= is supplied
    from .audit import AuditLog
except Exception:  # pragma: no cover - defensive only
    AuditLog = None  # type: ignore[assignment]

APPROVED = "approved"
REJECTED = "rejected"

ONE_SECOND_NS = 1_000_000_000
ONE_MINUTE_NS = 60 * ONE_SECOND_NS

# Rolling window for the order-to-trade ratio guard. Long enough to be
# meaningful for a quoting strategy; short enough that stale flow ages
# out of the ratio.
OTR_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: float = 25_000.0  # dollars per single order
    max_position: int = 200  # units, absolute
    max_orders_per_sec: int = 100  # new orders per rolling second (global)
    daily_loss_limit: float = 1_000.0  # dollars of equity drawdown vs start
    allow_shorts: bool = True
    max_orders_per_sec_per_symbol: int = 20  # new orders per rolling second, per symbol
    max_notional_per_minute: float = 100_000.0  # dollars per rolling 60s
    max_open_orders: int = 50  # unfilled/unclosed orders held at once
    max_order_to_trade_ratio: float = 50.0  # orders/fills ceiling in the rolling OTR window
    min_fills_before_otr: int = 10  # OTR guard is inactive until this many fills exist
    max_price_deviation_bps: float = 500.0  # fat-finger: limit price vs reference mid


@dataclass
class RiskDecision:
    approved: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> "RiskDecision":
        return cls(True, APPROVED)

    @classmethod
    def no(cls, reason: str) -> "RiskDecision":
        return cls(False, reason)


class RiskGateway:
    """Stateful pre-trade risk checks."""

    def __init__(self, limits: Optional[RiskLimits] = None,
                 tick_size: float = 0.01,
                 audit: Optional["AuditLog"] = None) -> None:
        self.limits = limits or RiskLimits()
        self.tick_size = tick_size
        self.kill_switch = False
        self.kill_reason = ""
        self._seen_order_ids: Set[str] = set()
        self._order_times_ns: Deque[int] = deque()
        self._start_equity: Optional[float] = None
        self.equity = 0.0  # updated via mark()
        self.rejections = 0
        # v2 state
        self._audit = audit
        self._per_symbol_times_ns: Dict[str, Deque[int]] = {}
        self._minute_notional: Deque[Tuple[int, float]] = deque()
        self._open_order_ids: Set[str] = set()
        self._otr_order_times_ns: Deque[int] = deque()
        self._otr_fill_times_ns: Deque[int] = deque()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def trip_kill_switch(self, reason: str) -> None:
        self.kill_switch = True
        self.kill_reason = reason or "manual"

    def reset_kill_switch(self) -> None:
        self.kill_switch = False
        self.kill_reason = ""

    def kill(self, reason: str) -> List[str]:
        """Trip the kill switch and return the currently open order ids so
        the caller/driver can cancel them. Cancel-via-return: the gateway
        itself never touches the matching engine; the driver must issue
        the cancels and call :meth:`note_order_closed` for each one. The
        switch stays tripped (blocking new orders) until
        :meth:`reset_kill_switch` is called explicitly."""
        self.trip_kill_switch(reason)
        return sorted(self._open_order_ids)

    def mark(self, equity: float) -> None:
        """Update current equity (cash + marked position). Trips the kill
        switch if the daily loss limit is breached."""
        if not math.isfinite(equity):
            self.trip_kill_switch("non-finite equity")
            return
        self.equity = equity
        if self._start_equity is None:
            self._start_equity = equity
        if self._start_equity - equity >= self.limits.daily_loss_limit:
            self.trip_kill_switch(
                f"daily loss limit breached: {self._start_equity - equity:.2f}")

    # ------------------------------------------------------------------
    # fill / open-order bookkeeping (called by the driver, not the engine)
    # ------------------------------------------------------------------
    def note_fill(self, ts_ns: int) -> None:
        """Record one fill at ``ts_ns`` for the order-to-trade ratio guard.
        Raises ``ValueError`` on a malformed timestamp rather than
        recording garbage (fail-closed)."""
        if not isinstance(ts_ns, int) or ts_ns < 0:
            raise ValueError("invalid timestamp for note_fill")
        self._otr_fill_times_ns.append(ts_ns)

    def note_order_closed(self, client_order_id: str) -> None:
        """Mark an approved order as closed (filled/cancelled by the
        driver). Frees a slot under ``max_open_orders``. Unknown ids are
        ignored silently — the order may already have been closed."""
        if client_order_id:
            self._open_order_ids.discard(client_order_id)

    def open_order_count(self) -> int:
        """Number of approved-but-not-yet-closed orders."""
        return len(self._open_order_ids)

    # ------------------------------------------------------------------
    # checks
    # ------------------------------------------------------------------
    def check_new_order(
        self,
        client_order_id: str,
        side: int,
        qty: int,
        price_ticks: Optional[int],
        position: int,
        ref_price_ticks: float,
        ts_ns: int,
        symbol: str = "",
    ) -> RiskDecision:
        """Validate one new order. ``ref_price_ticks`` is the current mid
        (for notional estimation of market orders). ``symbol`` scopes the
        per-symbol rate limit; pass ``""`` (default) to skip it — the
        global rate limit still applies. Called with keyword args by the
        backtester."""
        if self.kill_switch:
            return self._record(client_order_id, self._no(f"kill switch: {self.kill_reason}"))

        # --- input sanity (fail-closed) ---
        if not client_order_id or not isinstance(client_order_id, str):
            return self._record(client_order_id, self._no("empty client_order_id"))
        if side not in (BUY, SELL):
            return self._record(client_order_id, self._no("invalid side"))
        if not isinstance(qty, int) or qty <= 0:
            return self._record(client_order_id, self._no("qty must be a positive integer"))
        if price_ticks is not None and (
            not isinstance(price_ticks, int) or price_ticks <= 0
        ):
            return self._record(client_order_id, self._no("price must be a positive integer tick or None"))
        if not isinstance(ref_price_ticks, (int, float)) or not math.isfinite(ref_price_ticks) \
                or ref_price_ticks <= 0:
            return self._record(client_order_id, self._no("invalid reference price"))
        if not isinstance(ts_ns, int) or ts_ns < 0:
            return self._record(client_order_id, self._no("invalid timestamp"))
        if not isinstance(symbol, str):
            return self._record(client_order_id, self._no("invalid symbol"))

        # --- duplicates ---
        if client_order_id in self._seen_order_ids:
            return self._record(client_order_id, self._no("duplicate client_order_id"))

        # --- global rate limit (rolling 1s window) ---
        cutoff = ts_ns - ONE_SECOND_NS
        times = self._order_times_ns
        while times and times[0] < cutoff:
            times.popleft()
        if len(times) >= self.limits.max_orders_per_sec:
            return self._record(client_order_id, self._no("order rate limit"))

        # --- per-symbol rate limit (rolling 1s window; skipped when empty) ---
        if symbol:
            sym_times = self._per_symbol_times_ns.setdefault(symbol, deque())
            while sym_times and sym_times[0] < cutoff:
                sym_times.popleft()
            if len(sym_times) >= self.limits.max_orders_per_sec_per_symbol:
                return self._record(client_order_id, self._no("per-symbol order rate limit"))

        # --- notional of this order ---
        px = float(price_ticks) if price_ticks is not None else float(ref_price_ticks)
        notional = px * self.tick_size * qty

        # --- per-minute notional (rolling 60s window) ---
        minute_cutoff = ts_ns - ONE_MINUTE_NS
        minute = self._minute_notional
        minute_sum = 0.0
        for entry_ts, entry_notional in minute:
            if entry_ts >= minute_cutoff:
                minute_sum += entry_notional
        while minute and minute[0][0] < minute_cutoff:
            minute.popleft()
        if minute_sum + notional > self.limits.max_notional_per_minute:
            return self._record(client_order_id, self._no(
                f"per-minute notional {minute_sum + notional:.2f} exceeds limit"))

        # --- fat-finger price sanity (limit orders only) ---
        if price_ticks is not None:
            deviation_bps = abs(float(price_ticks) - float(ref_price_ticks)) \
                / float(ref_price_ticks) * 10_000.0
            if deviation_bps > self.limits.max_price_deviation_bps:
                return self._record(client_order_id, self._no(
                    f"fat-finger: price deviates {deviation_bps:.1f} bps from reference"))

        # --- max open orders ---
        if len(self._open_order_ids) >= self.limits.max_open_orders:
            return self._record(client_order_id, self._no("max open orders reached"))

        # --- order-to-trade ratio guard (rolling OTR window) ---
        # Inactive until enough fills exist — a cold start with zero fills
        # must never block trading.
        otr_cutoff = ts_ns - int(OTR_WINDOW_SECONDS * 1e9)
        otr_orders = self._otr_order_times_ns
        otr_fills = self._otr_fill_times_ns
        while otr_orders and otr_orders[0] < otr_cutoff:
            otr_orders.popleft()
        while otr_fills and otr_fills[0] < otr_cutoff:
            otr_fills.popleft()
        fills = len(otr_fills)
        if fills >= self.limits.min_fills_before_otr:
            orders = len(otr_orders) + 1  # include the order under review
            ratio = orders / fills
            if ratio > self.limits.max_order_to_trade_ratio:
                return self._record(client_order_id, self._no(
                    f"order-to-trade ratio {ratio:.1f} exceeds limit"))

        # --- max single-order notional ---
        if notional > self.limits.max_order_notional:
            return self._record(client_order_id, self._no(f"order notional {notional:.2f} exceeds limit"))

        # --- projected position ---
        projected = position + (qty if side == BUY else -qty)
        if abs(projected) > self.limits.max_position:
            return self._record(client_order_id, self._no(f"projected position {projected} exceeds limit"))
        if not self.limits.allow_shorts and projected < 0:
            return self._record(client_order_id, self._no("shorts not allowed"))

        # --- daily loss ---
        if self._start_equity is not None and \
                self._start_equity - self.equity >= self.limits.daily_loss_limit:
            self.trip_kill_switch("daily loss limit breached at order check")
            return self._record(client_order_id, self._no("daily loss limit"))

        # --- approved: record everything ---
        self._seen_order_ids.add(client_order_id)
        times.append(ts_ns)
        if symbol:
            self._per_symbol_times_ns[symbol].append(ts_ns)
        minute.append((ts_ns, notional))
        otr_orders.append(ts_ns)
        self._open_order_ids.add(client_order_id)
        return self._record(client_order_id, RiskDecision.ok())

    def check_cancel(self, client_order_id: str) -> RiskDecision:
        """Cancels always pass — cancelling can only reduce risk."""
        if not client_order_id:
            return RiskDecision.no("empty client_order_id")
        return RiskDecision.ok()

    def _no(self, reason: str) -> RiskDecision:
        self.rejections += 1
        return RiskDecision.no(reason)

    def _record(self, client_order_id: str, decision: RiskDecision) -> RiskDecision:
        """Log one check_new_order decision to the audit log (if any)."""
        if self._audit is not None:
            try:
                self._audit.log("risk_decision", {
                    "client_order_id": client_order_id,
                    "approved": decision.approved,
                    "reason": decision.reason,
                })
            except Exception:
                # Auditing must never change a risk decision.
                pass
        return decision
