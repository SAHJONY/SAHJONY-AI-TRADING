"""Research strategies for the simulator (paper signals only).

Strategies NEVER touch the order book or the matching engine directly.
They consume market snapshots via :meth:`Strategy.on_market`, learn about
their fills via :meth:`Strategy.on_fill`, and express everything as
:class:`OrderIntent` lists returned from :meth:`Strategy.decide`. The
backtester translates intents into risk-checked, latency-delayed engine
actions.

Included:

* :class:`AvellanedaStoikovMarketMaker` — the classic Avellaneda-Stoikov
  (2008) optimal market-making sketch: a reservation price skewed by
  inventory and an optimal spread from volatility and order-arrival
  estimates. Quote sizes are fixed; one-sided quoting near the inventory
  cap.
* :class:`MicrostructureSignalStrategy` — a toy short-horizon signal
  combining signed order-flow imbalance (trades) with microprice deviation;
  goes long/short small size on threshold crosses and flattens on
  reversal. This is a *demonstration of plumbing*, not a viable edge.
* :class:`MultiLevelFlowStrategy` — threshold directional signal
  combining signed trade-flow imbalance with multi-level book imbalance
  from snapshot depth. Same demonstration-only status.
* :class:`AdverseSelectionMarketMaker` — Avellaneda-Stoikov plus a
  volatility quoting pause and a heuristic adverse-selection response
  (spread widening + reservation-price shift when the book leans against
  inventory). Research heuristics, not proven edges.

Everything here is a research simulator: nothing claims profitability.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from .book import BUY, SELL

NEW = "new"
CANCEL = "cancel"


@dataclass(frozen=True)
class MarketSnapshot:
    ts_ns: int
    bid: Optional[int]  # ticks
    ask: Optional[int]  # ticks
    bid_qty: int
    ask_qty: int
    mid: Optional[float]  # ticks
    microprice: Optional[float]  # ticks
    imbalance: Optional[float]  # [-1, 1]
    # Top-N book depth, best price first, as (price_ticks, qty) pairs.
    # Populated by the backtester from L2OrderBook.depth(); may be empty
    # for hand-built snapshots, in which case strategies fall back to the
    # top-level ``imbalance`` field.
    bid_depth: Tuple[Tuple[int, int], ...] = ()
    ask_depth: Tuple[Tuple[int, int], ...] = ()


@dataclass(frozen=True)
class StrategyFill:
    side: int  # our side: BUY / SELL
    price: int  # ticks
    qty: int
    fee: float  # dollars paid on this fill


@dataclass
class OrderIntent:
    """What the strategy wants. The backtester executes via risk + engine."""

    action: str  # NEW or CANCEL
    side: int = BUY
    qty: int = 0
    price: Optional[int] = None  # ticks; None for market
    order_type: str = "limit"  # limit/market/ioc/fok/post_only
    tag: str = ""
    client_order_id: str = ""  # set for NEW; identifies the order
    target_order_id: str = ""  # set for CANCEL; which order to cancel


class Strategy:
    """Base class: market-data in, order intents out."""

    def __init__(self, tick_size: float = 0.01) -> None:
        self.tick_size = tick_size
        self.position = 0  # signed inventory in units
        self.cash = 0.0  # dollars
        self.fills = 0

    # -- inputs ------------------------------------------------------
    def on_market(self, snap: MarketSnapshot) -> None:
        """Lightweight per-event update. Keep this cheap."""

    def on_fill(self, fill: StrategyFill) -> None:
        dollar = fill.price * self.tick_size * fill.qty
        if fill.side == BUY:
            self.position += fill.qty
            self.cash -= dollar
        else:
            self.position -= fill.qty
            self.cash += dollar
        self.cash -= fill.fee
        self.fills += 1

    # -- output ------------------------------------------------------
    def decide(self, ts_ns: int) -> List[OrderIntent]:
        """Called on the backtester's decision schedule. Returns intents."""
        return []

    # -- helpers -----------------------------------------------------
    def equity(self, mid_ticks: Optional[float]) -> float:
        if mid_ticks is None:
            return self.cash
        return self.cash + self.position * mid_ticks * self.tick_size


