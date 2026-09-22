"""L2 limit order book with price-time priority (research simulator).

Prices are integer ticks; quantities are integer units; timestamps are
integer nanoseconds. The book holds *resting limit orders* only — it never
matches anything by itself (see :mod:`hft.matching` for the engine).

A limit order that would cross the spread on arrival is **rejected** rather
than matched: crossing flow is the matching engine's job, and a pure L2
book must never silently convert a resting order into an aggressive one.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

BUY = 1
SELL = -1

_VALID_SIDES = (BUY, SELL)


@dataclass
class BookOrder:
    """A single resting limit order."""

    order_id: int
    side: int  # BUY or SELL
    price: int  # integer ticks
    qty: int  # remaining quantity (integer units)
    ts_ns: int  # insertion timestamp, integer ns
    owner: str = "market"  # "market" (synthetic flow) or "self" (our simulated orders)
    queue_ahead: int = 0  # units ahead of this order at its level when inserted


class CrossedBookError(ValueError):
    """Raised when an order would cross the book on insertion."""


class L2OrderBook:
    """Price-time priority L2 book.

    Bids are kept in a descending sorted price list, asks ascending. Each
    price level holds a FIFO deque of :class:`BookOrder` (time priority).
    """

    def __init__(self, tick_size: float = 0.01) -> None:
        self.tick_size = tick_size
        self._bids: Dict[int, Deque[BookOrder]] = {}
        self._asks: Dict[int, Deque[BookOrder]] = {}
        self._bid_prices: List[int] = []  # ascending; best = last
        self._ask_prices: List[int] = []  # ascending; best = first
        self._index: Dict[int, Tuple[int, int]] = {}  # order_id -> (side, price)
        self._next_auto_id = 1

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _levels(self, side: int) -> Dict[int, Deque[BookOrder]]:
        return self._bids if side == BUY else self._asks

    def _prices(self, side: int) -> List[int]:
        return self._bid_prices if side == BUY else self._ask_prices

    def _best_price(self, side: int) -> Optional[int]:
        px = self._prices(side)
        if not px:
            return None
        return px[-1] if side == BUY else px[0]

    def _remove_level_if_empty(self, side: int, price: int) -> None:
        levels = self._levels(side)
        dq = levels.get(price)
        if dq is not None and not dq:
            del levels[price]
            prices = self._prices(side)
            i = bisect_left(prices, price)
            if i < len(prices) and prices[i] == price:
                prices.pop(i)

    # ------------------------------------------------------------------
    # mutation
    # ------------------------------------------------------------------
    def add(self, order: BookOrder) -> None:
        """Insert a resting limit order.

        Raises:
            ValueError: on invalid side / non-positive price or quantity,
                or a duplicate order id.
            CrossedBookError: if the order would cross the spread.
        """
        if order.side not in _VALID_SIDES:
            raise ValueError(f"invalid side {order.side!r}")
        if not isinstance(order.price, int) or order.price <= 0:
            raise ValueError(f"price must be a positive integer tick, got {order.price!r}")
        if not isinstance(order.qty, int) or order.qty <= 0:
            raise ValueError(f"qty must be a positive integer, got {order.qty!r}")
        if order.order_id in self._index:
            raise ValueError(f"duplicate order_id {order.order_id}")

        opp = SELL if order.side == BUY else BUY
        best_opp = self._best_price(opp)
        if best_opp is not None:
            if order.side == BUY and order.price >= best_opp:
                raise CrossedBookError(
                    f"buy @ {order.price} would cross best ask {best_opp}"
                )
            if order.side == SELL and order.price <= best_opp:
                raise CrossedBookError(
                    f"sell @ {order.price} would cross best bid {best_opp}"
                )

        levels = self._levels(order.side)
        dq = levels.get(order.price)
        if dq is None:
            dq = deque()
            levels[order.price] = dq
            insort(self._prices(order.side), order.price)
        order.queue_ahead = sum(o.qty for o in dq)
        dq.append(order)
        self._index[order.order_id] = (order.side, order.price)

    def cancel(self, order_id: int) -> bool:
        """Remove an order by id. Returns True if it existed."""
        loc = self._index.pop(order_id, None)
        if loc is None:
            return False
        side, price = loc
        dq = self._levels(side)[price]
        for i, o in enumerate(dq):
            if o.order_id == order_id:
                del dq[i]
                break
        self._remove_level_if_empty(side, price)
        return True

    def replace(
        self,
        order_id: int,
        new_price: Optional[int] = None,
        new_qty: Optional[int] = None,
    ) -> None:
        """Cancel + re-insert (loses queue position).

        If the re-insertion is invalid (e.g. crossed), the original order is
        restored untouched.
        """
        loc = self._index.get(order_id)
        if loc is None:
            raise KeyError(f"unknown order_id {order_id}")
        side, price = loc
        dq = self._levels(side)[price]
        old = next(o for o in dq if o.order_id == order_id)
        saved = BookOrder(
            order_id=old.order_id,
            side=old.side,
            price=old.price,
            qty=old.qty,
            ts_ns=old.ts_ns,
            owner=old.owner,
        )
        self.cancel(order_id)
        new = BookOrder(
            order_id=saved.order_id,
            side=saved.side,
            price=new_price if new_price is not None else saved.price,
            qty=new_qty if new_qty is not None else saved.qty,
            ts_ns=saved.ts_ns,
            owner=saved.owner,
        )
        try:
            self.add(new)
        except (ValueError, CrossedBookError):
            self.add(saved)  # restore original
            raise

    def set_level(self, side: int, price: int, total_qty: int) -> None:
        """Set the *non-self* liquidity at a price level (feed-driven).

        Used by the synthetic feed to move the book around. Our own resting
        orders (``owner == "self"``) are never removed by this call: if the
        requested total is below our resting quantity at the level, the
        non-self liquidity is set to zero and our orders stay.
        """
        if side not in _VALID_SIDES:
            raise ValueError(f"invalid side {side!r}")
        if not isinstance(price, int) or price <= 0:
            raise ValueError(f"price must be a positive integer tick, got {price!r}")
        if not isinstance(total_qty, int) or total_qty < 0:
            raise ValueError(f"total_qty must be a non-negative integer, got {total_qty!r}")

        levels = self._levels(side)
        dq = levels.get(price)
        self_qty = 0
        kept: Deque[BookOrder] = deque()
        if dq is not None:
            for o in dq:
                if o.owner == "self":
                    self_qty += o.qty
                    kept.append(o)
        want_market = max(0, total_qty - self_qty)
        if want_market == 0 and not kept:
            if dq is not None:
                del levels[price]
                prices = self._prices(side)
                i = bisect_left(prices, price)
                if i < len(prices) and prices[i] == price:
                    prices.pop(i)
            return
        if dq is None:
            dq = deque()
            levels[price] = dq
            insort(self._prices(side), price)
        # rebuild level: synthetic liquidity first (behind our orders in time
        # priority — our orders were there first), then our kept orders
        new_dq: Deque[BookOrder] = deque(kept)
        if want_market > 0:
            new_dq.appendleft(
                BookOrder(
                    order_id=self._alloc_id(),
                    side=side,
                    price=price,
                    qty=want_market,
                    ts_ns=0,
                    owner="market",
                )
            )
            self._index[new_dq[0].order_id] = (side, price)
        levels[price] = new_dq

    def _alloc_id(self) -> int:
        oid = -self._next_auto_id  # negative ids: synthetic, never collide
        self._next_auto_id += 1
        return oid

    def apply_aggressor(self, side: int, qty: int) -> List[Tuple[int, int, int]]:
        """Consume resting liquidity as an external aggressor.

        ``side`` is the aggressor's side (BUY lifts the ask). Returns a list
        of ``(price, qty, order_id)`` executions in price-time priority.
        Our own resting orders are included — callers that need
        queue-aware fill estimates should use
        :meth:`hft.matching.MatchingEngine.apply_external_trade` instead.
        """
        if side not in _VALID_SIDES:
            raise ValueError(f"invalid side {side!r}")
        if not isinstance(qty, int) or qty <= 0:
            raise ValueError(f"qty must be a positive integer, got {qty!r}")
        opp = SELL if side == BUY else BUY
        fills: List[Tuple[int, int, int]] = []
        remaining = qty
        while remaining > 0:
            best = self._best_price(opp)
            if best is None:
                break
            dq = self._levels(opp)[best]
            while dq and remaining > 0:
                o = dq[0]
                take = min(o.qty, remaining)
                o.qty -= take
                remaining -= take
                fills.append((best, take, o.order_id))
                if o.qty == 0:
                    dq.popleft()
                    self._index.pop(o.order_id, None)
            self._remove_level_if_empty(opp, best)
        return fills

    # ------------------------------------------------------------------
    # read-only views
    # ------------------------------------------------------------------
    def best_bid(self) -> Optional[Tuple[int, int]]:
        p = self._best_price(BUY)
        if p is None:
            return None
        return (p, sum(o.qty for o in self._bids[p]))

    def best_ask(self) -> Optional[Tuple[int, int]]:
        p = self._best_price(SELL)
        if p is None:
            return None
        return (p, sum(o.qty for o in self._asks[p]))

    def bbo(self) -> Dict[str, Optional[Tuple[int, int]]]:
        return {"bid": self.best_bid(), "ask": self.best_ask()}

    def midprice(self) -> Optional[float]:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb[0] + ba[0]) / 2.0

    def spread_ticks(self) -> Optional[int]:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        return ba[0] - bb[0]

    def depth(self, n: int = 5) -> Dict[str, List[Tuple[int, int]]]:
        """Top-``n`` levels per side as ``(price, total_qty)`` lists."""
        bids = [
            (p, sum(o.qty for o in self._bids[p]))
            for p in reversed(self._bid_prices[-n:])
        ]
        asks = [
            (p, sum(o.qty for o in self._asks[p])) for p in self._ask_prices[:n]
        ]
        return {"bids": bids, "asks": asks}

    def _level_qty(self, side: int, levels: int) -> int:
        prices = self._prices(side)
        sel = prices[-levels:] if side == BUY else prices[:levels]
        return sum(sum(o.qty for o in self._levels(side)[p]) for p in sel)

    def imbalance(self, levels: int = 5) -> Optional[float]:
        """Order-book imbalance over the top ``levels``: (B-A)/(B+A)."""
        b = self._level_qty(BUY, levels)
        a = self._level_qty(SELL, levels)
        denom = b + a
        if denom == 0:
            return None
        return (b - a) / denom

    def microprice(self, levels: int = 5) -> Optional[float]:
        """Quantity-weighted microprice over the top ``levels`` (ticks)."""
        b = self._level_qty(BUY, levels)
        a = self._level_qty(SELL, levels)
        denom = b + a
        if denom == 0:
            return None
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        return (a * bb[0] + b * ba[0]) / denom

    def self_orders(self) -> List[BookOrder]:
        """All resting orders with ``owner == "self"``."""
        out = []
        for side in (BUY, SELL):
            for dq in self._levels(side).values():
                out.extend(o for o in dq if o.owner == "self")
        return out

    def __len__(self) -> int:
        return len(self._index)
