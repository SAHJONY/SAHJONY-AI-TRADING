"""Tests for HFT Lab v2 strategies (research simulator; no profit claims).

Covers:
  * MultiLevelFlowStrategy: multi-level book-imbalance sign, signal
    direction, depth fallback;
  * AdverseSelectionMarketMaker: volatility pause (quotes cancelled, no
    NEW intents while paused), adverse-selection widening/shift;
  * AvellanedaStoikovMarketMaker: inventory-target skew direction,
    inventory_target honoured, quote-size shrink (opt-in), hard cap
    one-sided quoting preserved;
  * backtest wiring: MarketSnapshot carries bid_depth/ask_depth.
"""

import unittest

from hft.backtest import Backtest, BacktestConfig
from hft.book import BUY, SELL
from hft.feed import SyntheticL2Feed
from hft.risk import RiskGateway, RiskLimits
from hft.strategies import (
    CANCEL,
    NEW,
    AdverseSelectionMarketMaker,
    AvellanedaStoikovMarketMaker,
    MarketSnapshot,
    MultiLevelFlowStrategy,
    StrategyFill,
)


def snap(ts_ns=0, bid=100, ask=102, bid_depth=(), ask_depth=(),
         mid=101.0, microprice=101.0, imbalance=None):
    return MarketSnapshot(
        ts_ns=ts_ns, bid=bid, ask=ask, bid_qty=0, ask_qty=0,
        mid=mid, microprice=microprice, imbalance=imbalance,
        bid_depth=bid_depth, ask_depth=ask_depth,
    )


def mm_quotes(position=0, **kw):
    """Fresh AS market maker at ``position``; returns ({side: price}, intents)."""
    s = AvellanedaStoikovMarketMaker(quote_interval_ns=0, **kw)
    if position:
        side = BUY if position > 0 else SELL
        s.on_fill(StrategyFill(side=side, price=101, qty=abs(position), fee=0.0))
    s.on_market(snap())
    intents = [i for i in s.decide(1) if i.action == NEW]
    return {i.side: i.price for i in intents}, intents


class TestMultiLevelBookImbalance(unittest.TestCase):
    def test_bid_heavy_book_positive(self):
        s = MultiLevelFlowStrategy(w_flow=0.0, w_book=1.0, decide_interval_ns=0)
        s.on_market(snap(bid_depth=((100, 50), (99, 40)),
                         ask_depth=((102, 10), (103, 10))))
        s.on_trade_print(BUY, 1)  # _signal needs at least one print
        self.assertGreater(s._book_imbalance(s._last_snap), 0)
        self.assertGreater(s._signal(), 0)

    def test_ask_heavy_book_negative(self):
        s = MultiLevelFlowStrategy(w_flow=0.0, w_book=1.0, decide_interval_ns=0)
        s.on_market(snap(bid_depth=((100, 10), (99, 10)),
                         ask_depth=((102, 50), (103, 40))))
        s.on_trade_print(SELL, 1)
        self.assertLess(s._book_imbalance(s._last_snap), 0)
        self.assertLess(s._signal(), 0)

    def test_depth_levels_limit(self):
        # depth_levels=1 counts the best level only: bid 50 vs ask 10
        s = MultiLevelFlowStrategy(w_flow=0.0, w_book=1.0, depth_levels=1,
                                   decide_interval_ns=0)
        s.on_market(snap(bid_depth=((100, 50), (99, 1000)),
                         ask_depth=((102, 10), (103, 1000))))
        self.assertAlmostEqual(s._book_imbalance(s._last_snap), (50 - 10) / 60.0)

    def test_empty_depth_falls_back_to_snapshot_imbalance(self):
        s = MultiLevelFlowStrategy(decide_interval_ns=0)
        self.assertEqual(s._book_imbalance(snap(imbalance=0.8)), 0.8)
        self.assertEqual(s._book_imbalance(snap(imbalance=None)), 0.0)

    def test_signal_drives_long(self):
        s = MultiLevelFlowStrategy(entry_threshold=0.35, decide_interval_ns=0)
        for _ in range(3):
            s.on_trade_print(BUY, 10)
        s.on_market(snap(bid_depth=((100, 90),), ask_depth=((102, 10),)))
        intents = s.decide(1)
        self.assertEqual(len(intents), 1)
        i = intents[0]
        self.assertEqual(i.action, NEW)
        self.assertEqual(i.side, BUY)
        self.assertEqual(i.order_type, "post_only")  # passive entry at touch
        self.assertEqual(i.price, 100)

    def test_signal_drives_short(self):
        s = MultiLevelFlowStrategy(entry_threshold=0.35, decide_interval_ns=0)
        for _ in range(3):
            s.on_trade_print(SELL, 10)
        s.on_market(snap(bid_depth=((100, 10),), ask_depth=((102, 90),)))
        intents = s.decide(1)
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].side, SELL)

    def test_flat_band_no_trade(self):
        s = MultiLevelFlowStrategy(entry_threshold=0.35, decide_interval_ns=0)
        s.on_trade_print(BUY, 5)
        s.on_trade_print(SELL, 5)  # net zero flow
        s.on_market(snap(bid_depth=((100, 10),), ask_depth=((102, 10),)))
        self.assertEqual(s.decide(1), [])


