import pytest

from marketdata.schema import QuoteEvent, TradeEvent
from marketdata.microstructure import (
    build_snapshot,
    depth_imbalance,
    order_flow_imbalance,
    realized_volatility,
    trade_pressure,
)


def test_quote_schema_and_spread_bps():
    q = QuoteEvent("BTC/USD", bid=100.0, ask=100.2, bid_size=4.0, ask_size=2.0)
    assert q.mid == pytest.approx(100.1)
    assert q.spread_bps == pytest.approx((0.2 / 100.1) * 10_000)
    assert depth_imbalance(q) == pytest.approx(1 / 3)


def test_crossed_quote_fails_closed():
    with pytest.raises(ValueError):
        QuoteEvent("SPY", bid=101.0, ask=100.0)


def test_trade_pressure_is_notional_weighted():
    trades = [
        TradeEvent("SPY", price=100.0, size=2.0, side="buy"),
        TradeEvent("SPY", price=100.0, size=1.0, side="sell"),
    ]
    assert trade_pressure(trades) == pytest.approx(1 / 3)


def test_order_flow_imbalance_detects_bid_building():
    qs = [
        QuoteEvent("SPY", 100, 100.1, 10, 10),
        QuoteEvent("SPY", 100, 100.1, 14, 8),
        QuoteEvent("SPY", 100, 100.1, 16, 7),
    ]
    assert order_flow_imbalance(qs) > 0


def test_mixed_symbol_series_fails_closed():
    qs = [
        QuoteEvent("SPY", 100, 100.1, 10, 10),
        QuoteEvent("QQQ", 100, 100.1, 11, 9),
    ]
    with pytest.raises(ValueError):
        order_flow_imbalance(qs)


def test_realized_volatility_requires_valid_history():
    assert realized_volatility([100.0, 101.0]) == 0.0
    assert realized_volatility([100.0, 101.0, 99.0, 102.0]) > 0.0
    assert realized_volatility([100.0, 0.0, 102.0]) == 0.0


def test_snapshot_is_shadow_safe_and_deterministic():
    q = QuoteEvent("BTC/USD", 100.0, 100.2, 5.0, 3.0)
    qs = [QuoteEvent("BTC/USD", 99.9, 100.1, 4.0, 4.0), q]
    trades = [TradeEvent("BTC/USD", 100.1, 1.0, "buy")]
    snap = build_snapshot(q, qs, trades, [99.0, 100.0, 100.5, 100.1])
    assert snap.symbol == "BTC/USD"
    assert snap.mid == pytest.approx(100.1)
    assert snap.trade_pressure == pytest.approx(1.0)
    assert snap.depth_imbalance > 0
