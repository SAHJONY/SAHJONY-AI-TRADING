"""Tests for telemetry/latency.py — segmented cycle-latency telemetry.

Fully offline: no network, no broker, no credentials. Uses tmp_path for the
persistence file and sleeps only for timing-accuracy tolerance checks.
"""
import json
import math
import os
import time

import pytest

from telemetry import latency
from telemetry.latency import CycleRecorder, get_summary, percentile, summarize


def _recorder(tmp_path, **kw):
    return CycleRecorder(path=str(tmp_path / "lat.json"), **kw)


# ── timing accuracy ──────────────────────────────────────────────────────────
def test_segment_timing_accuracy(tmp_path):
    rec = _recorder(tmp_path)
    with rec.segment("council"):
        time.sleep(0.05)
    d = rec.durations["council"]
    assert 0.02 <= d <= 2.0, f"duration {d} outside tolerance"


def test_segment_decorator_form(tmp_path):
    rec = _recorder(tmp_path)

    @rec.segment("brain_call")
    def work():
        time.sleep(0.03)
        return 42

    assert work() == 42
    assert 0.01 <= rec.durations["brain_call"] <= 2.0


def test_note_accumulates_within_cycle(tmp_path):
    rec = _recorder(tmp_path)
    rec.note("feed_refresh", 0.5)
    rec.note("feed_refresh", 0.25)
    assert rec.durations["feed_refresh"] == pytest.approx(0.75)


def test_negative_and_nan_rejected(tmp_path):
    rec = _recorder(tmp_path)
    rec.note("x", -1.0)
    rec.note("x", float("nan"))
    rec.note("x", float("inf") if False else 0.1)  # finite ok
    assert rec.durations["x"] == pytest.approx(0.1)


# ── percentile math ──────────────────────────────────────────────────────────
def test_percentile_math():
    samples = sorted(float(i) for i in range(1, 101))  # 1..100
    assert percentile(samples, 0.50) == pytest.approx(50.5)
    assert percentile(samples, 0.95) == pytest.approx(95.05)
    assert percentile(samples, 0.99) == pytest.approx(99.01)
    assert percentile(samples, 0.0) == pytest.approx(1.0)
    assert percentile(samples, 1.0) == pytest.approx(100.0)


def test_percentile_edge_cases():
    assert percentile([], 0.5) is None
    assert percentile([2.5], 0.99) == pytest.approx(2.5)
    assert percentile([1.0, 3.0], 0.5) == pytest.approx(2.0)


# ── bounded memory ───────────────────────────────────────────────────────────
def test_bounded_memory_evicts_old(tmp_path):
    rec = _recorder(tmp_path, max_cycles=5)
    for i in range(10):
        rec.durations.clear()
        rec.note("feed_refresh", 0.1 * (i + 1))
        rec.committed = False
        rec.commit()
    assert len(rec._records) == 5
    # oldest surviving record is cycle 6 (0.6s), newest is cycle 10 (1.0s)
    assert rec._records[0]["durations"]["feed_refresh"] == pytest.approx(0.6)
    assert rec._records[-1]["durations"]["feed_refresh"] == pytest.approx(1.0)


def test_commit_idempotent(tmp_path):
    rec = _recorder(tmp_path)
    rec.note("x", 0.1)
    rec.commit()
    rec.commit()
    assert len(rec._records) == 1


# ── persistence round-trip ───────────────────────────────────────────────────
def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "lat.json")
    rec = CycleRecorder(path=path)
    with rec.segment("council"):
        time.sleep(0.02)
    rec.note("feed_refresh", 0.3)
    rec.commit()
    assert os.path.exists(path)

    rec2 = CycleRecorder(path=path)
    assert len(rec2._records) == 1
    assert rec2._records[0]["durations"]["feed_refresh"] == pytest.approx(0.3)
    assert rec2._records[0]["durations"]["council"] >= 0.005

    raw = json.load(open(path))
    assert raw["version"] == 1
    assert isinstance(raw["cycles"], list)


def test_corrupt_file_degrades_to_empty(tmp_path):
    path = tmp_path / "lat.json"
    path.write_text("not json {{{")
    rec = CycleRecorder(path=str(path))
    assert rec._records == []
    s = rec.summary()
    assert s["stale"] is True
    assert s["segments"] == {}


# ── fault isolation ──────────────────────────────────────────────────────────
def test_timer_exception_never_propagates(tmp_path, monkeypatch):
    class BrokenClock:
        @staticmethod
        def perf_counter():
            raise RuntimeError("clock exploded")

    monkeypatch.setattr(latency, "time", BrokenClock())
    rec = _recorder(tmp_path)
    with rec.segment("council"):  # must not raise
        pass
    assert rec.failures >= 1
    assert "council" not in rec.durations
    s = rec.summary()
    assert s["unavailable"] is True
    assert any("timer failure" in n for n in s["notes"])


def test_body_exception_still_propagates(tmp_path):
    """The recorder must NEVER swallow the timed code's own exceptions."""
    rec = _recorder(tmp_path)
    with pytest.raises(ValueError, match="boom"):
        with rec.segment("council"):
            raise ValueError("boom")
    # the segment still recorded its (partial) duration honestly
    assert "council" in rec.durations


def test_disabled_is_noop(tmp_path):
    rec = _recorder(tmp_path, enabled=False)
    with rec.segment("council"):
        time.sleep(0.01)
    rec.note("x", 1.0)
    assert rec.durations == {}
    s = rec.summary()
    assert s["enabled"] is False
    assert s["unavailable"] is True


