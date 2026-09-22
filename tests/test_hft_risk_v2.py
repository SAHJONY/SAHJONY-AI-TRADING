"""Tests for HFT Lab v2 risk + security upgrades (hft/risk.py v2).

Covers: per-symbol rate limit, per-minute notional limit, max open
orders, the order-to-trade ratio guard, fat-finger price sanity, the
kill() cancel-via-return upgrade, audit logging + secret redaction, and
the AlpacaPaperVenue paper-mode hardening.
"""

import json
import os
import tempfile
import unittest

from hft.audit import AuditLog
from hft.book import BUY
from hft.risk import RiskGateway, RiskLimits
from hft.venue import (
    PAPER_BASE_URL,
    PAPER_ONLY,
    AlpacaPaperVenue,
    _LIVE_BASE_URL,
)


def gw(**kw):
    limits = RiskLimits(**kw)
    return RiskGateway(limits)


def order(g, oid, ts_ns=0, symbol="", qty=1, price=100, ref=100.0):
    return g.check_new_order(
        client_order_id=oid,
        side=BUY,
        qty=qty,
        price_ticks=price,
        position=0,
        ref_price_ticks=ref,
        ts_ns=ts_ns,
        symbol=symbol,
    )


class TestRiskLimitsV2Defaults(unittest.TestCase):
    def test_new_fields_sane_defaults(self):
        lim = RiskLimits()
        self.assertEqual(lim.max_orders_per_sec_per_symbol, 20)
        self.assertEqual(lim.max_notional_per_minute, 100_000.0)
        self.assertEqual(lim.max_open_orders, 50)
        self.assertEqual(lim.max_order_to_trade_ratio, 50.0)
        self.assertEqual(lim.min_fills_before_otr, 10)
        self.assertEqual(lim.max_price_deviation_bps, 500.0)

    def test_old_fields_unchanged(self):
        lim = RiskLimits()
        self.assertEqual(lim.max_order_notional, 25_000.0)
        self.assertEqual(lim.max_position, 200)
        self.assertEqual(lim.max_orders_per_sec, 100)
        self.assertEqual(lim.daily_loss_limit, 1_000.0)
        self.assertTrue(lim.allow_shorts)


class TestPerSymbolRateLimit(unittest.TestCase):
    def test_per_symbol_limit_enforced(self):
        g = gw(max_orders_per_sec=1000, max_orders_per_sec_per_symbol=3)
        for i in range(3):
            d = order(g, f"s{i}", ts_ns=i, symbol="SPY")
            self.assertTrue(d.approved, i)
        d = order(g, "s3", ts_ns=3, symbol="SPY")
        self.assertFalse(d.approved)
        self.assertIn("per-symbol", d.reason)

    def test_per_symbol_independent_buckets(self):
        g = gw(max_orders_per_sec=1000, max_orders_per_sec_per_symbol=1)
        self.assertTrue(order(g, "a", symbol="SPY").approved)
        self.assertTrue(order(g, "b", symbol="QQQ").approved)
        self.assertFalse(order(g, "c", symbol="SPY").approved)

    def test_empty_symbol_skips_per_symbol_check(self):
        # Global rate limit still applies (set high here), but with an
        # empty symbol the per-symbol bucket must not reject anything.
        g = gw(max_orders_per_sec=1000, max_orders_per_sec_per_symbol=1)
        for i in range(5):
            d = order(g, f"e{i}", ts_ns=i, symbol="")
            self.assertTrue(d.approved, i)

    def test_window_slides(self):
        g = gw(max_orders_per_sec=1000, max_orders_per_sec_per_symbol=1)
        self.assertTrue(order(g, "a", ts_ns=0, symbol="SPY").approved)
        self.assertFalse(order(g, "b", ts_ns=1, symbol="SPY").approved)
        # one full second later the bucket is empty again
        self.assertTrue(order(g, "c", ts_ns=1_000_000_001, symbol="SPY").approved)

    def test_non_string_symbol_rejected_fail_closed(self):
        g = gw()
        d = order(g, "x", symbol=123)  # type: ignore[arg-type]
        self.assertFalse(d.approved)


