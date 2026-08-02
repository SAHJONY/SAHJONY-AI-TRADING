"""Regression tests for the trading-system optimizations (python -m tests.test_optimizations).

Each of these locks in a change that is only safe because it is behaviour-
preserving. They assert equivalence and invariants, never speed — a timing
assertion would be flaky on shared CI hardware, and the thing that actually
matters is that the fast path still computes the same numbers.
"""
from __future__ import annotations

import sys

import numpy as np

from config import load_config
from database import Database
from intelligence import engines
from backtest.engine import Backtester
from utils.quote_cache import CachedBroker

FAILURES = []


def _check(cond: bool, label: str) -> None:
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        FAILURES.append(label)


class _FakeBroker:
    """Counts upstream calls so caching can be observed rather than assumed."""
    mode = "offline-sim"

    def __init__(self):
        self.price_calls = 0
        self.hist_calls = 0
        self.advanced = 0
        self.px = 100.0

    @property
    def online(self) -> bool:
        return False

    def get_price(self, symbol):
        self.price_calls += 1
        return 0.0 if symbol == "BROKEN" else self.px

    def get_history(self, symbol, days=120):
        self.hist_calls += 1
        return {"closes": np.arange(1.0, float(days) + 1.0), "volumes": np.ones(days)}

    def advance_sim(self, steps=1):
        self.advanced += steps
        self.px += 1.0

    def submit_equity_order(self, symbol, qty, side):
        return {"status": "filled", "simulated": True}

    def whatever_else(self):
        return "delegated"