def test_interrupted_cycle_marked(tmp_path):
    rec = _recorder(tmp_path)
    rec.note("feed_refresh", 0.2)
    rec.interrupted = True
    rec.commit()
    s = rec.summary()
    assert any("interrupted" in n for n in s["notes"])
    assert s["segments"]["feed_refresh"]["p50"] == pytest.approx(0.2)


# ── no invented data ─────────────────────────────────────────────────────────
def test_missing_segments_absent_not_zero(tmp_path):
    rec = _recorder(tmp_path)
    for _ in range(3):
        rec.durations.clear()
        rec.note("feed_refresh", 0.1)
        rec.committed = False
        rec.commit()
    s = rec.summary()
    assert "feed_refresh" in s["segments"]
    assert "brain_call" not in s["segments"]      # never ran -> absent
    assert "council_deliberate" not in s["segments"]
    # and no zero-filled placeholders anywhere
    for seg in s["segments"].values():
        assert seg["n"] > 0


# ── staleness ────────────────────────────────────────────────────────────────
def test_stale_when_empty():
    s = summarize([])
    assert s["stale"] is True
    assert s["cycles_recorded"] == 0
    assert s["segments"] == {}


def test_stale_when_old():
    old = [{"ts": "2020-01-01T00:00:00+00:00",
            "durations": {"feed_refresh": 1.0}}]
    s = summarize(old, stale_after_s=60)
    assert s["stale"] is True
    s2 = summarize(old, stale_after_s=10 ** 12)
    assert s2["stale"] is False


def test_fresh_not_stale(tmp_path):
    rec = _recorder(tmp_path)
    rec.note("feed_refresh", 0.1)
    rec.commit()
    rec.durations.clear()  # summary() also folds in the in-flight cycle
    s = rec.summary()
    assert s["stale"] is False
    assert s["cycles_recorded"] == 1


# ── trend / degradation ──────────────────────────────────────────────────────
def _records_with(values):
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [{"ts": (base + timedelta(hours=i)).isoformat(),
             "durations": {"feed_refresh": v}}
            for i, v in enumerate(values)]


def test_trend_degraded_on_tripling():
    recs = _records_with([1.0] * 10 + [4.0] * 10)  # p99 1.0 -> 4.0
    s = summarize(recs, stale_after_s=10 ** 12)
    seg = s["segments"]["feed_refresh"]
    assert seg["trend_ratio"] == pytest.approx(4.0)
    assert seg["degraded"] is True
    assert "feed_refresh" in s["degraded_segments"]
    assert any("degraded" in n for n in s["notes"])


def test_no_trend_below_min_samples():
    recs = _records_with([1.0] * 4 + [9.0] * 4)  # only 8 samples
    s = summarize(recs, stale_after_s=10 ** 12)
    seg = s["segments"]["feed_refresh"]
    assert seg["trend_ratio"] is None
    assert seg["degraded"] is False


def test_stable_trend_not_degraded():
    recs = _records_with([1.0 + 0.01 * i for i in range(20)])
    s = summarize(recs, stale_after_s=10 ** 12)
    seg = s["segments"]["feed_refresh"]
    assert seg["degraded"] is False
    assert seg["trend_ratio"] == pytest.approx(1.09, rel=0.05)


# ── cycle() context manager + module-level segment() ─────────────────────────
def test_cycle_context_manager_end_to_end(tmp_path):
    path = str(tmp_path / "lat.json")
    with latency.cycle(path=path) as rec:
        assert rec is not None
        with latency.segment("feed_refresh"):
            time.sleep(0.02)
        with latency.segment("council_deliberate"):
            time.sleep(0.01)
    # committed on exit
    assert os.path.exists(path)
    s = get_summary(path=path)
    assert s["cycles_recorded"] == 1
    assert set(s["segments"]) == {"feed_refresh", "council_deliberate"}
    assert s["segments"]["feed_refresh"]["n"] == 1


def test_cycle_exception_still_commits_partial(tmp_path):
    path = str(tmp_path / "lat.json")
    with pytest.raises(RuntimeError, match="cycle blew up"):
        with latency.cycle(path=path):
            with latency.segment("feed_refresh"):
                time.sleep(0.01)
            raise RuntimeError("cycle blew up")
    s = get_summary(path=path)
    assert s["cycles_recorded"] == 1
    assert "feed_refresh" in s["segments"]
    assert any("interrupted" in n for n in s["notes"])


def test_module_segment_noop_outside_cycle():
    with latency.segment("anything"):  # no active cycle -> no-op, no raise
        pass

    @latency.segment("anything")
    def f():
        return "ok"

    assert f() == "ok"
    assert latency.current_summary() is None


def test_get_summary_never_raises_on_missing_file(tmp_path):
    s = get_summary(path=str(tmp_path / "nope.json"))
    assert s["stale"] is True
    assert s["segments"] == {}


def test_summary_percentiles_from_store(tmp_path):
    rec = _recorder(tmp_path)
    for i in range(1, 6):
        rec.durations.clear()
        rec.note("brain_call", float(i))  # 1..5
        rec.committed = False
        rec.commit()
    rec.durations.clear()  # summary() also folds in the in-flight cycle
    s = rec.summary()
    seg = s["segments"]["brain_call"]
    assert seg["n"] == 5
    assert seg["p50"] == pytest.approx(3.0)
    assert seg["p99"] == pytest.approx(4.96, rel=0.01)
    assert seg["last"] == pytest.approx(5.0)
