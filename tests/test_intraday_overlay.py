"""Intraday confirmation overlay: bounded, evidence-gated, and never fatal."""
from __future__ import annotations

import os
import tempfile

import pytest

from intelligence.intraday import (
    MAX_TILT,
    MIN_TICKS_PER_BAR,
    MIN_USABLE_BARS,
    IntradayOverlay,
)


class _Cfg:
    def __init__(self, enabled=True):
        self.intraday_overlay_enabled = enabled


class _DB:
    """Minimal stand-in carrying a real sqlite conn with the recorder's schema."""

    def __init__(self, path):
        import sqlite3
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE bars (
                symbol TEXT NOT NULL, ts INTEGER NOT NULL, interval_m INTEGER NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL NOT NULL DEFAULT 0, source TEXT,
                PRIMARY KEY (symbol, ts, interval_m))""")

    def add(self, symbol, interval_m, closes, ticks=3, start_ts=0):
        for i, c in enumerate(closes):
            self.conn.execute(
                "INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)",
                (symbol, start_ts + i * interval_m * 60, interval_m,
                 c, c, c, c, float(ticks), "test"))
        self.conn.commit()


class _BrokenDB:
    class _Conn:
        def execute(self, *a, **k):
            raise RuntimeError("database is locked")
    conn = _Conn()


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as td:
        d = _DB(os.path.join(td, "t.db"))
        yield d
        d.conn.close()


def _rising(n, start=100.0, step=0.004):
    return [start * (1 + step) ** i for i in range(n)]


def _falling(n, start=100.0, step=0.004):
    return [start * (1 - step) ** i for i in range(n)]


# ── gating ───────────────────────────────────────────────────────────────────
def test_disabled_overlay_is_silent(db):
    db.add("BTC/USD", 60, _rising(60))
    read = IntradayOverlay(_Cfg(enabled=False), db).read("BTC/USD", "long")
    assert read.tilt == 0.0
    assert "disabled" in read.summary


def test_too_few_usable_bars_yields_no_tilt(db):
    db.add("BTC/USD", 60, _rising(MIN_USABLE_BARS - 1))
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert read.tilt == 0.0
    assert "measured range" in read.summary


def test_single_tick_bars_are_not_counted(db):
    """98.9% of the live desk's 15m bars are single-tick: high == low, so their
    range is assumed, not measured. They must not qualify the overlay to speak."""
    db.add("BTC/USD", 15, _rising(400), ticks=MIN_TICKS_PER_BAR - 1)
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert read.tilt == 0.0


def test_flat_council_direction_gets_no_tilt(db):
    db.add("BTC/USD", 60, _rising(60))
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "flat")
    assert read.tilt == 0.0
    assert "flat" in read.summary


def test_no_bars_at_all(db):
    read = IntradayOverlay(_Cfg(), db).read("NOPE/USD", "long")
    assert read.tilt == 0.0


# ── the signal ───────────────────────────────────────────────────────────────
def test_rising_tape_confirms_a_long(db):
    db.add("BTC/USD", 60, _rising(60))
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert read.tilt > 0
    assert read.agrees is True
    assert "confirms" in read.summary


def test_rising_tape_contradicts_a_short(db):
    db.add("BTC/USD", 60, _rising(60))
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "short")
    assert read.tilt < 0
    assert read.agrees is False
    assert "contradicts" in read.summary


def test_falling_tape_confirms_a_short(db):
    db.add("BTC/USD", 60, _falling(60))
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "short")
    assert read.tilt > 0
    assert read.agrees is True


def test_direction_symmetry(db):
    """The same tape must tilt a long and a short by equal and opposite amounts —
    the overlay judges agreement, it does not prefer a side."""
    db.add("BTC/USD", 60, _rising(60))
    ov = IntradayOverlay(_Cfg(), db)
    assert ov.read("BTC/USD", "long").tilt == pytest.approx(
        -ov.read("BTC/USD", "short").tilt)


def test_flat_series_carries_no_information(db):
    db.add("BTC/USD", 60, [100.0] * 60)
    assert IntradayOverlay(_Cfg(), db).read("BTC/USD", "long").tilt == 0.0


# ── bounds ───────────────────────────────────────────────────────────────────
def test_tilt_is_clamped_even_on_a_violent_move(db):
    closes = [100.0] * 50 + [1e6]
    db.add("BTC/USD", 60, closes)
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert abs(read.tilt) <= MAX_TILT


def test_tilt_cannot_flip_a_verdict(db):
    """±0.05 must be too small to move a verdict across the 0.51 floor from any
    plausible distance — it shades a call, it does not make one."""
    db.add("BTC/USD", 60, _rising(60))
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert abs(read.tilt) <= MAX_TILT <= 0.05


@pytest.mark.parametrize("closes", [
    _rising(60), _falling(60), [100.0] * 60,
    [100.0 + (i % 7) for i in range(60)],
])
def test_tilt_always_within_bounds(db, closes):
    db.add("BTC/USD", 60, closes)
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert -MAX_TILT <= read.tilt <= MAX_TILT


# ── interval selection ───────────────────────────────────────────────────────
def test_picks_the_interval_with_measured_range_not_the_one_with_more_rows(db):
    """The live desk has 15m with 2 usable bars of 182 and 60m with 57 of 77.
    Ranking on row count would reliably choose the useless series."""
    db.add("BTC/USD", 15, _rising(300), ticks=1)      # many rows, none usable
    db.add("BTC/USD", 60, _rising(60), ticks=3)       # fewer rows, all usable
    read = IntradayOverlay(_Cfg(), db).read("BTC/USD", "long")
    assert read.interval_m == 60
    assert read.tilt != 0.0


# ── fault isolation ──────────────────────────────────────────────────────────
def test_database_failure_degrades_to_neutral():
    read = IntradayOverlay(_Cfg(), _BrokenDB()).read("BTC/USD", "long")
    assert read.tilt == 0.0
    assert read.summary  # reported, not raised


def test_reads_maps_every_symbol(db):
    db.add("BTC/USD", 60, _rising(60))
    out = IntradayOverlay(_Cfg(), db).reads([("BTC/USD", "long"), ("ETH/USD", "long")])
    assert set(out) == {"BTC/USD", "ETH/USD"}
    assert out["ETH/USD"].tilt == 0.0        # no bars recorded for it
