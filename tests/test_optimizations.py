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