def main() -> int:
    print("\n── expanding_vol replaces the O(n^2) loop exactly ──")
    rng = np.random.default_rng(4)
    cases = {
        "random walk": 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 250))),
        "trending": np.linspace(50.0, 150.0, 300),
        "high vol": 100 * np.exp(np.cumsum(rng.normal(0, 0.09, 180))),
        "just above start": 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 26))),
    }
    for name, closes in cases.items():
        old = np.array([engines.annualized_vol(closes[:i])
                        for i in range(20, len(closes))])
        new = engines.expanding_vol(closes, 20)
        _check(old.shape == new.shape and np.allclose(old, new, rtol=1e-9, atol=1e-12),
               f"{name}: matches the original loop element for element")
    _check(engines.expanding_vol(np.array([1.0, 2.0, 3.0]), 20).size == 0,
           "too-short series returns empty rather than raising")
    _check(engines.expanding_vol(np.array([]), 20).size == 0,
           "empty series returns empty rather than raising")
    flat = engines.expanding_vol(np.full(60, 42.0), 20)
    _check(flat.size > 0 and np.all(flat >= 0.0) and np.all(np.isfinite(flat)),
           "a flat series gives finite, non-negative vol (no sqrt of -0)")

    print("\n── per-cycle quote cache is transparent ──")
    fake = _FakeBroker()
    c = CachedBroker(fake)
    _check(c.mode == "offline-sim" and c.whatever_else() == "delegated",
           "unknown attributes and methods delegate to the adapter")
    _check(c.online is False, "properties delegate correctly")

    a, b = c.get_price("AAPL"), c.get_price("AAPL")
    _check(a == b and fake.price_calls == 1,
           "the same symbol is priced once per cycle, not once per caller")
    c.get_price("MSFT")
    _check(fake.price_calls == 2, "different symbols still reach the broker")

    c.begin_cycle()
    c.get_price("AAPL")
    _check(fake.price_calls == 3, "a new cycle re-reads the price")

    before = fake.price_calls
    c.advance_sim(1)
    c.get_price("AAPL")
    _check(fake.advanced == 1 and fake.price_calls == before + 1,
           "advancing the simulator invalidates cached prices")

    # a failed quote must never be pinned for a whole cycle
    fake2 = _FakeBroker()
    c2 = CachedBroker(fake2)
    c2.get_price("BROKEN")
    c2.get_price("BROKEN")
    _check(fake2.price_calls == 2, "a 0.0 (failed) quote is never cached")

    h1 = c.get_history("AAPL", 50)
    h2 = c.get_history("AAPL", 50)
    _check(fake.hist_calls == 1 and h1 is h2, "history is cached per (symbol, days)")
    c.get_history("AAPL", 120)
    _check(fake.hist_calls == 2, "a different lookback is a different cache entry")

    stats = c.cache_stats()
    _check(stats["price_hits"] >= 1 and stats["price_calls"] > stats["price_hits"],
           "cache reports hit statistics")

    print("\n── real-time quote guard ──")
    from utils.realtime import RealtimeGuard, consensus_price, Quote

    class _Feed:
        mode = "test"
        def __init__(self, seq): self.seq, self.i = seq, 0
        def get_price(self, symbol):
            v = self.seq[min(self.i, len(self.seq) - 1)]; self.i += 1; return v
        @property
        def online(self): return False

    # a single wild print is quarantined; the last good price is served instead
    g = RealtimeGuard(_Feed([100.0, 500.0, 101.0]), max_jump_pct=0.10)
    _check(g.get_price("X") == 100.0, "first quote is accepted")
    _check(g.get_price("X") == 100.0, "a 5x outlier print is rejected, last good served")
    _check(g.get_price("X") == 101.0, "the feed recovers to a sane price")
    _check(g.health().total_rejected == 1, "the rejection is counted in health")

    # two consecutive prints in the new region ARE a real move, not an outlier
    g2 = RealtimeGuard(_Feed([100.0, 130.0, 131.0]), max_jump_pct=0.10)
    g2.get_price("Y"); g2.get_price("Y")
    _check(g2.get_price("Y") == 131.0, "a confirmed gap is accepted on the second print")

    # a failed (0.0) read must never become a traded price
    g3 = RealtimeGuard(_Feed([100.0, 0.0]), max_jump_pct=0.10)
    g3.get_price("Z")
    _check(g3.get_price("Z") == 100.0, "a 0.0 read never replaces a good price")
    q = g3.last_quote("Z")
    _check(q is not None and q.stale and not q.trustworthy,
           "the served fallback is flagged stale and untrustworthy")

    # with no history at all a bad read stays 0.0 rather than inventing a price
    g4 = RealtimeGuard(_Feed([0.0]), max_jump_pct=0.10)
    _check(g4.get_price("W") == 0.0, "with no history, a bad read is not fabricated")

    # frozen-feed detection
    g5 = RealtimeGuard(_Feed([50.0, 50.0]), max_jump_pct=0.10, stale_after_s=0.0)
    g5.get_price("F"); g5.get_price("F")
    _check(g5.last_quote("F").suspect, "an unchanging price is flagged as possibly frozen")

    _check(g.mode == "test" and g.online is False, "guard delegates transparently")

    px, agreed = consensus_price([Quote("A", 100.0, 0), Quote("A", 100.5, 0),
                                  Quote("A", 100.2, 0)])
    _check(agreed and 100.0 <= px <= 100.5, "agreeing sources produce a median price")
    px2, agreed2 = consensus_price([Quote("A", 100.0, 0), Quote("A", 140.0, 0)])
    _check(not agreed2, "cross-source disagreement is reported, not silently averaged")
    _check(consensus_price([])[0] == 0.0, "no usable sources returns 0 and not-agreed")

    # venue timestamps: the failure fetch-time cannot see
    class _TsFeed:
        mode = "test"
        def __init__(self, age_s): self.age = age_s
        def get_price(self, symbol): return 100.0
        def get_price_with_ts(self, symbol):
            import time as _t
            return 100.0, _t.time() - self.age

    g6 = RealtimeGuard(_TsFeed(600.0), max_venue_age_s=60.0)
    _check(g6.venue_timestamps, "an adapter reporting venue time is detected")
    g6.get_price("V")
    q6 = g6.last_quote("V")
    _check(q6.venue_age_s is not None and q6.venue_age_s > 500,
           "staleness is measured from the exchange print, not our fetch")
    _check(q6.age_s < 5 and q6.suspect and not q6.trustworthy,
           "a fresh fetch of a stale print is caught (age_s alone would miss it)")

    g7 = RealtimeGuard(_TsFeed(1.0), max_venue_age_s=60.0)
    g7.get_price("V")
    _check(g7.last_quote("V").trustworthy, "a fresh venue print is trusted")

    # adapters without the optional extension must be unaffected
    g8 = RealtimeGuard(_Feed([100.0]), max_venue_age_s=60.0)
    _check(not g8.venue_timestamps and g8.get_price("N") == 100.0,
           "an adapter lacking the extension still prices normally")
    _check(g8.last_quote("N").venue_age_s is None,
           "…and honestly reports that it has no venue timestamp")

    class _BadTs(_Feed):
        def get_price_with_ts(self, symbol): raise RuntimeError("venue api down")
    g9 = RealtimeGuard(_BadTs([100.0]), max_venue_age_s=60.0)
    _check(g9.get_price("B") == 100.0,
           "a failing optional extension falls back instead of breaking pricing")

    print("\n── feed health reaches the things that act on it ──")
    from intelligence.hermes import Hermes
    _h = Hermes(load_config())

    class _Rejected:
        stale, suspect, venue_age_s = True, False, None
    class _Suspect:
        stale, suspect, venue_age_s = False, True, 612.0
    class _Good:
        stale, suspect, venue_age_s = False, False, 1.0
    class _FeedOf:
        def __init__(self, q): self.q = q
        def last_quote(self, sym): return self.q

    hard, soft = _h._feed_issues(_FeedOf(_Rejected()), "BTC/USD", [], [])
    _check(len(hard) == 1 and not soft,
           "a guard-rejected quote is a HARD issue — quarantines new risk, exits still flow")
    hard, soft = _h._feed_issues(_FeedOf(_Suspect()), "BTC/USD", [], [])
    _check(not hard and len(soft) == 1 and "612" in soft[0],
           "a stale venue print is a soft warning naming the age")
    _check(_h._feed_issues(_FeedOf(_Good()), "BTC/USD", [], []) == ([], []),
           "a healthy quote adds no issues")
    _check(_h._feed_issues(None, "BTC/USD", [], []) == ([], []),
           "no feed wired in leaves the review unchanged")

    class _Boom:
        def last_quote(self, sym): raise RuntimeError("guard exploded")
    _check(_h._feed_issues(_Boom(), "X", [], []) == ([], []),
           "a broken guard cannot take down the review that catches problems")

    from workforce.reporter import _feed_block
    class _NoFeed: pass
    _check(_feed_block(_NoFeed())["available"] is False,
           "the status block degrades when no feed is present")
    class _BadFeed:
        feed = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))
    blk = _feed_block(type("F", (), {"feed": property(
        lambda self: (_ for _ in ()).throw(RuntimeError("boom")))})())
    _check(blk["available"] is False and "error" in blk,
           "a failing feed never breaks the dashboard report")

    print("\n── extra strategies (S11-S18) ──")
    from backtest import synth as _syn
    from backtest.strategies import REGISTRY as _REG
    b4 = _syn.make(days=90, seed=5)
    for sid in ("s11", "s12", "s13", "s14", "s15", "s16", "s17", "s18"):
        _check(sid in _REG, f"{sid} is registered")
    for sid in ("s11", "s12", "s14", "s16", "s18"):
        r = Backtester(b4).run(_REG[sid]())
        ok = all(np.isfinite(t.pnl) and np.isfinite(t.r) for t in r["trades"])
        _check(ok and len(r["trades"]) > 0,
               f"{sid}: produces a measurable sample ({len(r['trades'])} trades)")
    for sid, cls in _REG.items():
        base = len(Backtester(b4).run(cls())["trades"])
        same = len(Backtester(b4).run(cls(**{}))["trades"])
        _check(base == same, f"{sid}: no-arg construction is the documented spec")

    print("\n── bar recorder (the only path from Robinhood to real bars) ──")
    from utils.bar_recorder import BarRecorder
    import tempfile as _tf, os as _os
    with _tf.TemporaryDirectory() as _d:
        _db = Database(_os.path.join(_d, "bars.db"))
        rec = BarRecorder(_db, interval_minutes=5)
        t0 = 1_800_000_000                      # a 5m bucket boundary
        for px in (100.0, 105.0, 95.0, 102.0):  # all inside one bucket
            rec.record("BTC/USD", px, ts=t0 + 10)
        _db.conn.commit()
        row = _db.conn.execute("SELECT * FROM bars WHERE symbol='BTC/USD'").fetchone()
        _check(row["open"] == 100.0 and row["high"] == 105.0
               and row["low"] == 95.0 and row["close"] == 102.0,
               "OHLC folds correctly from a stream of quotes")
        _check(row["volume"] == 4, "volume counts ticks (documented: NOT traded volume)")
        _check(row["ts"] == t0, "observations bucket to the interval start")

        rec.record("BTC/USD", 111.0, ts=t0 + 300)   # next bucket
        _db.conn.commit()
        _check(_db.conn.execute("SELECT COUNT(*) c FROM bars").fetchone()["c"] == 2,
               "a later observation opens a new bar")

        for bad in (0.0, -5.0, float("nan"), None):
            rec.record("BTC/USD", bad, ts=t0 + 600)
        _db.conn.commit()
        _check(_db.conn.execute("SELECT COUNT(*) c FROM bars").fetchone()["c"] == 2,
               "bad prices (0, negative, NaN, None) never create a bar")

        cov = rec.coverage()
        _check(cov and cov[0]["bars"] == 2 and cov[0]["interval_m"] == 5,
               "coverage reports what has actually accumulated")

        csv_path = _os.path.join(_d, "out.csv")
        n = rec.export_csv("BTC/USD", csv_path)
        from backtest.data import load_csv as _lc
        bars_out = _lc(csv_path)
        _check(n == 2 and len(bars_out) == 2 and bars_out.close[-1] == 111.0,
               "exported bars load straight into the backtest harness")

        class _BrokenDB:
            class conn:
                @staticmethod
                def executescript(*a): raise RuntimeError("no db")
        r2 = BarRecorder(_BrokenDB(), 5)
        r2.record("X", 1.0); r2.record_many({"X": 1.0})
        _check(r2.coverage() == [], "a broken database degrades silently, never raises")

    print("\n── recorded feed → harness (multi-interval, tick-quality gate) ──")
    from backtest.data import (DataUnavailable as _DU, desk_coverage,
                               load_desk_db)
    with _tf.TemporaryDirectory() as _d:
        path = _os.path.join(_d, "desk.db")
        _db = Database(path)
        from config import bar_intervals_for
        _check(bar_intervals_for(15) == (15, 60),
               "a 15-minute cycle records 15m and 60m — not 5m")
        _check(bar_intervals_for(5) == (5, 15),
               "a 5-minute cycle records the 5m spec, correctly, with no code change")
        _check(bar_intervals_for(1) == (1, 5) and bar_intervals_for(60) == (60, 240),
               "the interval tracks the cadence at both ends")
        for c in (1, 3, 5, 11, 15, 30, 60, 120):
            iv = bar_intervals_for(c)
            _check(iv[-1] >= 3 * c and iv[0] >= c and list(iv) == sorted(iv),
                   f"cycle {c}m -> {iv}: coarse bar gets >=3 quotes, fine one >=1")

        rec = BarRecorder(_db, bar_intervals_for(15))
        _check(rec.intervals == [15, 60] and rec.interval == 15,
               "recorder stores several intervals, finest first")
        t0 = 1_800_000_000                       # aligned to both 15m and 60m
        # the desk's real cadence: CYCLE_MINUTES=15 plus ~1 min of cycle work
        for k in range(40):
            rec.record("BTC/USD", 100.0 + (k % 7), ts=t0 + k * 16 * 60)
        _db.conn.commit()

        cov = {c["interval_m"]: c for c in rec.coverage()}
        _check(set(cov) == {15, 60}, "both intervals accumulate from one quote stream")
        _check(cov[15]["single_tick_pct"] > 50.0,
               "the native series is mostly single-tick — reported, not hidden")
        _check(cov[60]["ticks_per_bar"] >= 3.0 and cov[60]["usable_bars"] > 0,
               "the coarse series clears 3 observations a bar, so its range is real")

        dc = {c["interval_m"]: c for c in desk_coverage(path)}
        _check(dc[15]["single_tick_pct"] == cov[15]["single_tick_pct"]
               and dc[60]["bars"] == cov[60]["bars"],
               "backtest.desk_coverage agrees with the recorder's own accounting")

        b = load_desk_db(path, symbol="BTC/USD", interval_m=60)
        _check(b.tf_minutes == 60 and len(b) > 0,
               "recorded bars load into the harness labelled with their true timeframe")
        _check(bool((b.high > b.low).all()),
               "the min_ticks gate admits only bars whose range was observed")

        auto = load_desk_db(path, symbol="BTC/USD")
        _check(auto.tf_minutes == 60,
               "with no interval named it picks the series with measured ranges, "
               "not the one with the most rows")
        _check(len(load_desk_db(path, symbol="BTC/USD", interval_m=15,
                                min_ticks=1)) > 0,
               "min_ticks=1 is available for anyone who wants the raw record")
        try:
            load_desk_db(_os.path.join(_d, "missing.db"))
            _check(False, "a missing recorder DB raises DataUnavailable")
        except _DU:
            _check(True, "a missing recorder DB raises DataUnavailable, not a crash")

        # the dashboard's honest answer to "can I backtest this yet"
        from workforce.reporter import _feed_block
        class _F: pass
        f = _F(); f.bars = rec; f.feed = None
        blk = _feed_block(f).get("recorder", {})
        ser = {s["interval_m"]: s for s in blk.get("series", [])}
        _check(blk.get("enabled") and blk.get("intervals") == [15, 60],
               "status.json reports which intervals are being recorded")
        _check(ser[60]["usable"] > 0 and ser[15]["usable"] < ser[15]["bars"],
               "it reports USABLE bars, not a raw count that overstates the record")
        class _Boom:
            @property
            def bars(self): raise RuntimeError("db gone")
        boom = _feed_block(_Boom()).get("recorder", {})
        _check(boom.get("enabled") is False and "db gone" in boom.get("error", ""),
               "a recorder that raises degrades to an error field, never a crash")

    print("\n── database indices exist ──")
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        db = Database(os.path.join(d, "t.db"))
        idx = {r["name"] for r in
               db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        for want in ("idx_council_cycle", "idx_trades_cycle", "idx_equity_cycle",
                     "idx_investors_token"):
            _check(want in idx, f"{want} is created")
        mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        _check(str(mode).lower() == "wal", "journal stays in WAL mode")
        # the index must actually be used, not merely present
        plan = db.conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM council_log WHERE cycle=?", (1,)
        ).fetchall()
        _check(any("idx_council_cycle" in str(tuple(r)) for r in plan),
               "the council-log lookup plans through its index, not a scan")

    print()
    if FAILURES:
        print(f"OPTIMIZATION CHECKS FAILED ✗ ({len(FAILURES)})")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("OPTIMIZATION CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
