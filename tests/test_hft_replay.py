"""Tests for the HFT Lab v2 trade-print replay feed (hft/replay.py).

Uses a small slice (first 2000 trades) of the real fixture for speed.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from hft.book import BUY, SELL
from hft.feed import LEVEL, TRADE
from hft.replay import QTY_PER_BTC, ReplayFeed

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(REPO_ROOT, "hft", "data", "btcusd-trades.jsonl")
SLICE_N = 2000


def make_slice(n=SLICE_N):
    """Write the first n fixture lines to a temp file; return its path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as out, open(FIXTURE) as src:
        for i, line in enumerate(src):
            if i >= n:
                break
            out.write(line)
    return path


class TestReplayFixture(unittest.TestCase):
    def test_fixture_exists_and_parses(self):
        self.assertTrue(os.path.isfile(FIXTURE), "fixture file missing")
        n = 0
        prev_ts = -1
        with open(FIXTURE) as f:
            for line in f:
                d = json.loads(line)
                self.assertIn("ts", d)
                self.assertIn("price", d)
                self.assertIn("qty", d)
                self.assertIn(d["side"], ("b", "s"))
                self.assertGreater(d["ts"], prev_ts)  # strictly increasing
                prev_ts = d["ts"]
                self.assertGreater(d["price"], 0)
                self.assertGreater(d["qty"], 0)
                n += 1
        self.assertGreater(n, 1000, "fixture unexpectedly small")

    def test_source_md_exists(self):
        src = os.path.join(REPO_ROOT, "hft", "data", "SOURCE.md")
        self.assertTrue(os.path.isfile(src), "SOURCE.md missing")
        with open(src) as f:
            body = f.read()
        self.assertIn("2026-09-22", body)
        self.assertIn("Kraken", body)


class TestReplayFeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slice_path = make_slice()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.slice_path)

    def test_deterministic_stream(self):
        a = list(ReplayFeed(self.slice_path, seed=7))
        b = list(ReplayFeed(self.slice_path, seed=7))
        self.assertEqual(len(a), len(b))
        for ea, eb in zip(a, b):
            self.assertEqual(ea, eb)

    def test_reiteration_identical(self):
        feed = ReplayFeed(self.slice_path, seed=3)
        first = list(feed)
        second = list(feed)
        self.assertEqual(first, second)

    def test_timestamps_strictly_increasing(self):
        prev = -1
        for ev in ReplayFeed(self.slice_path, seed=7):
            self.assertGreater(ev.ts_ns, prev)
            prev = ev.ts_ns

    def test_trade_event_count_matches_fixture(self):
        with open(self.slice_path) as _f:
            trades = [json.loads(l) for l in _f]
        events = list(ReplayFeed(self.slice_path, seed=7))
        n_trades = sum(1 for e in events if e.kind == TRADE)
        self.assertEqual(n_trades, len(trades))

    def test_event_structure_and_trade_aggressor(self):
        with open(self.slice_path) as _f:
            trades = [json.loads(l) for l in _f]
        events = list(ReplayFeed(self.slice_path, seed=7))
        trade_events = [e for e in events if e.kind == TRADE]
        level_events = [e for e in events if e.kind == LEVEL]
        self.assertEqual(len(level_events), 2 * 5 * len(trades))
        for t, e in zip(trades, trade_events):
            want_side = BUY if t["side"] == "b" else SELL
            self.assertEqual(e.side, want_side)
            self.assertEqual(e.price, int(round(t["price"] / 0.01)))
            self.assertEqual(e.qty, max(1, int(round(t["qty"] * QTY_PER_BTC))))
        # best bid/ask bracket every print
        for e in level_events:
            self.assertIn(e.side, (BUY, SELL))
            self.assertGreater(e.qty, 0)

    def test_touch_spread_small_and_brackets_print(self):
        # group events per trade: 10 LEVEL + 1 TRADE, in order
        events = list(ReplayFeed(self.slice_path, seed=7))
        per = 2 * 5 + 1
        for i in range(0, len(events), per):
            chunk = events[i:i + per]
            self.assertEqual(len(chunk), per)
            trade = chunk[-1]
            self.assertEqual(trade.kind, TRADE)
            bids = [e for e in chunk[:-1] if e.side == BUY]
            asks = [e for e in chunk[:-1] if e.side == SELL]
            best_bid = max(e.price for e in bids)
            best_ask = min(e.price for e in asks)
            self.assertLessEqual(best_bid, trade.price)
            self.assertGreaterEqual(best_ask, trade.price)
            self.assertLessEqual(best_ask - best_bid, 3)  # modeled 1-3 ticks

    def test_different_seed_same_prints_different_book(self):
        a = [e for e in ReplayFeed(self.slice_path, seed=1) if e.kind == TRADE]
        b = [e for e in ReplayFeed(self.slice_path, seed=2) if e.kind == TRADE]
        self.assertEqual([(e.price, e.qty, e.side, e.ts_ns) for e in a],
                         [(e.price, e.qty, e.side, e.ts_ns) for e in b])
        la = [e for e in ReplayFeed(self.slice_path, seed=1) if e.kind == LEVEL]
        lb = [e for e in ReplayFeed(self.slice_path, seed=2) if e.kind == LEVEL]
        self.assertNotEqual(
            [(e.price, e.qty) for e in la], [(e.price, e.qty) for e in lb])

    def test_sim_seconds_and_estimate(self):
        feed = ReplayFeed(self.slice_path, seed=7)
        self.assertGreater(feed.sim_seconds, 0)
        self.assertEqual(feed.estimate_event_count(),
                         feed.n_trades * (2 * 5 + 1))
        self.assertEqual(feed.n_trades, SLICE_N)


class TestNoNetworkIO(unittest.TestCase):
    def test_replay_module_does_not_import_network(self):
        # Importing the hft package __init__ pulls existing modules (e.g.
        # venue); the assertion is scoped to what hft.replay itself adds.
        code = (
            "import sys, hft; "
            "before = set(sys.modules); "
            "import hft.replay; "
            "new = set(sys.modules) - before; "
            "bad = sorted(m for m in new if m.split('.')[0] in "
            "('urllib', 'socket', 'requests', 'http', 'ssl', 'websocket')); "
            "print('BAD:' + ','.join(bad) if bad else 'CLEAN')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CLEAN", r.stdout)

    def test_replay_source_has_no_network_references(self):
        src = open(os.path.join(REPO_ROOT, "hft", "replay.py")).read().lower()
        for token in ("urllib", "socket", "requests", "http", "urlopen",
                      "curl", "websocket"):
            self.assertNotIn(token, src, f"suspicious token: {token}")


if __name__ == "__main__":
    unittest.main()
