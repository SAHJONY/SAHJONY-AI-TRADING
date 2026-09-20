"""MACRO PULSE tests — no live network.

All HTTP is stubbed by monkeypatching this module's ``_http_get_json`` /
``_fetch_bars`` helpers, so the Yahoo Finance chart API is never touched.
Fixtures mimic the Yahoo v8 chart JSON shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import macro as mp  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_TS = 1_788_480_000  # 2026-09-01 00:00:00 UTC


def _yahoo_result(closes, symbol="DX-Y.NYB", tz="America/New_York"):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": symbol, "exchangeTimezoneName": tz},
                    "timestamp": [BASE_TS + i * 86400 for i in range(len(closes))],
                    "indicators": {"quote": [{"close": list(closes)}]},
                }
            ],
            "error": None,
        }
    }


def _bars(closes, tz="America/New_York"):
    return [((BASE_TS + i * 86400), c) for i, c in enumerate(closes)], tz


DXY_SPEC = {"symbol": "DX-Y.NYB", "name": "US Dollar Index", "unit": "points"}


# ---------------------------------------------------------------------------
# Instrument parsing
# ---------------------------------------------------------------------------

def test_parse_instrument_changes_and_trend_up():
    closes = [95.0 + i * 0.5 for i in range(25)]  # steady uptrend: 95.0 … 107.0
    inst = mp._parse_instrument(DXY_SPEC, *_bars(closes))
    assert inst["symbol"] == "DX-Y.NYB"
    assert inst["name"] == "US Dollar Index"
    assert inst["last"] == pytest.approx(107.0)
    assert inst["chg_1d_pct"] == pytest.approx(round(107.0 / 106.5 * 100 - 100, 3))
    assert inst["chg_5d_pct"] == pytest.approx(round(107.0 / 104.5 * 100 - 100, 3))
    assert inst["trend_20d"] == "up"
    assert inst["bars"] == 25
    assert inst["as_of"] is not None and len(inst["as_of"]) == 10


def test_parse_instrument_trend_down_and_flat():
    down = [110.0 - i * 0.5 for i in range(25)]
    assert mp._parse_instrument(DXY_SPEC, *_bars(down))["trend_20d"] == "down"
    flat = [100.0] * 25
    assert mp._parse_instrument(DXY_SPEC, *_bars(flat))["trend_20d"] == "flat"


def test_parse_instrument_insufficient_history():
    inst = mp._parse_instrument(DXY_SPEC, *_bars([100.0, 101.0, 102.0]))
    assert inst["trend_20d"] is None
    assert inst["chg_5d_pct"] is None
    assert inst["chg_1d_pct"] == pytest.approx(round(102.0 / 101.0 * 100 - 100, 3))


def test_parse_instrument_single_bar():
    inst = mp._parse_instrument(DXY_SPEC, *_bars([100.0]))
    assert inst["last"] == pytest.approx(100.0)
    assert inst["chg_1d_pct"] is None
    assert inst["chg_5d_pct"] is None
    assert inst["trend_20d"] is None


# ---------------------------------------------------------------------------
# Fetch (host fallback)
# ---------------------------------------------------------------------------

def test_fetch_bars_host_fallback(monkeypatch):
    calls = []

    def fake_get_json(url, timeout, headers=None):
        calls.append(url)
        if "query1" in url:
            raise ConnectionError("query1 down")
        return _yahoo_result([100.0, 101.0])

    monkeypatch.setattr(mp, "_http_get_json", fake_get_json)
    bars, tz = mp._fetch_bars("DX-Y.NYB")
    assert [c for _, c in bars] == [100.0, 101.0]
    assert tz == "America/New_York"
    assert len(calls) == 2  # tried query1, then query2


def test_fetch_bars_filters_null_closes(monkeypatch):
    result = _yahoo_result([100.0, None, 102.0])
    monkeypatch.setattr(mp, "_http_get_json", lambda *a, **k: result)
    bars, _ = mp._fetch_bars("DX-Y.NYB")
    assert [c for _, c in bars] == [100.0, 102.0]


# ---------------------------------------------------------------------------
# Backdrop derivation
# ---------------------------------------------------------------------------

def _mk(symbol, chg_5d=None, chg_1d=None):
    return {"symbol": symbol, "chg_5d_pct": chg_5d, "chg_1d_pct": chg_1d}


def test_backdrop_risk_off():
    bd = mp.derive_backdrop([_mk("DX-Y.NYB", 1.2), _mk("^TNX", 3.5)])
    assert bd["bias"] == "defensive"
    assert "risk-off headwind" in bd["label"]
    assert "INTELLIGENCE ONLY" in bd["label"]
    assert bd["window"] == "5d"


def test_backdrop_risk_on():
    bd = mp.derive_backdrop([_mk("DX-Y.NYB", -1.1), _mk("^TNX", -2.8)])
    assert bd["bias"] == "supportive"
    assert "risk-on tailwind" in bd["label"]


def test_backdrop_mixed():
    bd = mp.derive_backdrop([_mk("DX-Y.NYB", 1.2), _mk("^TNX", -0.5)])
    assert bd["bias"] == "neutral"
    assert "mixed" in bd["label"]


def test_backdrop_falls_back_to_1d():
    bd = mp.derive_backdrop([_mk("DX-Y.NYB", None, 0.9), _mk("^TNX", None, 2.4)])
    assert bd["bias"] == "defensive"
    assert bd["window"] == "1d"


def test_backdrop_missing_data_is_neutral():
    bd = mp.derive_backdrop([_mk("DX-Y.NYB", 1.2), _mk("^TNX", None, None)])
    assert bd["bias"] == "neutral"
    assert "unknown" in bd["label"]
    bd2 = mp.derive_backdrop([])
    assert bd2["bias"] == "neutral"
    assert "unknown" in bd2["label"]


# ---------------------------------------------------------------------------
# refresh() orchestration — never raises, stale on failure
# ---------------------------------------------------------------------------

def _fake_fetch_bars_ok(spec, timeout=20):
    closes = [100.0 + i * 0.1 for i in range(25)]
    return _bars(closes)


def test_refresh_success_writes_payload(tmp_path, monkeypatch):
    out = tmp_path / "macro_pulse.json"
    cache = tmp_path / "macro_pulse_cache.json"
    monkeypatch.setattr(mp, "_fetch_bars", _fake_fetch_bars_ok)

    payload = mp.refresh(out_path=out, cache_path=cache)
    assert payload["schema_version"] == 1
    assert payload["stale"] is False
    assert payload["errors"] == []
    assert len(payload["instruments"]) == 4
    assert payload["backdrop"]["bias"] in ("defensive", "neutral", "supportive")
    assert payload["sources"] == mp.SOURCES
    assert out.exists() and cache.exists()
    # every instrument carries the required fields, nothing invented
    for inst in payload["instruments"]:
        for key in ("symbol", "name", "unit", "last", "as_of",
                    "chg_1d_pct", "chg_5d_pct", "trend_20d", "bars"):
            assert key in inst


def test_refresh_network_failure_is_stale_not_raise(tmp_path, monkeypatch):
    out = tmp_path / "macro_pulse.json"
    cache = tmp_path / "macro_pulse_cache.json"

    def boom(url, timeout, headers=None):
        raise ConnectionError("no network")

    monkeypatch.setattr(mp, "_http_get_json", boom)
    payload = mp.refresh(out_path=out, cache_path=cache)  # must not raise
    assert payload["stale"] is True
    assert len(payload["errors"]) == 4  # one per instrument
    assert payload["instruments"] == []
    assert "unknown" in payload["backdrop"]["label"]
    assert out.exists()
    assert not cache.exists()  # nothing good to cache


def test_refresh_serves_stale_cache_on_total_failure(tmp_path, monkeypatch):
    out = tmp_path / "macro_pulse.json"
    cache = tmp_path / "macro_pulse_cache.json"
    monkeypatch.setattr(mp, "_fetch_bars", _fake_fetch_bars_ok)
    mp.refresh(out_path=out, cache_path=cache)

    def boom(spec, timeout=20):
        raise ConnectionError("no network")

    monkeypatch.setattr(mp, "_fetch_bars", boom)
    monkeypatch.setattr(mp, "CACHE_TTL_S", 0)  # expire the cache: force the network path
    payload = mp.refresh(out_path=out, cache_path=cache)
    assert payload["stale"] is True
    assert len(payload["instruments"]) == 4  # stale cache served
    assert any("stale cache" in e for e in payload["errors"])


def test_refresh_cache_first_skips_network(tmp_path, monkeypatch):
    out = tmp_path / "macro_pulse.json"
    cache = tmp_path / "macro_pulse_cache.json"
    monkeypatch.setattr(mp, "_fetch_bars", _fake_fetch_bars_ok)
    mp.refresh(out_path=out, cache_path=cache)

    def must_not_run(*a, **k):
        raise AssertionError("network must not be touched on fresh cache")

    monkeypatch.setattr(mp, "_fetch_bars", must_not_run)
    payload = mp.refresh(out_path=out, cache_path=cache)
    assert payload["stale"] is False
    assert len(payload["instruments"]) == 4


# ---------------------------------------------------------------------------
# load_payload / summary_for_status
# ---------------------------------------------------------------------------

def test_load_payload_roundtrip(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert mp.load_payload(path)["schema_version"] == 1
    assert mp.load_payload(tmp_path / "missing.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert mp.load_payload(bad) == {}


def test_summary_for_status():
    assert mp.summary_for_status({}) == {"available": False}
    payload = {
        "ts": "2026-09-19T00:00:00+00:00",
        "stale": False,
        "sources": mp.SOURCES,
        "backdrop": {"bias": "neutral"},
        "instruments": [
            {"symbol": "DX-Y.NYB", "last": 100.2, "chg_5d_pct": 0.5, "trend_20d": "up"},
            {"symbol": "^TNX", "last": 5.0, "chg_5d_pct": -1.0, "trend_20d": "down"},
        ],
    }
    s = mp.summary_for_status(payload)
    assert s["available"] is True
    assert s["instrument_count"] == 2
    assert s["backdrop"]["bias"] == "neutral"
    assert s["instruments"][0]["symbol"] == "DX-Y.NYB"
    assert s["stale"] is False
    assert s["sources"] == mp.SOURCES