class AvellanedaStoikovMarketMaker(Strategy):
    """Avellaneda-Stoikov-style quoting (textbook formulas, toy calibration).

    reservation price:  r = mid - gamma * sigma^2 * T * (q - target)
    optimal spread:     s = gamma * sigma^2 * T + (2/gamma) * ln(1 + gamma/kappa)

    sigma is the rolling stdev of midprice changes (ticks per event),
    kappa the arrival rate of market orders (events per second, estimated
    from trade prints). ``inventory_target`` skews the reservation price
    toward a non-zero inventory target (default 0, which reproduces the
    classic formula). Quotes refresh on a fixed schedule; stale quotes
    are cancelled first. Inventory beyond ``max_inventory`` forces
    one-sided quoting. With ``size_shrink=True`` the quote size shrinks
    linearly toward 1 lot as |q - target| approaches ``max_inventory``;
    the default (False) keeps the fixed-size behaviour.

    Subclass hooks: :meth:`_quoting_paused` and
    :meth:`_reservation_and_spread`.
    """

    def __init__(
        self,
        gamma: float = 0.1,
        kappa: float = 50.0,
        horizon: float = 1.0,
        order_size: int = 5,
        max_inventory: int = 50,
        quote_interval_ns: int = 50_000_000,  # refresh every 50 ms sim
        vol_window: int = 500,
        tick_size: float = 0.01,
        inventory_target: int = 0,
        size_shrink: bool = False,
    ) -> None:
        super().__init__(tick_size=tick_size)
        self.gamma = gamma
        self.kappa = kappa
        self.horizon = horizon
        self.order_size = order_size
        self.max_inventory = max_inventory
        self.quote_interval_ns = quote_interval_ns
        self.inventory_target = inventory_target
        self.size_shrink = size_shrink
        self._mids: Deque[float] = deque(maxlen=vol_window)
        self._trades = 0
        self._trade_window_start: Optional[int] = None
        self._last_quote_ns: Optional[int] = None
        self._live_quotes: Dict[str, str] = {}  # client_order_id -> side tag
        self._seq = 0
        self._last_snap: Optional[MarketSnapshot] = None

    def on_market(self, snap: MarketSnapshot) -> None:
        self._last_snap = snap
        if snap.mid is not None:
            self._mids.append(snap.mid)

    def on_trade_print(self, ts_ns: int) -> None:
        self._trades += 1
        if self._trade_window_start is None:
            self._trade_window_start = ts_ns

    def _sigma(self) -> float:
        if len(self._mids) < 10:
            return 1.0
        diffs = [b - a for a, b in zip(list(self._mids)[:-1], list(self._mids)[1:])]
        mean = sum(diffs) / len(diffs)
        var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
        return math.sqrt(var) if var > 0 else 1.0

    def _kappa_est(self, ts_ns: int) -> float:
        if self._trade_window_start is None or ts_ns <= self._trade_window_start:
            return self.kappa
        elapsed_s = (ts_ns - self._trade_window_start) / 1e9
        if elapsed_s <= 0:
            return self.kappa
        return max(1.0, self._trades / elapsed_s)

    def decide(self, ts_ns: int) -> List[OrderIntent]:
        snap = self._last_snap
        if snap is None or snap.mid is None or snap.bid is None or snap.ask is None:
            return []
        if self._last_quote_ns is not None and ts_ns - self._last_quote_ns < self.quote_interval_ns:
            return []

        intents: List[OrderIntent] = []
        if self._quoting_paused(ts_ns):
            # risk-off: pull every live quote and emit nothing new
            for cid in list(self._live_quotes):
                intents.append(OrderIntent(action=CANCEL, target_order_id=cid,
                                           tag="mm-pause"))
            self._live_quotes.clear()
            return intents

        r, spread = self._reservation_and_spread(ts_ns, snap)

        raw_bid = math.floor(r - spread / 2.0)
        raw_ask = math.ceil(r + spread / 2.0)
        # never cross the touch; keep at least the touch prices honest
        bid_px = min(raw_bid, snap.ask - 1)
        ask_px = max(raw_ask, snap.bid + 1)
        if bid_px >= ask_px:  # degenerate (huge inventory skew): widen out
            mid_i = int(round(snap.mid))
            bid_px, ask_px = mid_i - 2, mid_i + 2

        for cid in list(self._live_quotes):
            intents.append(OrderIntent(action=CANCEL, target_order_id=cid, tag="mm-refresh"))
        self._live_quotes.clear()

        want_bid = self.position > -self.max_inventory
        want_ask = self.position < self.max_inventory
        # hard inventory cap: one-sided only at the boundary
        if self.position <= -self.max_inventory:
            want_bid, want_ask = True, False
        if self.position >= self.max_inventory:
            want_bid, want_ask = False, True

        if want_bid:
            intents.append(self._quote(BUY, bid_px, "mm-bid"))
        if want_ask:
            intents.append(self._quote(SELL, ask_px, "mm-ask"))
        self._last_quote_ns = ts_ns
        return intents

    # -- subclass hooks ---------------------------------------------
    def _quoting_paused(self, ts_ns: int) -> bool:
        """True -> cancel all live quotes and emit no new ones this round.

        The base class never pauses; subclasses (e.g.
        :class:`AdverseSelectionMarketMaker`) override this.
        """
        return False

    def _reservation_and_spread(
        self, ts_ns: int, snap: MarketSnapshot
    ) -> Tuple[float, float]:
        """Reservation price (ticks) and target spread (ticks)."""
        sigma = self._sigma()
        kappa = self._kappa_est(ts_ns)
        g, T = self.gamma, self.horizon
        q = self.position - self.inventory_target
        r = snap.mid - g * sigma * sigma * T * q
        spread = g * sigma * sigma * T + (2.0 / g) * math.log(1.0 + g / kappa)
        return r, max(spread, 1.0)

    def _effective_quote_size(self) -> int:
        """Quote size, optionally shrinking as inventory drifts from target.

        Off by default (returns ``order_size`` unchanged). When
        ``size_shrink=True``, the size falls linearly from ``order_size``
        at the target to a floor of 1 lot as |q - target| reaches
        ``max_inventory``.
        """
        if not self.size_shrink or self.max_inventory <= 0:
            return self.order_size
        ratio = min(1.0, abs(self.position - self.inventory_target) / self.max_inventory)
        return max(1, int(round(self.order_size * (1.0 - ratio))))

    def _quote(self, side: int, price: int, tag: str) -> OrderIntent:
        self._seq += 1
        cid = f"mm-{self._seq}"
        self._live_quotes[cid] = tag
        return OrderIntent(action=NEW, side=side, qty=self._effective_quote_size(),
                           price=price, order_type="post_only",
                           tag=tag, client_order_id=cid)