class TestVolatilityPause(unittest.TestCase):
    def _mm(self):
        return AdverseSelectionMarketMaker(quote_interval_ns=0, vol_window=30,
                                          vol_pause_threshold=5.0)

    def test_quotes_when_calm(self):
        s = self._mm()
        for t in range(12):
            s.on_market(snap(ts_ns=t, mid=101.0, microprice=101.0, imbalance=0.0))
        intents = s.decide(100)
        new = [i for i in intents if i.action == NEW]
        self.assertEqual(len(new), 2)
        self.assertFalse(s.paused)

    def test_pause_cancels_and_emits_no_new(self):
        s = self._mm()
        for t in range(12):
            s.on_market(snap(ts_ns=t, mid=101.0, microprice=101.0, imbalance=0.0))
        s.decide(100)
        self.assertEqual(len(s._live_quotes), 2)
        # volatile regime: alternating +/-50 tick moves -> stdev ~50
        for t in range(12, 30):
            mid = 1000.0 if t % 2 == 0 else 1050.0
            s.on_market(snap(ts_ns=t, mid=mid, microprice=mid, imbalance=0.0))
        intents = s.decide(200)
        self.assertTrue(s.paused)
        self.assertTrue(all(i.action == CANCEL for i in intents))
        self.assertFalse(any(i.action == NEW for i in intents))
        self.assertEqual(len(s._live_quotes), 0)
        # still paused, nothing live left -> empty
        self.assertEqual(s.decide(300), [])

    def test_resume_after_calm(self):
        s = self._mm()
        for t in range(12):
            s.on_market(snap(ts_ns=t, mid=101.0, microprice=101.0, imbalance=0.0))
        s.decide(100)
        for t in range(12, 30):
            mid = 1000.0 if t % 2 == 0 else 1050.0
            s.on_market(snap(ts_ns=t, mid=mid, microprice=mid, imbalance=0.0))
        s.decide(200)
        self.assertTrue(s.paused)
        # calm again long enough to flush the volatile samples (vol_window=30)
        for t in range(30, 70):
            s.on_market(snap(ts_ns=t, mid=101.0, microprice=101.0, imbalance=0.0))
        intents = s.decide(400)
        self.assertFalse(s.paused)
        self.assertEqual(len([i for i in intents if i.action == NEW]), 2)

    def test_pause_disabled_with_none(self):
        s = AdverseSelectionMarketMaker(quote_interval_ns=0, vol_window=30,
                                       vol_pause_threshold=None)
        for t in range(30):
            mid = 1000.0 if t % 2 == 0 else 1050.0
            s.on_market(snap(ts_ns=t, mid=mid, microprice=mid, imbalance=0.0))
        intents = s.decide(100)
        self.assertFalse(s.paused)
        self.assertEqual(len([i for i in intents if i.action == NEW]), 2)


