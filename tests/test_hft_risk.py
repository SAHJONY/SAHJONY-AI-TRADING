"""Tests for hft.risk: fail-closed checks, limits, kill switch."""

import unittest

from hft.book import BUY, SELL
from hft.risk import RiskGateway, RiskLimits


def gw(**kw):
    limits = RiskLimits(**kw)
    return RiskGateway(limits)


class TestFailClosedInputs(unittest.TestCase):
    def test_bad_qty_rejected(self):
        g = gw()
        for bad in (0, -5):
            d = g.check_new_order("a", BUY, bad, 100, 0, 100.0, 0)
            self.assertFalse(d.approved, bad)

    def test_bad_price_rejected(self):
        g = gw()
        d = g.check_new_order("a", BUY, 5, -3, 0, 100.0, 0)
        self.assertFalse(d.approved)
        d = g.check_new_order("a", BUY, 5, 0, 0, 100.0, 0)
        self.assertFalse(d.approved)

    def test_bad_side_rejected(self):
        g = gw()
        d = g.check_new_order("a", 0, 5, 100, 0, 100.0, 0)
        self.assertFalse(d.approved)

    def test_empty_client_order_id_rejected(self):
        g = gw()
        d = g.check_new_order("", BUY, 5, 100, 0, 100.0, 0)
        self.assertFalse(d.approved)

    def test_non_finite_ref_price_rejected(self):
        g = gw()
        for bad in (float("nan"), float("inf"), -1.0):
            d = g.check_new_order("a", BUY, 5, None, 0, bad, 0)
            self.assertFalse(d.approved, bad)


class TestLimits(unittest.TestCase):
    def test_max_order_notional(self):
        g = gw(max_order_notional=1_000.0)
        # 200 ticks * $0.01 * 1000 = $2000 > $1000
        d = g.check_new_order("a", BUY, 1000, 200, 0, 200.0, 0)
        self.assertFalse(d.approved)
        d = g.check_new_order("b", BUY, 100, 200, 0, 200.0, 0)  # $200 ok
        self.assertTrue(d.approved)

    def test_max_position(self):
        g = gw(max_position=50)
        d = g.check_new_order("a", BUY, 60, 100, 0, 100.0, 0)
        self.assertFalse(d.approved)
        d = g.check_new_order("b", SELL, 60, 100, 0, 100.0, 0)
        self.assertFalse(d.approved)
        d = g.check_new_order("c", BUY, 50, 100, 0, 100.0, 0)
        self.assertTrue(d.approved)

    def test_rate_limit(self):
        g = gw(max_orders_per_sec=3)
        for i in range(3):
            d = g.check_new_order(f"o{i}", BUY, 1, 100, 0, 100.0, i * 100)
            self.assertTrue(d.approved)
        d = g.check_new_order("o3", BUY, 1, 100, 0, 100.0, 300)
        self.assertFalse(d.approved)
        self.assertIn("rate", d.reason)
        # window slides: 1.5s later the first orders fall out
        d = g.check_new_order("o4", BUY, 1, 100, 0, 100.0, 1_500_000_100)
        self.assertTrue(d.approved)

    def test_duplicate_order_id(self):
        g = gw()
        d = g.check_new_order("a", BUY, 1, 100, 0, 100.0, 0)
        self.assertTrue(d.approved)
        d = g.check_new_order("a", BUY, 1, 100, 0, 100.0, 1)
        self.assertFalse(d.approved)

    def test_cancel_always_passes(self):
        g = gw()
        g.trip_kill_switch("test")
        self.assertTrue(g.check_cancel("anything").approved)


class TestKillSwitch(unittest.TestCase):
    def test_tripped_blocks_everything(self):
        g = gw()
        g.trip_kill_switch("manual test")
        d = g.check_new_order("a", BUY, 1, 100, 0, 100.0, 0)
        self.assertFalse(d.approved)
        self.assertIn("kill switch", d.reason)

    def test_daily_loss_limit_trips(self):
        g = gw(daily_loss_limit=100.0)
        g.mark(10_000.0)  # sets start equity
        g.mark(9_950.0)   # -$50: ok
        self.assertFalse(g.kill_switch)
        g.mark(9_899.0)   # -$101: breach
        self.assertTrue(g.kill_switch)
        d = g.check_new_order("a", BUY, 1, 100, 0, 100.0, 0)
        self.assertFalse(d.approved)

    def test_reset_restores(self):
        g = gw()
        g.trip_kill_switch("x")
        g.reset_kill_switch()
        d = g.check_new_order("a", BUY, 1, 100, 0, 100.0, 0)
        self.assertTrue(d.approved)


if __name__ == "__main__":
    unittest.main()