class MicrostructureSignalStrategy(Strategy):
    """Toy short-horizon signal: order-flow imbalance + microprice deviation.

    signal = w_ofi * ofi_norm + w_mp * (microprice - mid) / spread

    where ofi_norm is the signed trade-quantity imbalance over a rolling
    window, normalised to [-1, 1]. Cross above +threshold -> target long;
    below -threshold -> target short; inside the band -> flat. Entries are
    passive (limit at the touch); exits/flattens are aggressive (IOC).
    """

    def __init__(
        self,
        window: int = 200,
        entry_threshold: float = 0.35,
        w_ofi: float = 0.6,
        w_mp: float = 0.4,
        max_position: int = 20,
        order_size: int = 5,
        decide_interval_ns: int = 10_000_000,  # 10 ms sim
        tick_size: float = 0.01,
    ) -> None:
        super().__init__(tick_size=tick_size)
        self.window = window
        self.entry_threshold = entry_threshold
        self.w_ofi = w_ofi
        self.w_mp = w_mp
        self.max_position = max_position
        self.order_size = order_size
        self.decide_interval_ns = decide_interval_ns
        self._signed_qty: Deque[int] = deque(maxlen=window)
        self._last_snap: Optional[MarketSnapshot] = None
        self._last_decide_ns: Optional[int] = None
        self._seq = 0

    def on_market(self, snap: MarketSnapshot) -> None:
        self._last_snap = snap

    def on_trade_print(self, aggressor_side: int, qty: int) -> None:
        self._signed_qty.append(qty if aggressor_side == BUY else -qty)

    def _signal(self) -> float:
        snap = self._last_snap
        if snap is None or snap.mid is None or not self._signed_qty:
            return 0.0
        tot = sum(abs(q) for q in self._signed_qty)
        ofi_norm = (sum(self._signed_qty) / tot) if tot else 0.0
        mp_dev = 0.0
        if snap.microprice is not None and snap.bid is not None and snap.ask is not None:
            spread = max(1, snap.ask - snap.bid)
            mp_dev = (snap.microprice - snap.mid) / spread
        return self.w_ofi * ofi_norm + self.w_mp * mp_dev

    def decide(self, ts_ns: int) -> List[OrderIntent]:
        snap = self._last_snap
        if snap is None or snap.bid is None or snap.ask is None:
            return []
        if self._last_decide_ns is not None and ts_ns - self._last_decide_ns < self.decide_interval_ns:
            return []
        self._last_decide_ns = ts_ns

        sig = self._signal()
        if sig > self.entry_threshold:
            target = self.max_position
        elif sig < -self.entry_threshold:
            target = -self.max_position
        else:
            target = 0
        delta = target - self.position
        if abs(delta) < self.order_size:
            return []
        side = BUY if delta > 0 else SELL
        qty = min(abs(delta), self.order_size)
        # entries passive at the touch, exits/flattens aggressive
        entering = (target > 0 and self.position <= 0) or (target < 0 and self.position >= 0)
        if entering:
            price = snap.bid if side == BUY else snap.ask
            otype = "post_only"
        else:
            price = snap.ask if side == BUY else snap.bid
            otype = "ioc"
        self._seq += 1
        return [OrderIntent(action=NEW, side=side, qty=qty, price=price,
                            order_type=otype, tag="micro",
                            client_order_id=f"micro-{self._seq}")]


