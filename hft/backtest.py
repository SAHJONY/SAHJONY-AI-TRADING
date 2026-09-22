"""Event-driven backtester: feed -> strategy -> risk -> matching engine.

The loop, in simulation time:

1. pop due actions from the latency-delayed queue and submit them to the
   matching engine (fills flow back to the strategy and the risk gateway);
2. apply the next feed event to the book (quote levels) or the engine
   (trade prints, with queue-aware fill estimates for our resting orders);
3. hand a market snapshot to the strategy;
4. on the decision schedule, turn the strategy's intents into risk-checked
   orders, delayed by the latency model before they reach the exchange.

Latency model (v1): our *actions* are delayed by one one-way latency
sample (see :mod:`hft.latency`); the market-data leg is assumed
instantaneous — a documented simplification. Fees: the taker fee
(``taker_fee_bps``) applies to aggressive fills, the maker fee
(``maker_fee_bps``, default 0) to passive fills.

v2: the driver feeds fill and order-lifecycle events back into the risk
gateway (``note_fill`` / ``note_order_closed`` on fills, cancels,
rejections, and fully-filled orders) so the order-to-trade-ratio and
max-open-orders guards track live state instead of accumulating forever.

Everything is offline and deterministic given the seed.
"""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .book import BUY, SELL, L2OrderBook
from .feed import LEVEL, TRADE, FeedEvent, SyntheticL2Feed
from .latency import LatencyModel, TickToTradeTracker
from .matching import (
    FOK, IOC, LIMIT, MARKET, POST_ONLY,
    IncomingOrder, MatchingEngine,
)
from .risk import RiskGateway
from .strategies import (
    CANCEL, NEW, MarketSnapshot, OrderIntent, Strategy, StrategyFill,
)


@dataclass(frozen=True)
class BacktestConfig:
    taker_fee_bps: float = 5.0
    maker_fee_bps: float = 0.0
    decide_interval_ns: int = 10_000_000  # 10 ms sim between decide() calls
    equity_sample_every: int = 1_000  # events between equity samples
    seed: int = 7


# Depth levels attached to each MarketSnapshot from the L2 book.
SNAPSHOT_DEPTH_LEVELS = 5


@dataclass
class BacktestResult:
    metrics: Dict[str, float]
    fills: List[dict]
    notes: List[str] = field(default_factory=list)