class TestPerMinuteNotional(unittest.TestCase):
    def test_reject_when_minute_sum_exceeded(self):
        g = RiskGateway(RiskLimits(max_notional_per_minute=100.0), tick_size=1.0)
        d1 = g.check_new_order("m1", BUY, 6, 10, 0, 10.0, 0)  # $60
        self.assertTrue(d1.approved)
        d2 = g.check_new_order("m2", BUY, 6, 10, 0, 10.0, 0)  # $60 -> $120 > $100
        self.assertFalse(d2.approved)
        self.assertIn("per-minute", d2.reason)

    def test_accept_when_under_limit(self):
        g = RiskGateway(RiskLimits(max_notional_per_minute=100.0), tick_size=1.0)
        d = g.check_new_order("m1", BUY, 6, 10, 0, 10.0, 0)  # $60 < $100
        self.assertTrue(d.approved)

    def test_window_prunes_after_60s(self):
        g = RiskGateway(RiskLimits(max_notional_per_minute=100.0), tick_size=1.0)
        d1 = g.check_new_order("m1", BUY, 6, 10, 0, 10.0, 0)
        self.assertTrue(d1.approved)
        d2 = g.check_new_order("m2", BUY, 6, 10, 0, 10.0, 61 * 1_000_000_000)
        self.assertTrue(d2.approved)  # the $60 from 61s ago aged out


class TestMaxOpenOrders(unittest.TestCase):
    def test_reject_at_limit(self):
        g = gw(max_open_orders=2)
        self.assertTrue(order(g, "o1").approved)
        self.assertTrue(order(g, "o2").approved)
        self.assertEqual(g.open_order_count(), 2)
        d = order(g, "o3")
        self.assertFalse(d.approved)
        self.assertIn("open orders", d.reason)

    def test_note_order_closed_frees_slot(self):
        g = gw(max_open_orders=2)
        order(g, "o1")
        order(g, "o2")
        self.assertFalse(order(g, "o3").approved)
        g.note_order_closed("o1")
        self.assertEqual(g.open_order_count(), 1)
        self.assertTrue(order(g, "o4").approved)

    def test_note_order_closed_unknown_id_is_safe(self):
        g = gw(max_open_orders=1)
        g.note_order_closed("never-seen")  # must not raise
        self.assertEqual(g.open_order_count(), 0)


class TestOrderToTradeRatio(unittest.TestCase):
    def test_inactive_until_enough_fills(self):
        # min_fills_before_otr=2: three orders with zero fills are fine,
        # one fill still leaves the guard inactive.
        g = gw(max_order_to_trade_ratio=2.0, min_fills_before_otr=2)
        for i in range(3):
            self.assertTrue(order(g, f"z{i}", ts_ns=i).approved)
        g.note_fill(3)
        self.assertTrue(order(g, "z3", ts_ns=4).approved)

    def test_reject_when_ratio_exceeded(self):
        g = gw(max_order_to_trade_ratio=2.0, min_fills_before_otr=2)
        self.assertTrue(order(g, "z0", ts_ns=0).approved)
        self.assertTrue(order(g, "z1", ts_ns=1).approved)
        self.assertTrue(order(g, "z2", ts_ns=2).approved)
        g.note_fill(3)
        g.note_fill(4)
        # ratio including this order would be exactly 2.0 -> still ok
        self.assertTrue(order(g, "z3", ts_ns=5).approved)
        # (4 approved + 1 under review) / 2 fills = 2.5 > 2.0 -> rejected
        d = order(g, "z4", ts_ns=6)
        self.assertFalse(d.approved)
        self.assertIn("order-to-trade", d.reason)

    def test_note_fill_rejects_bad_timestamp(self):
        g = gw()
        with self.assertRaises(ValueError):
            g.note_fill(-1)
        with self.assertRaises(ValueError):
            g.note_fill("x")  # type: ignore[arg-type]


class TestFatFinger(unittest.TestCase):
    def _g(self):
        return gw(max_price_deviation_bps=500.0)  # 5%

    def test_just_inside_boundary_approved(self):
        g = self._g()
        self.assertTrue(order(g, "f1", price=10499, ref=10000.0).approved)  # +4.99%
        self.assertTrue(order(g, "f2", price=9501, ref=10000.0).approved)   # -4.99%

    def test_exactly_at_boundary_approved(self):
        g = self._g()
        self.assertTrue(order(g, "f1", price=10500, ref=10000.0).approved)  # exactly 5%
        self.assertTrue(order(g, "f2", price=9500, ref=10000.0).approved)

    def test_just_outside_boundary_rejected(self):
        g = self._g()
        d = order(g, "f1", price=10501, ref=10000.0)  # +5.01%
        self.assertFalse(d.approved)
        self.assertIn("fat-finger", d.reason)
        d = order(g, "f2", price=9499, ref=10000.0)  # -5.01%
        self.assertFalse(d.approved)

    def test_market_order_skips_check(self):
        g = self._g()
        # A market order (price None) is not subject to the fat-finger
        # check regardless of where the reference sits.
        d = order(g, "mkt", price=None, ref=10000.0)
        self.assertTrue(d.approved)