class MultiLevelFlowStrategy(Strategy):
    """Threshold directional strategy: signed trade flow + multi-level depth.

    signal = w_flow * flow_imbalance + w_book * book_imbalance

    * ``flow_imbalance``: signed aggressor quantity over a rolling window
      of trade prints, normalised to [-1, 1];
    * ``book_imbalance``: (bid_qty - ask_qty) / (bid_qty + ask_qty) summed
      over the top ``depth_levels`` of the snapshot's ``bid_depth`` /
      ``ask_depth`` (falls back to the snapshot's top-level ``imbalance``
      when depth is unavailable).

    Cross above +entry_threshold -> target long; below -entry_threshold ->
    target short; inside the band -> flat. Entries are passive (limit at
    the touch); exits/flattens are aggressive (IOC). This is a
    demonstration of plumbing, not a viable edge.
    """

    def __init__(
        self,
        window: int = 200,
        depth_levels: int = 5,
        entry_threshold: float = 0.35,
        w_flow: float = 0.5,
        w_book: float = 0.5,
        max_position: int = 20,
        order_size: int = 5,
        decide_interval_ns: int = 10_000_000,  # 10 ms sim
        tick_size: float = 0.01,
    ) -> None:
        super().__init__(tick_size=tick_size)
        self.window = window
        self.depth_levels = depth_levels
        self.entry_threshold = entry_threshold
        self.w_flow = w_flow
        self.w_book = w_book
        self.max_position = max_position
        self.order_size = order_size
        self.decide_interval_ns = decide_interval_ns
        self._signed_qty: Deque[int] = deque(maxlen=window)
        self._last_snap: Optional[MarketSnapshot] = None
        self._last_decide_ns: Optional[int] = None
        self._seq = 0

    def on_market(self, snap: MarketSnapshot) -> None:
        self._last_snap = snap

    def on_trade_print(self, aggressor_side: int, qty: int) -> None:
        self._signed_qty.append(qty if aggressor_side == BUY else -qty)

    def _flow_imbalance(self) -> float:
        tot = sum(abs(q) for q in self._signed_qty)
        return (sum(self._signed_qty) / tot) if tot else 0.0

    def _book_imbalance(self, snap: MarketSnapshot) -> float:
        if snap.bid_depth and snap.ask_depth:
            b = sum(q for _, q in snap.bid_depth[: self.depth_levels])
            a = sum(q for _, q in snap.ask_depth[: self.depth_levels])
            tot = b + a
            return (b - a) / tot if tot else 0.0
        return snap.imbalance if snap.imbalance is not None else 0.0

    def _signal(self) -> float:
        snap = self._last_snap
        if snap is None or snap.mid is None or not self._signed_qty:
            return 0.0
        return (self.w_flow * self._flow_imbalance()
                + self.w_book * self._book_imbalance(snap))

    def decide(self, ts_ns: int) -> List[OrderIntent]:
        snap = self._last_snap
        if snap is None or snap.bid is None or snap.ask is None:
            return []
        if self._last_decide_ns is not None and ts_ns - self._last_decide_ns < self.decide_interval_ns:
            return []
        self._last_decide_ns = ts_ns

        sig = self._signal()
        if sig > self.entry_threshold:
            target = self.max_position
        elif sig < -self.entry_threshold:
            target = -self.max_position
        else:
            target = 0
        delta = target - self.position
        if abs(delta) < self.order_size:
            return []
        side = BUY if delta > 0 else SELL
        qty = min(abs(delta), self.order_size)
        # entries passive at the touch, exits/flattens aggressive
        entering = (target > 0 and self.position <= 0) or (target < 0 and self.position >= 0)
        if entering:
            price = snap.bid if side == BUY else snap.ask
            otype = "post_only"
        else:
            price = snap.ask if side == BUY else snap.bid
            otype = "ioc"
        self._seq += 1
        return [OrderIntent(action=NEW, side=side, qty=qty, price=price,
                            order_type=otype, tag="mlflow",
                            client_order_id=f"mlflow-{self._seq}")]


