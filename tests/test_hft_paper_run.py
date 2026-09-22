"""Tests for hft/paper_run.py — fail-closed behaviors, no network, no keys.

Nothing here touches the network: HTTP is monkeypatched away, and the
"credentials" are obvious dummy values. What we assert:

* missing env keys -> clean abort, and key *values* never appear in the
  error text;
* the paper-URL assertion refuses the live endpoint;
* dry-run mode never calls venue.submit;
* a data-fetch failure raises before any submit can happen;
* the per-order notional cap skips oversize intents without submitting;
* a risk-gateway rejection blocks submission.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from hft import paper_run
from hft.audit import AuditLog
from hft.book import BUY
from hft.matching import OrderResult
from hft.risk import RiskGateway, RiskLimits
from hft.strategies import NEW, OrderIntent
from hft.venue import PAPER_BASE_URL, AlpacaPaperVenue

_SENTINEL_ID = "DUMMY-KEY-ID-VALUE"
_SENTINEL_SECRET = "DUMMY-SECRET-VALUE"


class StubVenue:
    """Records submits; never touches the network."""

    def __init__(self):
        self.submits = []
        self.cancels = []

    def submit(self, order, symbol=""):
        self.submits.append((order, symbol))
        return OrderResult(status="new", leaves_qty=order.qty,
                           reason="stub accepted")

    def cancel(self, client_order_id):
        self.cancels.append(client_order_id)
        return True

    def close(self):
        pass


def _audit():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    tmp.close()
    return AuditLog(tmp.name), tmp.name


def _runner(**kw):
    audit, path = _audit()
    venue = StubVenue()
    risk = RiskGateway(RiskLimits(), tick_size=paper_run.TICK, audit=audit)
    defaults = dict(symbol="SPY", key_id=_SENTINEL_ID, secret=_SENTINEL_SECRET,
                    dry_run=True, audit=audit, venue=venue, risk=risk)
    defaults.update(kw)
    return paper_run.PaperRunner(**defaults), venue, path


def _intent(qty=1, price_ticks=60000):
    return OrderIntent(action=NEW, side=BUY, qty=qty, price=price_ticks,
                       order_type="limit", tag="t", client_order_id="x")


class TestKeyHandling(unittest.TestCase):
    def test_missing_keys_abort_cleanly(self):
        env = {}
        with self.assertRaises(paper_run.PaperRunnerError) as ctx:
            paper_run._read_keys(env)
        msg = str(ctx.exception)
        self.assertIn("APCA_API_KEY_ID", msg)
        self.assertIn("APCA_API_SECRET_KEY", msg)

    def test_one_key_missing_aborts(self):
        with self.assertRaises(paper_run.PaperRunnerError):
            paper_run._read_keys({paper_run.ENV_KEY_ID: _SENTINEL_ID})

    def test_key_values_never_in_error_text(self):
        # The present key's value must not leak into the missing-key error.
        env = {paper_run.ENV_KEY_ID: _SENTINEL_ID}
        with self.assertRaises(paper_run.PaperRunnerError) as ctx:
            paper_run._read_keys(env)
        self.assertNotIn(_SENTINEL_ID, str(ctx.exception))
        self.assertNotIn(_SENTINEL_SECRET, str(ctx.exception))

    def test_keys_returned_when_present(self):
        env = {paper_run.ENV_KEY_ID: _SENTINEL_ID,
               paper_run.ENV_SECRET: _SENTINEL_SECRET}
        self.assertEqual(paper_run._read_keys(env),
                         (_SENTINEL_ID, _SENTINEL_SECRET))


class TestPaperOnly(unittest.TestCase):
    def test_live_url_refused(self):
        with self.assertRaises(paper_run.PaperRunnerError):
            paper_run._assert_paper_url("https://api.alpaca.markets")

    def test_arbitrary_url_refused(self):
        with self.assertRaises(paper_run.PaperRunnerError):
            paper_run._assert_paper_url("https://example.com")

    def test_paper_url_accepted(self):
        paper_run._assert_paper_url(PAPER_BASE_URL)  # must not raise

    def test_venue_constructor_still_refuses_live(self):
        with self.assertRaises(ValueError):
            AlpacaPaperVenue(api_key="k", secret_key="s",
                             base_url="https://api.alpaca.markets")

    def test_new_venue_is_paper(self):
        venue = paper_run._new_venue("k", "s")
        self.assertTrue(venue.paper_mode)
        venue.close()


class TestDryRun(unittest.TestCase):
    def test_dry_run_submits_nothing(self):
        runner, venue, path = _runner(dry_run=True, max_notional=10_000.0)
        ok = runner._submit_intent(_intent(), 60000.0, 0, 1_000_000)
        self.assertFalse(ok)
        self.assertEqual(venue.submits, [])
        with open(path) as fh:
            events = [json.loads(line)["event"] for line in fh]
        self.assertIn("order_intent", events)
        self.assertNotIn("order_submitted", events)
        runner.audit.close()
        os.unlink(path)

    def test_dry_run_counts_intent_so_loop_terminates(self):        # Regression: dry-run intents must advance orders_submitted, or the
        # trade loop (which exits on orders_submitted >= max_orders) never
        # stops in dry-run mode.
        runner, venue, path = _runner(dry_run=True, max_notional=10_000.0,
                                      max_orders=2)
        runner._submit_intent(_intent(), 60000.0, 0, 1_000_000)
        runner._submit_intent(_intent(), 60000.0, 0, 2_000_000)
        self.assertEqual(runner.orders_submitted, 2)
        self.assertEqual(venue.submits, [])
        with open(path) as fh:
            intents = [json.loads(line) for line in fh
                       if json.loads(line)["event"] == "order_intent"]
        self.assertTrue(all(e["dry_run"] for e in intents))
        runner.audit.close()
        os.unlink(path)

    def test_max_iterations_stops_loop_without_signals(self):
        # The loop must also terminate after max_iterations polls even when
        # the strategy never fires (quiet market), or CI dry-runs hang.
        runner, venue, path = _runner(dry_run=True, max_orders=100,
                                      max_iterations=2, interval=0.01)
        runner._trade_iteration = lambda: None  # no signal, no intents
        rc = runner.run_trade()
        self.assertEqual(rc, 0)
        self.assertEqual(runner.orders_submitted, 0)
        self.assertEqual(venue.submits, [])
        with open(path) as fh:
            events = [json.loads(line) for line in fh]
        stops = [e for e in events if e["event"] == "run_stop"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["reason"], "max_iterations_reached")
        self.assertEqual(stops[0]["iterations"], 2)
        runner.audit.close()
        os.unlink(path)

    def test_live_mode_submits_after_risk_approval(self):
        runner, venue, path = _runner(dry_run=False, max_notional=10_000.0)
        ok = runner._submit_intent(_intent(), 60000.0, 0, 1_000_000)
        self.assertTrue(ok)
        self.assertEqual(len(venue.submits), 1)
        order, symbol = venue.submits[0]
        self.assertEqual(symbol, "SPY")
        self.assertEqual(order.qty, 1)
        runner.audit.close()
        os.unlink(path)


class TestFailClosed(unittest.TestCase):
    def test_data_fetch_failure_places_no_orders(self):
        runner, venue, path = _runner(dry_run=False)
        with mock.patch.object(paper_run, "fetch_bars",
                               side_effect=paper_run.PaperRunnerError("down")):
            with self.assertRaises(paper_run.PaperRunnerError):
                runner._trade_iteration()
        self.assertEqual(venue.submits, [])
        runner.audit.close()
        os.unlink(path)

    def test_notional_cap_skips_oversize_intent(self):
        runner, venue, path = _runner(dry_run=False, max_notional=25.0)
        # 1 share @ $600 > $25 cap -> skipped, never submitted
        ok = runner._submit_intent(_intent(qty=1, price_ticks=60000),
                                   60000.0, 0, 1_000_000)
        self.assertFalse(ok)
        self.assertEqual(venue.submits, [])
        with open(path) as fh:
            events = [json.loads(line)["event"] for line in fh]
        self.assertIn("order_skipped", events)
        runner.audit.close()
        os.unlink(path)

    def test_risk_rejection_blocks_submit(self):
        audit, path = _audit()
        venue = StubVenue()
        # absurdly small per-order notional -> gateway rejects
        risk = RiskGateway(RiskLimits(max_order_notional=0.01),
                           tick_size=paper_run.TICK, audit=audit)
        runner = paper_run.PaperRunner(
            symbol="SPY", key_id=_SENTINEL_ID, secret=_SENTINEL_SECRET,
            dry_run=False, max_notional=10_000.0, audit=audit,
            venue=venue, risk=risk)
        ok = runner._submit_intent(_intent(), 60000.0, 0, 1_000_000)
        self.assertFalse(ok)
        self.assertEqual(venue.submits, [])
        with open(path) as fh:
            events = [json.loads(line)["event"] for line in fh]
        self.assertIn("order_blocked", events)
        self.assertIn("risk_decision", events)
        audit.close()
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
