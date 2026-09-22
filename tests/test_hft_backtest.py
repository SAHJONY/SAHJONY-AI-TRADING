"""Tests for hft.backtest + latency + feed determinism (offline)."""

import unittest

from hft.backtest import Backtest, BacktestConfig
from hft.book import BUY, SELL
from hft.feed import LEVEL, TRADE, FeedEvent, SyntheticL2Feed
from hft.latency import LatencyConfig, LatencyModel, TickToTradeTracker
from hft.matching import IncomingOrder
from hft.risk import RiskGateway, RiskLimits
from hft.strategies import AvellanedaStoikovMarketMaker, MicrostructureSignalStrategy
from hft.venue import AlpacaPaperVenue, LiveVenue, PaperVenue


def tiny_run(seed=7, **kw):
    feed = SyntheticL2Feed(seed=seed, sim_seconds=20, events_per_sec=200,
                           **kw)
    strat = AvellanedaStoikovMarketMaker()
    risk = RiskGateway(RiskLimits(max_order_notional=100_000.0,
                                  max_position=500,
                                  max_orders_per_sec=10_000,
                                  daily_loss_limit=100_000.0))
    latency = LatencyModel(LatencyConfig(one_way_ns=250_000,
                                         jitter_sigma=0.0, seed=seed))
    bt = Backtest(feed, strat, risk, BacktestConfig(seed=seed), latency)
    return bt.run()


class TestDeterminism(unittest.TestCase):
    def test_same_seed_identical_pnl(self):
        r1 = tiny_run(seed=7)
        r2 = tiny_run(seed=7)
        self.assertEqual(r1.metrics["total_pnl"], r2.metrics["total_pnl"])
        self.assertEqual(r1.metrics["fills"], r2.metrics["fills"])
        self.assertEqual(len(r1.fills), len(r2.fills))
        for f1, f2 in zip(r1.fills, r2.fills):
            self.assertEqual(f1, f2)

    def test_different_seed_usually_differs(self):
        r1 = tiny_run(seed=7)
        r2 = tiny_run(seed=8)
        # feeds differ -> at least the event-level path differs
        self.assertNotEqual(r1.metrics["events"], 0)
        self.assertTrue(
            r1.metrics["total_pnl"] != r2.metrics["total_pnl"]
            or r1.metrics["fills"] != r2.metrics["fills"])

    def test_feed_deterministic(self):
        f1 = list(SyntheticL2Feed(seed=3, sim_seconds=2, events_per_sec=50))
        f2 = list(SyntheticL2Feed(seed=3, sim_seconds=2, events_per_sec=50))
        self.assertEqual(f1, f2)
        self.assertEqual(len(f1), 100)
        # timestamps strictly increasing, integer ns
        tss = [e.ts_ns for e in f1]
        self.assertTrue(all(isinstance(t, int) for t in tss))
        self.assertTrue(all(b > a for a, b in zip(tss, tss[1:])))

    def test_feed_has_trades_and_levels(self):
        evs = list(SyntheticL2Feed(seed=3, sim_seconds=5, events_per_sec=200))
        kinds = {e.kind for e in evs}
        self.assertEqual(kinds, {LEVEL, TRADE})


class TestBacktestMetrics(unittest.TestCase):
    def test_metrics_keys_present(self):
        r = tiny_run(seed=7)
        m = r.metrics
        for key in ("total_pnl", "sharpe_per_sample", "max_drawdown",
                    "fill_rate", "markout_1s_ticks", "markout_10s_ticks",
                    "avg_abs_inventory", "orders_per_sec", "fees_paid",
                    "tick_to_trade_mean_us"):
            self.assertIn(key, m, key)

    def test_sanity_bounds(self):
        r = tiny_run(seed=7)
        m = r.metrics
        self.assertGreaterEqual(m["fill_rate"], 0.0)
        self.assertLessEqual(m["fill_rate"], 1.0)
        self.assertGreaterEqual(m["max_drawdown"], 0.0)
        self.assertGreaterEqual(m["orders_submitted"], 0)
        self.assertGreater(m["events"], 0)
        self.assertGreaterEqual(m["fees_paid"], 0.0)

    def test_micro_strategy_runs(self):
        feed = SyntheticL2Feed(seed=11, sim_seconds=20, events_per_sec=200)
        strat = MicrostructureSignalStrategy()
        risk = RiskGateway(RiskLimits(max_order_notional=100_000.0,
                                      max_position=500,
                                      max_orders_per_sec=10_000,
                                      daily_loss_limit=100_000.0))
        bt = Backtest(feed, strat, risk, BacktestConfig(seed=11),
                      LatencyModel(LatencyConfig(seed=11)))
        r = bt.run()
        self.assertIn("total_pnl", r.metrics)
        self.assertTrue(r.notes)  # honesty notes attached


