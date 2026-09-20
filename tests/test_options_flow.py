"""BTC Options-Flow Intelligence tests — no live network.

All HTTP is stubbed by monkeypatching this module's ``_http_get_json``
helper. Fixtures are built from a sanitized sample of the real Deribit
``get_book_summary_by_currency`` response shape (public market data —
verified live 2026-09-19).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import options_flow as oflow  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures (real API shape)
# ---------------------------------------------------------------------------

BOOK_SUMMARY_FIXTURE = {
    "jsonrpc": "2.0",
    "result": [
        # Nearest expiry 2026-09-25: puts bid up — defensive posture
        {
            "instrument_name": "BTC-25SEP26-70000-P",
            "open_interest": 1200.0,
            "mark_iv": 62.5,
            "volume": 300.0,
            "volume_usd": 24000000.0,
            "underlying_price": 81000.0,
        },
        {
            "instrument_name": "BTC-25SEP26-90000-C",
            "open_interest": 400.0,
            "mark_iv": 52.0,
            "volume": 150.0,
            "volume_usd": 12000000.0,
            "underlying_price": 81000.0,
        },
        # Far expiry 2027-03-26: calmer contango
        {
            "instrument_name": "BTC-26MAR27-60000-P",
            "open_interest": 500.0,
            "mark_iv": 58.0,
            "volume": 0.0,
            "volume_usd": 0.0,
            "underlying_price": 81500.0,
        },
        {
            "instrument_name": "BTC-26MAR27-120000-C",
            "open_interest": 500.0,
            "mark_iv": 56.0,
            "volume": 10.0,
            "volume_usd": 800000.0,
            "underlying_price": 81500.0,
        },
        # Unparseable / degenerate rows must be ignored, never crash
        {
            "instrument_name": "BTC-PERPETUAL",
            "open_interest": 9000.0,
            "mark_iv": None,
            "volume": 5000.0,
            "volume_usd": 400000000.0,
            "underlying_price": 81200.0,
        },
        {
            "instrument_name": "garbage",
            "open_interest": 10.0,
            "mark_iv": 90.0,
            "volume": 1.0,
            "volume_usd": 80000.0,
            "underlying_price": 81000.0,
        },
        {
            "instrument_name": "BTC-25SEP26-95000-C",
            "open_interest": None,  # no OI → ignored
            "mark_iv": 99.9,
            "volume": 0.0,
            "volume_usd": 0.0,
            "underlying_price": 81000.0,
        },
        {
            "instrument_name": "BTC-25SEP26-85000-P",
            "open_interest": 200.0,
            "mark_iv": None,  # missing IV → OI counts, IV excluded
            "volume": 5.0,
            "volume_usd": 405000.0,
            "underlying_price": 81000.0,
        },
    ],
}


def _stub_http(monkeypatch, fixture):
    def _fake(url, timeout):
        assert url.startswith("https://www.deribit.com/")
        return fixture
    monkeypatch.setattr(oflow, "_http_get_json", _fake)


# ---------------------------------------------------------------------------
# Instrument-name parsing
# ---------------------------------------------------------------------------

def test_parse_expiry_call_and_put():
    assert oflow._parse_expiry("BTC-26MAR27-40000-C") == ("2027-03-26", "call")
    assert oflow._parse_expiry("BTC-25SEP26-72000-P") == ("2026-09-25", "put")


@pytest.mark.parametrize("name", [
    "BTC-PERPETUAL", "BTC-25SEP26-FUTURE", "garbage", "", None,
    "BTC-99XXX26-1000-C", "BTC-32SEP26-1000-P",
])
def test_parse_expiry_rejects_non_options(name):
    assert oflow._parse_expiry(name) == (None, None)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_aggregate_expiries_per_expiry_metrics():
    expiries, totals = oflow.aggregate_expiries(
        BOOK_SUMMARY_FIXTURE["result"], underlying_price=81000.0
    )
    assert len(expiries) == 2
    near, far = expiries
    assert near["expiry"] == "2026-09-25"
    # put OI 1200 + 200 (None-IV row still counts OI); call OI 400
    assert near["put_oi"] == 1400.0
    assert near["call_oi"] == 400.0
    assert near["put_call_oi_ratio"] == pytest.approx(3.5)
    # OI-weighted put IV: only the 1200 row has an IV → 62.5
    assert near["put_iv_avg"] == pytest.approx(62.5)
    assert near["call_iv_avg"] == pytest.approx(52.0)
    assert near["skew"] == pytest.approx(10.5)
    assert far["expiry"] == "2027-03-26"
    assert far["skew"] == pytest.approx(2.0)

    # Totals
    assert totals["option_oi_btc"] == pytest.approx(2800.0)
    assert totals["option_oi_usd"] == pytest.approx(2800.0 * 81000.0)
    # 24h volume: only positive volumes count
    assert totals["volume_24h_btc"] == pytest.approx(300.0 + 150.0 + 10.0 + 5.0)
    assert totals["volume_24h_usd"] == pytest.approx(
        24000000.0 + 12000000.0 + 800000.0 + 405000.0
    )


def test_aggregate_empty_rows():
    expiries, totals = oflow.aggregate_expiries([], underlying_price=None)
    assert expiries == []
    assert totals["option_oi_btc"] == 0.0
    assert totals["option_oi_usd"] is None


def test_aggregate_ignores_perpetual_rows():
    rows = [BOOK_SUMMARY_FIXTURE["result"][4]]  # BTC-PERPETUAL
    expiries, totals = oflow.aggregate_expiries(rows, underlying_price=81000.0)
    assert expiries == []
    assert totals["option_oi_btc"] == 0.0


# ---------------------------------------------------------------------------
# Flow read
# ---------------------------------------------------------------------------

def test_flow_read_defensive():
    expiries, _ = oflow.aggregate_expiries(
        BOOK_SUMMARY_FIXTURE["result"], underlying_price=81000.0
    )
    flow = oflow.flow_read(expiries)
    # put/call OI 2000/900 = 2.22 ≥ 1.25 AND near skew +10.5 ≥ 5 → defensive
    assert flow["bias"] == "defensive"
    assert flow["label"].startswith("INTELLIGENCE ONLY")
    assert flow["put_call_oi_ratio"] == pytest.approx(2.111, rel=1e-3)
    assert len(flow["flags"]) >= 2


def test_flow_read_neutral_on_empty():
    flow = oflow.flow_read([])
    assert flow["bias"] == "neutral"
    assert flow["put_call_oi_ratio"] is None
    assert flow["flags"]


def test_flow_read_watch_single_flag():
    expiries = [{
        "expiry": "2026-09-25",
        "put_oi": 1300.0, "call_oi": 1000.0, "put_call_oi_ratio": 1.3,
        "put_iv_avg": 55.0, "call_iv_avg": 54.0, "skew": 1.0,
        "avg_iv": 54.5, "total_oi_btc": 2300.0, "contracts": 10,
    }]
    flow = oflow.flow_read(expiries)
    # Only the put/call ratio flag fires → watch
    assert flow["bias"] == "watch"


def test_flow_read_neutral_calm_book():
    expiries = [{
        "expiry": "2026-09-25",
        "put_oi": 1000.0, "call_oi": 1000.0, "put_call_oi_ratio": 1.0,
        "put_iv_avg": 55.0, "call_iv_avg": 56.0, "skew": -1.0,
        "avg_iv": 55.5, "total_oi_btc": 2000.0, "contracts": 10,
    }, {
        "expiry": "2027-03-26",
        "put_oi": 500.0, "call_oi": 500.0, "put_call_oi_ratio": 1.0,
        "put_iv_avg": 57.0, "call_iv_avg": 57.0, "skew": 0.0,
        "avg_iv": 57.0, "total_oi_btc": 1000.0, "contracts": 8,
    }]
    flow = oflow.flow_read(expiries)
    assert flow["bias"] == "neutral"
    assert flow["term_slope"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Cache-first fetch
# ---------------------------------------------------------------------------

def test_fetch_book_summary_caches_and_serves(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    _stub_http(monkeypatch, BOOK_SUMMARY_FIXTURE)
    rows, underlying = oflow.fetch_book_summary(cache_path=cache, ttl_s=900)
    assert len(rows) == len(BOOK_SUMMARY_FIXTURE["result"])
    assert underlying == pytest.approx(81000.0)
    assert cache.exists()

    # Second call with a failing network must serve the cache
    def _boom(url, timeout):
        raise RuntimeError("network down")
    monkeypatch.setattr(oflow, "_http_get_json", _boom)
    rows2, underlying2 = oflow.fetch_book_summary(cache_path=cache, ttl_s=900)
    assert len(rows2) == len(rows)
    assert underlying2 == underlying


# ---------------------------------------------------------------------------
# refresh / load_payload / summary_for_status
# ---------------------------------------------------------------------------

def test_refresh_writes_payload(tmp_path, monkeypatch):
    _stub_http(monkeypatch, BOOK_SUMMARY_FIXTURE)
    out = tmp_path / "options_flow.json"
    cache = tmp_path / "cache.json"
    payload = oflow.refresh(out_path=out, cache_path=cache)

    assert out.exists()
    assert payload["schema_version"] == 1
    assert payload["stale"] is False
    assert payload["errors"] == []
    assert payload["underlying_price"] == pytest.approx(81000.0)
    assert len(payload["expiries"]) == 2
    assert payload["totals"]["option_oi_btc"] == pytest.approx(2800.0)
    assert payload["flow_read"]["bias"] == "defensive"
    assert "Deribit public book summary (keyless)" in payload["sources"]

    # load_payload round-trips
    assert oflow.load_payload(out) == payload

    # summary_for_status shape
    summary = oflow.summary_for_status(payload)
    assert summary["available"] is True
    assert summary["flow_read"]["bias"] == "defensive"
    assert summary["expiry_count"] == 2
    assert summary["stale"] is False


def test_refresh_never_raises_on_source_failure(tmp_path, monkeypatch):
    def _boom(url, timeout):
        raise RuntimeError("network down")
    monkeypatch.setattr(oflow, "_http_get_json", _boom)
    out = tmp_path / "options_flow.json"
    cache = tmp_path / "cache.json"
    payload = oflow.refresh(out_path=out, cache_path=cache)

    assert payload["stale"] is True
    assert payload["errors"]  # failures recorded, never raised
    assert payload["flow_read"]["bias"] == "neutral"
    assert out.exists()


def test_refresh_empty_result_is_stale(tmp_path, monkeypatch):
    _stub_http(monkeypatch, {"jsonrpc": "2.0", "result": []})
    out = tmp_path / "options_flow.json"
    cache = tmp_path / "cache.json"
    payload = oflow.refresh(out_path=out, cache_path=cache)
    assert payload["stale"] is True
    assert payload["expiries"] == []


def test_load_payload_missing_returns_empty(tmp_path):
    assert oflow.load_payload(tmp_path / "nope.json") == {}
    assert oflow.summary_for_status({}) == {"available": False}


def test_no_order_emission_or_secrets():
    # The module is advisory only: no broker/execution imports, no env secrets.
    src = Path(oflow.__file__).read_text(encoding="utf-8")
    for token in ("API_KEY", "API_SECRET", "SECRET_KEY", "place_order",
                  "submit_order", "create_order", "os.environ["):
        assert token not in src
