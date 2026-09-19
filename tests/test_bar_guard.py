"""Fabricated-bar guard tests (upgrade/autonomous-profit).

A bar built from one poll-cadence quote has open == high == low == close: its
range — and every ATR/wick/volume signal computed from it — is fabricated.
Verifies the canonical guard in utils/bar_recorder.py:
- fetch_bars() excludes single-tick bars by default.
- The threshold is a single shared constant (intraday uses the same one).
"""
from __future__ import annotations

import os
import time

from database.db import Database
from utils.bar_recorder import BarRecorder, MIN_TICKS_MEASURED_RANGE
import intelligence.intraday as intraday_mod


def _recorder(tmp_path):
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    db = Database(str(tmp_path / "bars.db"))
    return BarRecorder(db, [15], source="test"), db


def _write_bar(db, symbol, ts, ticks, price=100.0):
    db.conn.execute(
        """INSERT INTO bars (symbol, ts, interval_m, open, high, low, close,
                             volume, source)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol, ts, interval_m) DO NOTHING""",
        (symbol, ts, 15, price, price, price, price, ticks, "test"))
    db.conn.commit()


def test_fetch_bars_excludes_single_tick(tmp_path):
    rec, db = _recorder(tmp_path)
    now = int(time.time())
    step = 15 * 60
    base = now // step * step - 4 * step
    _write_bar(db, "BTC/USD", base, 1)            # fabricated range
    _write_bar(db, "BTC/USD", base + step, 3)    # measured
    _write_bar(db, "BTC/USD", base + 2 * step, 1)
    _write_bar(db, "BTC/USD", base + 3 * step, 5)
    bars = rec.fetch_bars("BTC/USD", 15)
    assert len(bars) == 2, "only measured-range bars must come back"
    assert all(b["volume"] >= MIN_TICKS_MEASURED_RANGE for b in bars)
    assert bars[0]["ts"] < bars[1]["ts"], "oldest first"
    print("✓ fetch_bars excludes fabricated single-tick bars")


def test_fetch_bars_never_raises(tmp_path):
    rec, _ = _recorder(tmp_path)
    assert rec.fetch_bars("NOPE", 15) == []
    print("✓ fetch_bars is total (empty on unknown symbol)")


def test_threshold_is_single_sourced(tmp_path):
    assert MIN_TICKS_MEASURED_RANGE == 2
    assert intraday_mod.MIN_TICKS_PER_BAR is MIN_TICKS_MEASURED_RANGE, \
        "intraday must use the shared constant, not its own copy"
    print("✓ one constant, shared by all consumers")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        test_fetch_bars_excludes_single_tick(p)
        test_fetch_bars_never_raises(p)
        test_threshold_is_single_sourced(p)
    print("ALL BAR GUARD TESTS PASSED")
