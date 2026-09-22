"""Tests for hft.matching: order types, priority, queue-aware fills."""

import unittest

from hft.book import BUY, SELL, BookOrder, L2OrderBook
from hft.matching import (
    FOK, IOC, LIMIT, MARKET, POST_ONLY, IncomingOrder, MatchingEngine,
)


def seed_book():
    b = L2OrderBook()
    seq = [1]
    def add(side, price, qty, owner="market", ts=0):
        o = BookOrder(order_id=seq[0], side=side, price=price, qty=qty,
                      ts_ns=ts, owner=owner)
        seq[0] += 1
        b.add(o)
        return o.order_id
    add(SELL, 102, 10, ts=1)
    add(SELL, 103, 10, ts=2)
    add(BUY, 100, 10, ts=3)
    add(BUY, 99, 10, ts=4)
    return b


def incoming(cid, side, qty, otype=LIMIT, price=None, owner="x", ts=100):
    return IncomingOrder(client_order_id=cid, owner=owner, side=side,
                         qty=qty, order_type=otype, price=price, ts_ns=ts)


class TestLimitAndMarket(unittest.TestCase):
    def test_market_sweeps_price_time(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 15, MARKET))
        self.assertEqual(r.status, "filled")
        self.assertEqual([(f.price, f.qty) for f in r.fills],
                         [(102, 10), (103, 5)])
        self.assertTrue(all(f.aggressor for f in r.fills))

    def test_market_partial_when_thin(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 100, MARKET))
        self.assertEqual(r.status, "expired")
        self.assertEqual(sum(f.qty for f in r.fills), 20)

    def test_limit_rests_when_not_marketable(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 5, LIMIT, price=101))
        self.assertEqual(r.status, "new")
        self.assertEqual(r.leaves_qty, 5)
        self.assertEqual(e.book.best_bid(), (101, 5))

    def test_limit_partial_fill_rests_remainder(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 15, LIMIT, price=102))
        self.assertEqual(r.status, "partial")
        self.assertEqual(sum(f.qty for f in r.fills), 10)
        self.assertEqual(r.leaves_qty, 5)
        # remainder rests at its limit price without crossing
        self.assertEqual(e.book.best_bid(), (102, 5))

    def test_invalid_orders_rejected_fail_closed(self):
        e = MatchingEngine(seed_book())
        self.assertEqual(e.submit(incoming("a", BUY, 0, MARKET)).status, "rejected")
        self.assertEqual(e.submit(incoming("a", BUY, -3, MARKET)).status, "rejected")
        self.assertEqual(e.submit(incoming("a", BUY, 5, LIMIT, price=-1)).status, "rejected")
        self.assertEqual(e.submit(incoming("a", BUY, 5, MARKET, price=100)).status, "rejected")
        self.assertEqual(e.submit(incoming("a", 0, 5, MARKET)).status, "rejected")
        self.assertEqual(e.submit(incoming("", BUY, 5, MARKET)).status, "rejected")
        self.assertEqual(e.submit(incoming("a", BUY, 5, "bogus")).status, "rejected")


class TestIOC_FOK_PostOnly(unittest.TestCase):
    def test_ioc_fills_and_cancels_remainder(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 15, IOC, price=102))
        self.assertEqual(r.status, "expired")
        self.assertEqual(sum(f.qty for f in r.fills), 10)
        self.assertEqual(r.leaves_qty, 0)
        self.assertEqual(e.book.best_bid(), (100, 10))  # nothing rested

    def test_ioc_no_fill(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 5, IOC, price=101))
        self.assertEqual(r.status, "expired")
        self.assertEqual(r.fills, [])

    def test_fok_all_or_nothing(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 25, FOK, price=103))
        self.assertEqual(r.status, "rejected")  # only 20 available
        r2 = e.submit(incoming("b", BUY, 20, FOK, price=103))
        self.assertEqual(r2.status, "filled")
        self.assertEqual(sum(f.qty for f in r2.fills), 20)

    def test_post_only_rejects_marketable(self):
        e = MatchingEngine(seed_book())
        r = e.submit(incoming("a", BUY, 5, POST_ONLY, price=102))
        self.assertEqual(r.status, "rejected")
        r2 = e.submit(incoming("b", BUY, 5, POST_ONLY, price=101))
        self.assertEqual(r2.status, "new")

    def test_duplicate_client_order_id(self):
        e = MatchingEngine(seed_book())
        r1 = e.submit(incoming("a", BUY, 5, LIMIT, price=101, owner="self"))
        self.assertEqual(r1.status, "new")
        r2 = e.submit(incoming("a", BUY, 5, LIMIT, price=101, owner="self"))
        self.assertEqual(r2.status, "rejected")


class TestSelfTradePrevention(unittest.TestCase):
    def test_incoming_self_order_blocked(self):
        b = seed_book()
        e = MatchingEngine(b)
        # rest our own ask
        r = e.submit(incoming("s1", SELL, 5, LIMIT, price=104, owner="self"))
        self.assertEqual(r.status, "new")
        # our buy sweeping through it is rejected, not self-matched
        r2 = e.submit(incoming("s2", BUY, 10, MARKET, owner="self"))
        self.assertEqual(r2.status, "rejected")
        self.assertIn("self-trade", r2.reason)

    def test_market_self_trade_blocked(self):
        b = L2OrderBook()
        e = MatchingEngine(b)
        e.submit(incoming("s1", SELL, 5, LIMIT, price=110, owner="self"))
        r = e.submit(incoming("s2", BUY, 3, MARKET, owner="self"))
        self.assertEqual(r.status, "rejected")


class TestQueueAwareFills(unittest.TestCase):
    def test_queue_ahead_blocks_fill(self):
        b = L2OrderBook()
        e = MatchingEngine(b)
        # market liquidity first at the ask, then our order behind it in
        # time priority (inserted directly; a new sell at the touch would
        # correctly match instead of resting, so we seed priority by hand)
        b.add(BookOrder(order_id=1, side=SELL, price=102, qty=90, ts_ns=1))
        b.add(BookOrder(order_id=2, side=SELL, price=102, qty=10, ts_ns=2,
                        owner="self"))
        # external buy print of 50: consumes 50 of the 90 ahead of us
        fills = e.apply_external_trade(BUY, 50)
        self.assertEqual(fills, [])  # we were behind the queue
        # another print of 50: 40 remaining ahead, 10 reaches us
        fills = e.apply_external_trade(BUY, 50)
        self.assertEqual(sum(f.qty for f in fills), 10)
        self.assertTrue(all(not f.aggressor for f in fills))

    def test_full_queue_consumption_fills_us(self):
        b = L2OrderBook()
        e = MatchingEngine(b)
        r = e.submit(incoming("s1", SELL, 10, LIMIT, price=102, owner="self"))
        self.assertEqual(r.status, "new")
        fills = e.apply_external_trade(BUY, 10)
        self.assertEqual(sum(f.qty for f in fills), 10)


if __name__ == "__main__":
    unittest.main()