class TestAdverseSelectionResponse(unittest.TestCase):
    def _mm(self):
        return AdverseSelectionMarketMaker(
            quote_interval_ns=0, vol_pause_threshold=None,
            adverse_widen_factor=2.0, adverse_shift_ticks=2,
            imbalance_threshold=0.3)

    def test_adverse_widens_and_shifts_down_when_long(self):
        s = self._mm()
        s.on_fill(StrategyFill(side=BUY, price=101, qty=10, fee=0.0))
        s.on_market(snap(mid=101.0, microprice=101.0, imbalance=0.0))
        px_ok = {i.side: i.price for i in s.decide(1) if i.action == NEW}
        s.on_market(snap(mid=101.0, microprice=100.5, imbalance=-0.6))
        px_adv = {i.side: i.price for i in s.decide(2) if i.action == NEW}
        self.assertTrue(s._adverse(snap(mid=101.0, microprice=100.5,
                                        imbalance=-0.6)))
        self.assertLess(px_adv[BUY], px_ok[BUY])  # shifted down
        self.assertGreater(px_adv[SELL] - px_adv[BUY],
                           px_ok[SELL] - px_ok[BUY])  # widened

    def test_no_adverse_when_flat(self):
        s = self._mm()
        self.assertFalse(s._adverse(snap(mid=101.0, microprice=100.5,
                                         imbalance=-0.6)))

    def test_no_adverse_when_book_supports_inventory(self):
        s = self._mm()
        s.on_fill(StrategyFill(side=BUY, price=101, qty=10, fee=0.0))
        # long + book leaning up = not adverse
        self.assertFalse(s._adverse(snap(mid=101.0, microprice=101.5,
                                         imbalance=0.6)))


class TestInventoryTarget(unittest.TestCase):
    def test_reservation_falls_as_inventory_rises_above_target(self):
        px0, _ = mm_quotes(position=0)
        px20, _ = mm_quotes(position=20)
        self.assertLess(px20[BUY], px0[BUY])
        self.assertLess(px20[SELL], px0[SELL])

    def test_inventory_target_honoured(self):
        px_flat, _ = mm_quotes(position=0)
        px_target, _ = mm_quotes(position=10, inventory_target=10)
        self.assertEqual(px_target, px_flat)  # no skew at the target
        px_skewed, _ = mm_quotes(position=10)  # target=0 default: skewed down
        self.assertLess(px_skewed[BUY], px_flat[BUY])

    def test_size_shrink_opt_in(self):
        _, i0 = mm_quotes(position=0, size_shrink=True, order_size=10,
                          max_inventory=50)
        _, i25 = mm_quotes(position=25, size_shrink=True, order_size=10,
                           max_inventory=50)
        _, i40 = mm_quotes(position=40, size_shrink=True, order_size=10,
                           max_inventory=50)
        self.assertEqual([i.qty for i in i0], [10, 10])
        self.assertEqual([i.qty for i in i25], [5, 5])
        self.assertEqual([i.qty for i in i40], [2, 2])

    def test_no_size_shrink_by_default(self):
        _, intents = mm_quotes(position=40, order_size=10, max_inventory=50)
        self.assertEqual([i.qty for i in intents], [10, 10])

    def test_hard_cap_still_one_sided(self):
        px, intents = mm_quotes(position=50, max_inventory=50)
        sides = {i.side for i in intents}
        self.assertEqual(sides, {SELL})
        px, intents = mm_quotes(position=-50, max_inventory=50)
        sides = {i.side for i in intents}
        self.assertEqual(sides, {BUY})


class TestBacktestDepthWiring(unittest.TestCase):
    def test_snapshot_carries_depth(self):
        feed = SyntheticL2Feed(seed=7, sim_seconds=5, events_per_sec=50)
        strat = MultiLevelFlowStrategy(decide_interval_ns=0)
        risk = RiskGateway(RiskLimits(max_order_notional=100_000.0,
                                      max_position=500,
                                      max_orders_per_sec=10_000,
                                      daily_loss_limit=100_000.0))
        bt = Backtest(feed, strat, risk, BacktestConfig(seed=7))
        res = bt.run()
        snap_ = strat._last_snap
        self.assertIsNotNone(snap_)
        self.assertTrue(len(snap_.bid_depth) > 0)
        self.assertTrue(len(snap_.ask_depth) > 0)
        self.assertTrue(all(len(level) == 2 for level in snap_.bid_depth))
        self.assertIn("total_pnl", res.metrics)


if __name__ == "__main__":
    unittest.main()