class TestKillUpgrade(unittest.TestCase):
    def test_kill_returns_open_ids_and_blocks_new_orders(self):
        g = gw()
        order(g, "k1")
        order(g, "k2")
        g.note_order_closed("k1")
        order(g, "k3")
        open_ids = g.kill("test reason")
        self.assertEqual(sorted(open_ids), ["k2", "k3"])
        self.assertTrue(g.kill_switch)
        self.assertEqual(g.kill_reason, "test reason")
        d = order(g, "k4")
        self.assertFalse(d.approved)
        self.assertIn("kill switch", d.reason)

    def test_kill_with_no_open_orders_returns_empty(self):
        g = gw()
        self.assertEqual(g.kill("nothing open"), [])
        self.assertTrue(g.kill_switch)

    def test_legacy_trip_and_reset_still_work(self):
        g = gw()
        g.trip_kill_switch("manual")
        self.assertFalse(order(g, "a").approved)
        g.reset_kill_switch()
        self.assertTrue(order(g, "b").approved)

    def test_kill_is_cancel_via_return_only(self):
        # The gateway itself must not mutate the open set on kill — the
        # driver does the cancels and reports them via note_order_closed.
        g = gw()
        order(g, "k1")
        g.kill("r")
        self.assertEqual(g.open_order_count(), 1)
        g.note_order_closed("k1")
        self.assertEqual(g.open_order_count(), 0)


class TestAuditLog(unittest.TestCase):
    def _tmp(self):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def test_decisions_logged_with_fields(self):
        path = self._tmp()
        audit = AuditLog(path)
        g = RiskGateway(audit=audit)
        order(g, "ok1")
        g.check_new_order("bad1", BUY, 0, 100, 0, 100.0, 0)  # rejected: bad qty
        audit.close()
        with open(path, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIn("ts", line)
            self.assertEqual(line["event"], "risk_decision")
            self.assertIn("client_order_id", line)
            self.assertIn("approved", line)
            self.assertIn("reason", line)
        by_id = {line["client_order_id"]: line for line in lines}
        self.assertTrue(by_id["ok1"]["approved"])
        self.assertEqual(by_id["ok1"]["reason"], "approved")
        self.assertFalse(by_id["bad1"]["approved"])

    def test_lines_are_appended(self):
        path = self._tmp()
        audit = AuditLog(path)
        g = RiskGateway(audit=audit)
        order(g, "a1")
        audit.close()
        with open(path, encoding="utf-8") as fh:
            first = fh.read()
        audit2 = AuditLog(path)  # reopen: must append, never truncate
        audit2.log("heartbeat", {"alive": True})
        audit2.close()
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith(first))
        self.assertIn("heartbeat", text)

    def test_secret_keys_redacted(self):
        path = self._tmp()
        audit = AuditLog(path)
        audit.log("custom", {
            "api_secret": "SHOULD-NOT-APPEAR",
            "authToken": "SHOULD-NOT-APPEAR",
            "encryption_key": "SHOULD-NOT-APPEAR",
            "password_hash": "SHOULD-NOT-APPEAR",
            "note": "hello",
        })
        audit.close()
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        line = json.loads(raw.strip())
        self.assertEqual(line["api_secret"], "[REDACTED]")
        self.assertEqual(line["authToken"], "[REDACTED]")
        self.assertEqual(line["encryption_key"], "[REDACTED]")
        self.assertEqual(line["password_hash"], "[REDACTED]")
        self.assertEqual(line["note"], "hello")
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn("SHOULD-NOT-APPEAR", fh.read())

    def test_no_audit_means_no_behavior_change(self):
        g = gw()  # audit=None
        self.assertTrue(order(g, "plain").approved)


class TestVenuePaperHardening(unittest.TestCase):
    def test_paper_only_constant(self):
        self.assertTrue(PAPER_ONLY)

    def test_paper_mode_property(self):
        v = AlpacaPaperVenue(api_key="K", secret_key="S")
        self.assertTrue(v.paper_mode)

    def test_live_url_still_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            AlpacaPaperVenue(api_key="K", secret_key="S", base_url=_LIVE_BASE_URL)

    def test_request_asserts_paper_endpoint(self):
        v = AlpacaPaperVenue(api_key="K", secret_key="S")
        self.assertEqual(v._base_url, PAPER_BASE_URL)
        # Tamper with the URL after construction: _request must refuse
        # before any network activity (the assert runs first).
        v._base_url = _LIVE_BASE_URL
        with self.assertRaises(AssertionError) as ctx:
            v._request("GET", "/v2/account")
        self.assertIn("refusing non-paper endpoint", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