class TestLatency(unittest.TestCase):
    def test_deterministic_delay(self):
        m = LatencyModel(LatencyConfig(one_way_ns=250_000, jitter_sigma=0.0,
                                       seed=1))
        self.assertEqual(m.apply(1_000), 251_000)

    def test_jitter_seeded(self):
        m1 = LatencyModel(LatencyConfig(one_way_ns=1000, jitter_sigma=0.5,
                                        seed=42))
        m2 = LatencyModel(LatencyConfig(one_way_ns=1000, jitter_sigma=0.5,
                                        seed=42))
        self.assertEqual([m1.apply(0) for _ in range(5)],
                         [m2.apply(0) for _ in range(5)])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            LatencyConfig(one_way_ns=-1)
        m = LatencyModel()
        with self.assertRaises(ValueError):
            m.apply(-5)

    def test_tick_to_trade_tracker(self):
        t = TickToTradeTracker()
        t.record(1000, 1500)
        t.record(2000, 2600)
        s = t.stats()
        self.assertEqual(s["count"], 2)
        self.assertAlmostEqual(s["mean_us"], 0.55)
        with self.assertRaises(ValueError):
            t.record(5000, 4000)


class TestVenues(unittest.TestCase):
    def test_live_venue_stub(self):
        with self.assertRaises(NotImplementedError):
            LiveVenue()

    def test_paper_venue_roundtrip(self):
        v = PaperVenue()
        v.book.set_level(SELL, 105, 10)
        r = v.submit(IncomingOrder(client_order_id="x", owner="t",
                                   side=BUY, qty=4, order_type="market",
                                   ts_ns=0))
        self.assertEqual(r.status, "filled")

    def test_alpaca_paper_rejects_live(self):
        with self.assertRaises(ValueError):
            AlpacaPaperVenue(api_key="k", secret_key="s",
                             base_url="https://api.alpaca.markets")

    def test_alpaca_paper_requires_keys(self):
        with self.assertRaises(ValueError):
            AlpacaPaperVenue()

    def test_alpaca_paper_constructs_offline(self):
        v = AlpacaPaperVenue(api_key="PK_TEST", secret_key="SK_TEST")
        self.assertEqual(v._base_url, "https://paper-api.alpaca.markets")

    def test_alpaca_submit_mapping_offline(self):
        v = AlpacaPaperVenue(api_key="PK_TEST", secret_key="SK_TEST")
        captured = {}

        def fake_request(method, path, body=None):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = body
            return {"id": "oid-1", "status": "accepted"}

        v._request = fake_request
        r = v.submit(IncomingOrder(client_order_id="c1", owner="t", side=BUY,
                                   qty=10, order_type="limit", price=15000,
                                   ts_ns=0),
                     symbol="SPY")
        self.assertEqual(captured["path"], "/v2/orders")
        self.assertEqual(captured["body"]["symbol"], "SPY")
        self.assertEqual(captured["body"]["limit_price"], 150.00)
        self.assertEqual(r.status, "new")

    def test_alpaca_submit_needs_symbol(self):
        v = AlpacaPaperVenue(api_key="PK_TEST", secret_key="SK_TEST")
        r = v.submit(IncomingOrder(client_order_id="c1", owner="t", side=BUY,
                                   qty=10, order_type="market", ts_ns=0))
        self.assertEqual(r.status, "rejected")


if __name__ == "__main__":
    unittest.main()
