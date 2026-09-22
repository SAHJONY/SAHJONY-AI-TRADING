"""Matching-engine simulator (research only — no live orders).

Simulates a price-time priority limit order book exchange for a single
instrument:

* Order types: ``limit``, ``market``, ``ioc`` (limit, immediate-or-cancel),
  ``fok`` (limit, fill-or-kill), ``post_only`` (limit that must not cross).
* Incoming orders walk the resting book in price-time priority; partial
  fills are reported; unfilled limit quantity rests (unless IOC).
* **Queue-position-aware fills for our own resting orders**: when an
  *external* trade print (from the synthetic feed) hits a level where our
  orders rest, we estimate fills with a simple queue-ahead model — our
  order only fills after the liquidity ahead of it at that level is
  consumed. This is an approximation, not a real queue model.
* **Self-trade prevention**: an incoming order from ``owner == "self"``
  that would match a resting ``"self"`` order is rejected outright.

All inputs are validated fail-closed: anything malformed is rejected, never
partially applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .book import BUY, SELL, L2OrderBook, BookOrder, CrossedBookError

LIMIT = "limit"
MARKET = "market"
IOC = "ioc"
FOK = "fok"
POST_ONLY = "post_only"

_VALID_TYPES = (LIMIT, MARKET, IOC, FOK, POST_ONLY)

# statuses
NEW = "new"  # accepted, resting
FILLED = "filled"
PARTIAL = "partial"  # partially filled, remainder resting (limit)
EXPIRED = "expired"  # IOC remainder / market leftover
REJECTED = "rejected"
CANCELED = "canceled"


@dataclass
class IncomingOrder:
    client_order_id: str
    owner: str  # "self" or anything else
    side: int  # BUY / SELL
    qty: int
    order_type: str = LIMIT
    price: Optional[int] = None  # ticks; required for limit/ioc/fok/post_only
    ts_ns: int = 0


@dataclass
class Fill:
    price: int  # ticks
    qty: int
    aggressor: bool  # True if our incoming order took liquidity
    counterparty_order_id: int = 0
    ts_ns: int = 0


@dataclass
class OrderResult:
    status: str
    fills: List[Fill] = field(default_factory=list)
    leaves_qty: int = 0
    reason: str = ""


class MatchingEngine:
    """Price-time matching against an :class:`L2OrderBook`."""

    def __init__(self, book: L2OrderBook) -> None:
        self.book = book
        # start our id sequence past any ids already resting in the book
        # (the feed uses negative synthetic ids; direct book.add callers
        # may use small positives)
        self._seq = (max(book._index) + 1) if book._index else 1
        self._live: Dict[str, BookOrder] = {}  # client_order_id -> resting order

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def submit(self, order: IncomingOrder) -> OrderResult:
        """Validate and execute one incoming order. Never raises on bad
        input — it returns ``REJECTED`` with a reason (fail-closed)."""
        err = self._validate(order)
        if err:
            return OrderResult(status=REJECTED, reason=err)
        if order.client_order_id in self._live:
            return OrderResult(status=REJECTED, reason="duplicate client_order_id")

        if order.order_type == MARKET:
            if self._would_self_trade(order):
                return OrderResult(status=REJECTED, reason="self-trade prevention")
            fills = self._match(order.side, order.qty, limit_price=None,
                                owner=order.owner, ts_ns=order.ts_ns)
            filled = sum(f.qty for f in fills)
            # market orders never rest; any shortfall simply expires
            if filled == order.qty:
                return OrderResult(status=FILLED, fills=fills, leaves_qty=0)
            return OrderResult(status=EXPIRED, fills=fills, leaves_qty=0,
                               reason="" if filled else "no liquidity")

        # ---- limit-family ----
        if order.order_type == POST_ONLY and self._is_marketable(order.side, order.price):
            return OrderResult(status=REJECTED, reason="post_only would cross")

        if order.order_type == FOK:
            if self._available_at(order.side, order.price) < order.qty:
                return OrderResult(status=REJECTED, reason="fok not fully fillable")

        if self._would_self_trade(order):
            return OrderResult(status=REJECTED, reason="self-trade prevention")

        fills = self._match(order.side, order.qty, limit_price=order.price,
                            owner=order.owner, ts_ns=order.ts_ns)
        filled = sum(f.qty for f in fills)
        leaves = order.qty - filled

        if order.order_type == IOC:
            return OrderResult(
                status=FILLED if leaves == 0 else (EXPIRED if filled else EXPIRED),
                fills=fills, leaves_qty=0,
                reason="" if filled else "ioc no fill",
            )

        if leaves > 0:
            rest = BookOrder(
                order_id=self._seq, side=order.side, price=order.price,
                qty=leaves, ts_ns=order.ts_ns, owner=order.owner,
            )
            self._seq += 1
            try:
                self.book.add(rest)
            except (ValueError, CrossedBookError) as exc:  # fail-closed
                return OrderResult(status=REJECTED, fills=fills,
                                   reason=f"rest rejected: {exc}")
            self._live[order.client_order_id] = rest
            status = PARTIAL if filled else NEW
            return OrderResult(status=status, fills=fills, leaves_qty=leaves)
        return OrderResult(status=FILLED, fills=fills, leaves_qty=0)

    def cancel(self, client_order_id: str) -> bool:
        """Cancel one of our resting orders. Returns True if it existed."""
        resting = self._live.pop(client_order_id, None)
        if resting is None:
            return False
        return self.book.cancel(resting.order_id)

    def apply_external_trade(self, side: int, qty: int) -> List[Fill]:
        """Apply a trade print from the market-data feed.

        ``side`` is the *aggressor's* side. The print walks the book in
        price-time priority. Fills for our own resting orders use a simple
        queue-ahead estimate: the print must first consume everything
        ahead of our order in time priority at that level (measured from
        the book's current state) before any quantity reaches us. This is
        an approximation of real queue dynamics, not a calibrated model.

        Returns fills for ``owner == "self"`` orders only.
        """
        if side not in (BUY, SELL) or not isinstance(qty, int) or qty <= 0:
            raise ValueError("invalid external trade")
        opp = SELL if side == BUY else BUY
        our_fills: List[Fill] = []
        remaining = qty
        while remaining > 0:
            best = self.book._best_price(opp)
            if best is None:
                break
            dq = self.book._levels(opp)[best]
            orders = list(dq)
            level_total = sum(o.qty for o in orders)
            if level_total == 0:
                break
            c = min(remaining, level_total)  # print qty reaching this level
            cum = 0  # original qty ahead of the current order in time priority
            consumed = 0
            for o in orders:
                if c <= cum:
                    break
                room = c - cum  # print qty left after the queue ahead of o
                original = o.qty
                take = min(original, room)
                if take > 0:
                    o.qty -= take
                    consumed += take
                    if o.qty == 0:
                        dq.remove(o)
                        self.book._index.pop(o.order_id, None)
                        self._drop_live(o.order_id)
                    if o.owner == "self":
                        our_fills.append(Fill(price=best, qty=take,
                                              aggressor=False,
                                              counterparty_order_id=o.order_id))
                cum += original
            remaining -= consumed
            self.book._remove_level_if_empty(opp, best)
            if consumed == 0:
                break
        return our_fills

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _validate(self, order: IncomingOrder) -> Optional[str]:
        if order.side not in (BUY, SELL):
            return "invalid side"
        if not isinstance(order.qty, int) or order.qty <= 0:
            return "qty must be a positive integer"
        if order.order_type not in _VALID_TYPES:
            return f"unknown order_type {order.order_type!r}"
        if order.order_type == MARKET:
            if order.price is not None:
                return "market order must not carry a price"
        else:
            if not isinstance(order.price, int) or order.price <= 0:
                return "limit price must be a positive integer tick"
        if not order.client_order_id or not isinstance(order.client_order_id, str):
            return "client_order_id must be a non-empty string"
        if not isinstance(order.ts_ns, int) or order.ts_ns < 0:
            return "ts_ns must be a non-negative integer"
        return None

    def _is_marketable(self, side: int, price: int) -> bool:
        opp = SELL if side == BUY else BUY
        best = self.book._best_price(opp)
        if best is None:
            return False
        return price >= best if side == BUY else price <= best

    def _available_at(self, side: int, price: int) -> int:
        """Total resting qty on the opposite side at acceptable prices."""
        opp = SELL if side == BUY else BUY
        total = 0
        for p in self.book._prices(opp):
            if side == BUY and p > price:
                break
            if side == SELL and p < price:
                break
            total += sum(o.qty for o in self.book._levels(opp)[p])
        return total

    def _would_self_trade(self, order: IncomingOrder) -> bool:
        """True if the incoming self order would hit a resting self order."""
        if order.owner != "self":
            return False
        opp = SELL if order.side == BUY else BUY
        prices = self.book._prices(opp)
        # market orders sweep every level; limit orders stop at their price
        seq = prices if order.side == BUY else list(reversed(prices))
        for p in seq:
            if order.price is not None:
                if order.side == BUY and p > order.price:
                    break
                if order.side == SELL and p < order.price:
                    break
            for o in self.book._levels(opp)[p]:
                if o.owner == "self":
                    return True
        return False

    def _match(self, side: int, qty: int, limit_price: Optional[int],
               owner: str, ts_ns: int) -> List[Fill]:
        opp = SELL if side == BUY else BUY
        fills: List[Fill] = []
        remaining = qty
        while remaining > 0:
            best = self.book._best_price(opp)
            if best is None:
                break
            if limit_price is not None:
                if side == BUY and best > limit_price:
                    break
                if side == SELL and best < limit_price:
                    break
            dq = self.book._levels(opp)[best]
            while dq and remaining > 0:
                o = dq[0]
                if o.owner == "self" and owner == "self":
                    # belt-and-braces: should have been rejected earlier
                    dq.popleft()
                    self.book._index.pop(o.order_id, None)
                    self._drop_live(o.order_id)
                    continue
                take = min(o.qty, remaining)
                o.qty -= take
                remaining -= take
                fills.append(Fill(price=best, qty=take, aggressor=True,
                                  counterparty_order_id=o.order_id, ts_ns=ts_ns))
                if o.qty == 0:
                    dq.popleft()
                    self.book._index.pop(o.order_id, None)
                    self._drop_live(o.order_id)
            self.book._remove_level_if_empty(opp, best)
        return fills

    def _drop_live(self, book_order_id: int) -> None:
        dead = [cid for cid, o in self._live.items() if o.order_id == book_order_id]
        for cid in dead:
            del self._live[cid]
