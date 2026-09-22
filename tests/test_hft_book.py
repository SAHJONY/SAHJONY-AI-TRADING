"""Tests for hft.book: priority, BBO/depth math, crossed-book rejection."""

import unittest

from hft.book import (
    BUY, SELL, BookOrder, CrossedBookError, L2OrderBook,
)


def _mk(oid, side, price, qty, ts=0, owner="market"):
    return BookOrder(order_id=oid, side=side, price=price, qty=qty,
                     ts_ns=ts, owner=owner)


class TestPriceTimePriority(unittest.TestCase):
    def test_time_priority_within_level(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5, ts=10))
        b.add(_mk(2, BUY, 100, 7, ts=20))
        fills = b.apply_aggressor(SELL, 6)
        # oldest first: order 1 fully (5), then 1 from order 2
        self.assertEqual(fills, [(100, 5, 1), (100, 1, 2)])

    def test_price_priority_across_levels(self):
        b = L2OrderBook()
        b.add(_mk(1, SELL, 102, 5))
        b.add(_mk(2, SELL, 101, 5))
        fills = b.apply_aggressor(BUY, 5)
        self.assertEqual(fills, [(101, 5, 2)])

    def test_bbo_and_depth(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5))
        b.add(_mk(2, BUY, 99, 3))
        b.add(_mk(3, SELL, 102, 4))
        self.assertEqual(b.best_bid(), (100, 5))
        self.assertEqual(b.best_ask(), (102, 4))
        d = b.depth(2)
        self.assertEqual(d["bids"], [(100, 5), (99, 3)])
        self.assertEqual(d["asks"], [(102, 4)])

    def test_cancel(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5))
        self.assertTrue(b.cancel(1))
        self.assertFalse(b.cancel(1))
        self.assertIsNone(b.best_bid())

    def test_replace_loses_queue_position(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5, ts=10))
        b.add(_mk(2, BUY, 100, 5, ts=20))
        b.replace(1, new_qty=5)  # cancel + re-add -> now behind order 2
        fills = b.apply_aggressor(SELL, 5)
        self.assertEqual(fills[0][2], 2)

    def test_replace_restores_on_crossed(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5))
        b.add(_mk(2, SELL, 102, 5))
        with self.assertRaises(CrossedBookError):
            b.replace(1, new_price=103)  # would cross the ask
        self.assertEqual(b.best_bid(), (100, 5))  # original intact


class TestCrossedBookRejection(unittest.TestCase):
    def test_buy_crossing_ask_rejected(self):
        b = L2OrderBook()
        b.add(_mk(1, SELL, 102, 5))
        with self.assertRaises(CrossedBookError):
            b.add(_mk(2, BUY, 102, 1))
        with self.assertRaises(CrossedBookError):
            b.add(_mk(3, BUY, 105, 1))

    def test_sell_crossing_bid_rejected(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5))
        with self.assertRaises(CrossedBookError):
            b.add(_mk(2, SELL, 100, 1))

    def test_invalid_inputs_rejected(self):
        b = L2OrderBook()
        with self.assertRaises(ValueError):
            b.add(_mk(1, 0, 100, 5))
        with self.assertRaises(ValueError):
            b.add(_mk(1, BUY, -5, 5))
        with self.assertRaises(ValueError):
            b.add(_mk(1, BUY, 100, 0))
        b.add(_mk(1, BUY, 100, 5))
        with self.assertRaises(ValueError):
            b.add(_mk(1, BUY, 99, 5))  # duplicate id


class TestBookMath(unittest.TestCase):
    def setUp(self):
        self.b = L2OrderBook()
        self.b.add(_mk(1, BUY, 100, 30))
        self.b.add(_mk(2, BUY, 99, 10))
        self.b.add(_mk(3, SELL, 102, 10))
        self.b.add(_mk(4, SELL, 103, 30))

    def test_midprice_and_spread(self):
        self.assertEqual(self.b.midprice(), 101.0)
        self.assertEqual(self.b.spread_ticks(), 2)

    def test_imbalance(self):
        # bids 40, asks 40 over top 5 -> 0
        self.assertAlmostEqual(self.b.imbalance(5), 0.0)
        # top 1: bids 30 vs asks 10 -> 0.5
        self.assertAlmostEqual(self.b.imbalance(1), 0.5)

    def test_microprice(self):
        # (10*100 + 30*102) / 40 = 101.5
        self.assertAlmostEqual(self.b.microprice(1), 101.5)

    def test_imbalance_none_when_empty(self):
        b = L2OrderBook()
        self.assertIsNone(b.imbalance())
        self.assertIsNone(b.microprice())
        self.assertIsNone(b.midprice())

    def test_set_level_preserves_self_orders(self):
        b = L2OrderBook()
        b.add(_mk(1, BUY, 100, 5, owner="self"))
        b.set_level(BUY, 100, 50)  # feed says 50 total at level
        self.assertEqual(b.best_bid(), (100, 50))  # 45 market + 5 self
        b.set_level(BUY, 100, 2)  # feed drops below our size: we stay
        self.assertEqual(b.best_bid(), (100, 5))
        self.assertEqual(len(b.self_orders()), 1)


if __name__ == "__main__":
    unittest.main()