class AdverseSelectionMarketMaker(AvellanedaStoikovMarketMaker):
    """AS market maker with a volatility pause and an adverse-selection guard.

    Two research heuristics layered on the base Avellaneda-Stoikov
    quoter (both are uncalibrated toys, not proven edges):

    * **Volatility pause.** When the rolling stdev of midprice changes
      (ticks per event, the same estimator the base class uses) exceeds
      ``vol_pause_threshold``, quoting pauses: live quotes are cancelled
      and no NEW intents are emitted until volatility falls back under
      the threshold. ``vol_pause_threshold=None`` disables the pause.
    * **Adverse-selection response.** When the book leans against our
      inventory direction -- long inventory while the multi-level
      imbalance is more negative than ``-imbalance_threshold`` and the
      microprice sits below mid (mirrored for shorts) -- the target
      spread is multiplied by ``adverse_widen_factor`` and the
      reservation price is shifted ``adverse_shift_ticks`` in the
      direction of the pressure (down when long, up when short). The
      intent is to make the inventory side cheaper to offload while
      demanding more compensation; it is a heuristic, not a calibrated
      toxicity model.

    All base-class parameters (including ``inventory_target`` and
    ``size_shrink``) are accepted unchanged.
    """

    def __init__(
        self,
        *args,
        vol_pause_threshold: Optional[float] = 25.0,
        adverse_widen_factor: float = 2.0,
        adverse_shift_ticks: int = 2,
        imbalance_threshold: float = 0.3,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.vol_pause_threshold = vol_pause_threshold
        self.adverse_widen_factor = adverse_widen_factor
        self.adverse_shift_ticks = adverse_shift_ticks
        self.imbalance_threshold = imbalance_threshold
        self.paused = False  # last evaluated pause state (for inspection)

    def _quoting_paused(self, ts_ns: int) -> bool:
        if self.vol_pause_threshold is None:
            self.paused = False
            return False
        self.paused = self._sigma() > self.vol_pause_threshold
        return self.paused

    def _adverse(self, snap: MarketSnapshot) -> bool:
        """True when book pressure leans against our inventory direction."""
        q = self.position
        if q == 0:
            return False
        imb = snap.imbalance if snap.imbalance is not None else 0.0
        mp_dev = 0.0
        if snap.microprice is not None and snap.mid is not None:
            mp_dev = snap.microprice - snap.mid  # ticks
        if q > 0:  # long: hurt by downward pressure
            return imb < -self.imbalance_threshold and mp_dev < 0
        # short: hurt by upward pressure
        return imb > self.imbalance_threshold and mp_dev > 0

    def _reservation_and_spread(
        self, ts_ns: int, snap: MarketSnapshot
    ) -> Tuple[float, float]:
        r, spread = super()._reservation_and_spread(ts_ns, snap)
        if self._adverse(snap):
            spread *= self.adverse_widen_factor
            # shift with the pressure: down when long, up when short
            r += -self.adverse_shift_ticks if self.position > 0 else self.adverse_shift_ticks
        return r, spread
