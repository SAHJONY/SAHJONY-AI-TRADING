"""Deterministic microstructure features for shadow/research use.

No broker calls and no order submission. All functions are pure and fail closed on
invalid inputs so telemetry cannot silently manufacture alpha.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from marketdata.schema import QuoteEvent, TradeEvent


@dataclass(frozen=True)
class MicrostructureSnapshot:
    symbol: str
    mid: float
    spread_bps: float
    depth_imbalance: float
    order_flow_imbalance: float
    realized_vol: float
    trade_pressure: float


def depth_imbalance(quote: QuoteEvent) -> float:
    total = quote.bid_size + quote.ask_size
    if total <= 0:
        return 0.0
    return max(-1.0, min(1.0, (quote.bid_size - quote.ask_size) / total))


def trade_pressure(trades: Iterable[TradeEvent]) -> float:
    buy = sell = 0.0
    for t in trades:
        notional = t.price * t.size
        if not math.isfinite(notional) or notional <= 0:
            continue
        if t.side == "buy":
            buy += notional
        elif t.side == "sell":
            sell += notional
    total = buy + sell
    if total <= 0:
        return 0.0
    return max(-1.0, min(1.0, (buy - sell) / total))


def order_flow_imbalance(quotes: Iterable[QuoteEvent]) -> float:
    rows = list(quotes)
    if len(rows) < 2:
        return 0.0
    flow = 0.0
    scale = 0.0
    prev = rows[0]
    for cur in rows[1:]:
        if cur.symbol != prev.symbol:
            raise ValueError("mixed symbols in quote series")
        db = cur.bid_size - prev.bid_size
        da = cur.ask_size - prev.ask_size
        # Rising bid depth is positive; rising ask depth is negative.
        step = db - da
        if math.isfinite(step):
            flow += step
            scale += abs(db) + abs(da)
        prev = cur
    if scale <= 0:
        return 0.0
    return max(-1.0, min(1.0, flow / scale))


def realized_volatility(prices: Iterable[float]) -> float:
    xs = [float(x) for x in prices]
    if len(xs) < 3 or any((not math.isfinite(x) or x <= 0) for x in xs):
        return 0.0
    rets = [math.log(xs[i] / xs[i - 1]) for i in range(1, len(xs))]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / max(1, n - 1)
    return math.sqrt(max(0.0, var))


def build_snapshot(quote: QuoteEvent, recent_quotes: Iterable[QuoteEvent],
                   recent_trades: Iterable[TradeEvent], prices: Iterable[float]) -> MicrostructureSnapshot:
    quotes = list(recent_quotes)
    if quotes and any(q.symbol != quote.symbol for q in quotes):
        raise ValueError("mixed symbols in quote series")
    trades = list(recent_trades)
    if trades and any(t.symbol != quote.symbol for t in trades):
        raise ValueError("mixed symbols in trade series")
    return MicrostructureSnapshot(
        symbol=quote.symbol,
        mid=quote.mid,
        spread_bps=quote.spread_bps,
        depth_imbalance=depth_imbalance(quote),
        order_flow_imbalance=order_flow_imbalance(quotes),
        realized_vol=realized_volatility(prices),
        trade_pressure=trade_pressure(trades),
    )