class Backtest:
    def __init__(
        self,
        feed: SyntheticL2Feed,
        strategy: Strategy,
        risk: RiskGateway,
        config: Optional[BacktestConfig] = None,
        latency: Optional[LatencyModel] = None,
        tick_size: float = 0.01,
    ) -> None:
        self.feed = feed
        self.strategy = strategy
        self.risk = risk
        self.config = config or BacktestConfig()
        self.latency = latency or LatencyModel()
        self.tick_size = tick_size
        self.book = L2OrderBook(tick_size=tick_size)
        self.engine = MatchingEngine(self.book)
        self.tracker = TickToTradeTracker()
        # order bookkeeping: client_order_id -> dict(side, qty, submitted_ts, decision_ts)
        self._orders: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    def run(self) -> BacktestResult:
        cfg = self.config
        taker_rate = cfg.taker_fee_bps / 10_000.0
        maker_rate = cfg.maker_fee_bps / 10_000.0

        pending: list = []  # heap of (execute_ts, seq, kind, payload)
        seq = itertools.count()
        fills: List[dict] = []
        mid_hist_ts: List[int] = []
        mid_hist_px: List[float] = []
        equity_curve: List[float] = []
        inv_samples: List[int] = []

        submitted_qty = 0
        filled_qty = 0
        rejected = 0
        risk_rejected = 0
        n_orders = 0
        n_events = 0
        last_decide_ts: Optional[int] = None

        def record_fill(side: int, price: int, qty: int, aggressor: bool,
                        decision_ts: int, fill_ts: int) -> None:
            nonlocal filled_qty
            fee = price * self.tick_size * qty * (taker_rate if aggressor else maker_rate)
            self.strategy.on_fill(StrategyFill(side=side, price=price,
                                               qty=qty, fee=fee))
            self.risk.note_fill(fill_ts)
            filled_qty += qty
            fills.append({"ts_ns": fill_ts, "side": side, "price": price,
                          "qty": qty, "aggressor": aggressor, "fee": fee})
            if aggressor:
                self.tracker.record(decision_ts, fill_ts)

        def snapshot(ts_ns: int) -> MarketSnapshot:
            bbo = self.book.bbo()
            bid = bbo["bid"]
            ask = bbo["ask"]
            depth = self.book.depth(SNAPSHOT_DEPTH_LEVELS)
            return MarketSnapshot(
                ts_ns=ts_ns,
                bid=bid[0] if bid else None,
                ask=ask[0] if ask else None,
                bid_qty=bid[1] if bid else 0,
                ask_qty=ask[1] if ask else 0,
                mid=self.book.midprice(),
                microprice=self.book.microprice(),
                imbalance=self.book.imbalance(),
                bid_depth=tuple(depth["bids"]),
                ask_depth=tuple(depth["asks"]),
            )

        def drain_due(ts_ns: int) -> None:
            nonlocal rejected
            while pending and pending[0][0] <= ts_ns:
                _, _, kind, payload = heapq.heappop(pending)
                if kind == "cancel":
                    if self.engine.cancel(payload):
                        self.risk.note_order_closed(payload)
                    self._orders.pop(payload, None)
                else:  # new order
                    order, decision_ts = payload
                    res = self.engine.submit(order)
                    meta = self._orders.get(order.client_order_id, {})
                    meta["submitted"] = True
                    if res.status in ("rejected",):
                        rejected += 1
                    for f in res.fills:
                        record_fill(order.side, f.price, f.qty, True,
                                    decision_ts, order.ts_ns)
                    if res.status == "rejected" or res.leaves_qty == 0:
                        # fully filled / cancelled-on-entry (IOC) / rejected:
                        # free the open-order slot in the risk gateway
                        self.risk.note_order_closed(order.client_order_id)
                        self._orders.pop(order.client_order_id, None)

        def maybe_decide(ts_ns: int) -> None:
            nonlocal n_orders, risk_rejected, last_decide_ts, submitted_qty
            if last_decide_ts is not None and \
                    ts_ns - last_decide_ts < cfg.decide_interval_ns:
                return
            last_decide_ts = ts_ns
            snap = snapshot(ts_ns)
            mid = snap.mid if snap.mid is not None else 0.0
            for intent in self.strategy.decide(ts_ns):
                if intent.action == CANCEL:
                    dec = self.risk.check_cancel(intent.target_order_id)
                    if not dec.approved:
                        risk_rejected += 1
                        continue
                    heapq.heappush(pending, (self.latency.apply(ts_ns),
                                             next(seq), "cancel",
                                             intent.target_order_id))
                    continue
                if intent.action != NEW:
                    risk_rejected += 1
                    continue
                # risk check at decision time (pre-trade)
                dec = self.risk.check_new_order(
                    client_order_id=intent.client_order_id,
                    side=intent.side, qty=intent.qty, price_ticks=intent.price,
                    position=self.strategy.position,
                    ref_price_ticks=mid if mid > 0 else 1.0,
                    ts_ns=ts_ns,
                )
                if not dec.approved:
                    risk_rejected += 1
                    continue
                n_orders += 1
                submitted_qty += intent.qty
                order = IncomingOrder(
                    client_order_id=intent.client_order_id,
                    owner="self", side=intent.side, qty=intent.qty,
                    order_type=intent.order_type, price=intent.price,
                    ts_ns=self.latency.apply(ts_ns),
                )
                self._orders[intent.client_order_id] = {
                    "side": intent.side, "qty": intent.qty,
                    "decision_ts": ts_ns,
                }
                heapq.heappush(pending, (order.ts_ns, next(seq), "new",
                                        (order, ts_ns)))

        for event in self.feed:
            ts = event.ts_ns
            n_events += 1
            drain_due(ts)

            if event.kind == LEVEL:
                self.book.set_level(event.side, event.price, event.qty)
            else:  # TRADE
                for f in self.engine.apply_external_trade(event.side, event.qty):
                    # passive fill of our resting order; decision ts unknown
                    # for feed-driven fills -> use event ts (no tracker sample)
                    fee = f.price * self.tick_size * f.qty * maker_rate
                    self.strategy.on_fill(StrategyFill(
                        side=(BUY if event.side == SELL else SELL),
                        price=f.price, qty=f.qty, fee=fee))
                    self.risk.note_fill(ts)
                    filled_qty += f.qty
                    fills.append({"ts_ns": ts,
                                  "side": (BUY if event.side == SELL else SELL),
                                  "price": f.price, "qty": f.qty,
                                  "aggressor": False, "fee": fee})
                # reconcile: submitted orders no longer resting in the engine
                # were fully filled by prints -> free their risk slots
                for cid, meta in list(self._orders.items()):
                    if meta.get("submitted") and cid not in self.engine._live:
                        self.risk.note_order_closed(cid)
                        self._orders.pop(cid, None)
                if hasattr(self.strategy, "on_trade_print"):
                    try:
                        self.strategy.on_trade_print(event.side, event.qty)
                    except TypeError:
                        try:
                            self.strategy.on_trade_print(ts)
                        except TypeError:
                            pass

            snap = snapshot(ts)
            if snap.mid is not None:
                mid_hist_ts.append(ts)
                mid_hist_px.append(snap.mid)
            self.strategy.on_market(snap)
            maybe_decide(ts)

            if n_events % cfg.equity_sample_every == 0:
                mid = self.book.midprice()
                eq = self.strategy.equity(mid)
                self.risk.mark(eq)
                equity_curve.append(eq)
                inv_samples.append(abs(self.strategy.position))

        # drain anything still scheduled after the feed ends
        while pending:
            _, _, kind, payload = heapq.heappop(pending)
            if kind == "cancel":
                if self.engine.cancel(payload):
                    self.risk.note_order_closed(payload)
                self._orders.pop(payload, None)
            else:
                order, decision_ts = payload
                res = self.engine.submit(order)
                if res.status == "rejected":
                    rejected += 1
                for f in res.fills:
                    record_fill(order.side, f.price, f.qty, True,
                                decision_ts, order.ts_ns)
                if res.status == "rejected" or res.leaves_qty == 0:
                    self.risk.note_order_closed(order.client_order_id)
                    self._orders.pop(order.client_order_id, None)

        final_mid = self.book.midprice()
        final_equity = self.strategy.equity(final_mid)
        self.risk.mark(final_equity)
        equity_curve.append(final_equity)

        metrics = self._metrics(
            fills=fills, equity_curve=np.asarray(equity_curve, dtype=float),
            mid_ts=np.asarray(mid_hist_ts, dtype=np.int64),
            mid_px=np.asarray(mid_hist_px, dtype=float),
            inv_samples=inv_samples, n_events=n_events, n_orders=n_orders,
            submitted_qty=submitted_qty,
            filled_qty=filled_qty, rejected=rejected,
            risk_rejected=risk_rejected, final_equity=final_equity,
            sim_seconds=self.feed.sim_seconds, tick_size=self.tick_size,
        )
        notes = [
            "Simulator only: synthetic seeded feed, no real market data.",
            "Market-data latency leg assumed zero in v1; action leg delayed "
            f"by LatencyModel (one_way={self.latency.config.one_way_ns} ns).",
            f"Taker fee {cfg.taker_fee_bps} bps, maker fee {cfg.maker_fee_bps} bps.",
            "End-of-run position marked to market, not liquidated.",
        ]
        return BacktestResult(metrics=metrics, fills=fills, notes=notes)

    # ------------------------------------------------------------------
    def _metrics(self, *, fills, equity_curve, mid_ts, mid_px, inv_samples,
                 n_events, n_orders, submitted_qty, filled_qty, rejected,
                 risk_rejected, final_equity, sim_seconds,
                 tick_size) -> Dict[str, float]:
        m: Dict[str, float] = {}
        m["events"] = float(n_events)
        m["orders_submitted"] = float(n_orders)
        m["orders_rejected_engine"] = float(rejected)
        m["orders_rejected_risk"] = float(risk_rejected)
        m["fills"] = float(len(fills))
        m["fill_rate"] = (filled_qty / submitted_qty) if submitted_qty else 0.0
        m["total_pnl"] = float(final_equity)
        m["fees_paid"] = float(sum(f["fee"] for f in fills))
        m["final_position"] = float(self.strategy.position)
        m["avg_abs_inventory"] = float(np.mean(inv_samples)) if inv_samples else 0.0
        m["orders_per_sec"] = n_orders / sim_seconds if sim_seconds else 0.0

        if equity_curve.size > 1:
            rets = np.diff(equity_curve)
            std = float(np.std(rets))
            # per-sample Sharpe, documented as such (samples are evenly
            # spaced in event count, not in calendar time)
            m["sharpe_per_sample"] = (
                float(np.mean(rets)) / std * math.sqrt(rets.size) if std > 0 else 0.0
            )
            peak = np.maximum.accumulate(equity_curve)
            dd = peak - equity_curve
            m["max_drawdown"] = float(np.max(dd))
        else:
            m["sharpe_per_sample"] = 0.0
            m["max_drawdown"] = 0.0

        # adverse selection: markout of aggressive fills vs future mid
        for horizon_s, key in ((1, "markout_1s_ticks"), (10, "markout_10s_ticks")):
            mos = self._markouts(fills, mid_ts, mid_px, horizon_s)
            m[key] = float(np.mean(mos)) if mos else 0.0
            m[key + "_n"] = float(len(mos))
        ttt = self.tracker.stats()
        m["tick_to_trade_mean_us"] = ttt.get("mean_us", 0.0)
        m["tick_to_trade_p99_us"] = ttt.get("p99", 0.0) / 1000.0 if ttt.get("p99") else 0.0
        return m

    @staticmethod
    def _markouts(fills, mid_ts, mid_px, horizon_s: int):
        """Mean markout in ticks for aggressive fills.

        markout = our_side_sign * (mid(t+h) - fill_price).
        Positive = price moved in our favour after we took liquidity
        (good); negative = adverse selection.
        """
        if mid_ts.size == 0:
            return []
        out = []
        horizon_ns = int(horizon_s * 1_000_000_000)
        for f in fills:
            if not f["aggressor"]:
                continue
            target = f["ts_ns"] + horizon_ns
            i = int(np.searchsorted(mid_ts, target))
            if i >= mid_ts.size:
                continue
            sign = 1 if f["side"] == BUY else -1
            out.append(sign * (float(mid_px[i]) - f["price"]))
        return out
