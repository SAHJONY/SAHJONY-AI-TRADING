"""News / Sentiment Intelligence Engine tests — no live network.

All parsing/normalization logic is exercised with fixture payloads; the
network legs (``_http_get_json``) are stubbed via monkeypatch or their
failure paths are asserted through ``refresh()`` with patched fetchers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import news  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures (shaped like the real payloads verified live 2026-09-19)
# ---------------------------------------------------------------------------

FNG_FIXTURE = {
    "name": "Fear and Greed Index",
    "data": [
        {"value": "71", "value_classification": "Greed", "timestamp": "1789862400",
         "time_until_update": "80824"},
        {"value": "56", "value_classification": "Greed", "timestamp": "1789689600"},
        {"value": "57", "value_classification": "Greed", "timestamp": "1789344000"},
    ],
    "metadata": {"error": None},
}

GDELT_FIXTURE = {
    "timeline": [
        {"series": "Search Results",
         "data": [
             {"date": "20260913000000", "volume": 100},
             {"date": "20260914000000", "volume": 110},
             {"date": "20260915000000", "volume": 90},
             {"date": "20260916000000", "volume": 105},
             {"date": "20260917000000", "volume": 115},
             {"date": "20260918000000", "volume": 100},
             {"date": "20260919000000", "volume": 400},
         ]},
    ]
}

TRENDING_FIXTURE = {
    "coins": [
        {"item": {"id": "zcoin", "name": "Firo", "symbol": "FIRO",
                  "market_cap_rank": 812}},
        {"item": {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC",
                  "market_cap_rank": 1}},
    ],
    "exchanges": [],
}


# ---------------------------------------------------------------------------
# Fear & Greed parsing
# ---------------------------------------------------------------------------

def test_parse_fng_value_classification_and_delta():
    fg = news._parse_fng(FNG_FIXTURE)
    assert fg["value"] == 71.0
    assert fg["classification"] == "Greed"
    assert fg["delta_7d"] == 14.0  # 71 - 57
    assert len(fg["history"]) == 3


def test_parse_fng_empty_is_none_not_invented():
    fg = news._parse_fng({})
    assert fg["value"] is None
    assert fg["classification"] is None
    assert fg["delta_7d"] is None
    assert fg["history"] == []


def test_parse_fng_malformed_values():
    fg = news._parse_fng({"data": [{"value": "n/a", "value_classification": "X"}]})
    assert fg["value"] is None
    assert fg["classification"] == "X"
    assert fg["delta_7d"] is None


# ---------------------------------------------------------------------------
# GDELT timelinevol parsing
# ---------------------------------------------------------------------------

def test_parse_gdelt_spike():
    e = news._parse_gdelt_timelinevol(GDELT_FIXTURE)
    assert e["count_24h"] == 400.0
    assert e["days_sampled"] == 7
    assert e["count_7d_avg"] == pytest.approx(145.71, abs=0.01)
    assert e["spike_ratio"] == pytest.approx(400 / 145.714, abs=0.01)


def test_parse_gdelt_zero_baseline_no_invented_ratio():
    e = news._parse_gdelt_timelinevol(
        {"timeline": [{"data": [{"volume": 0}, {"volume": 0}]}]})
    assert e["count_24h"] == 0.0
    assert e["count_7d_avg"] == 0.0
    assert e["spike_ratio"] is None  # 0 baseline -> no ratio, never invented


def test_parse_gdelt_empty():
    e = news._parse_gdelt_timelinevol({})
    assert e["count_24h"] is None
    assert e["days_sampled"] == 0


# ---------------------------------------------------------------------------
# CoinGecko trending parsing
# ---------------------------------------------------------------------------

def test_parse_trending_names_symbols_only():
    coins = news._parse_trending(TRENDING_FIXTURE)
    assert coins == [
        {"name": "Firo", "symbol": "FIRO", "id": "zcoin", "market_cap_rank": 812},
        {"name": "Bitcoin", "symbol": "BTC", "id": "bitcoin", "market_cap_rank": 1},
    ]


def test_parse_trending_cap_and_empty():
    coins = news._parse_trending(TRENDING_FIXTURE, cap=1)
    assert len(coins) == 1
    assert news._parse_trending({}) == []


# ---------------------------------------------------------------------------
# Bounded sentiment read
# ---------------------------------------------------------------------------

def _read(value, spikes=()):
    vol = [{"query": q, "spike": True} for q in spikes]
    return news.sentiment_read({"value": value, "classification": "x"}, vol)


def test_sentiment_extreme_fear_contrarian():
    r = _read(15)
    assert r["fear_greed_label"] == "extreme_fear"
    assert r["bias"] == "mildly_bullish_contrarian"
    assert r["label"].startswith("INTELLIGENCE ONLY")


def test_sentiment_extreme_greed_cautious():
    r = _read(85)
    assert r["fear_greed_label"] == "extreme_greed"
    assert r["bias"] == "cautious_bearish"


def test_sentiment_bands():
    assert _read(30)["bias"] == "cautious_bullish"
    assert _read(50)["bias"] == "neutral"
    assert _read(70)["bias"] == "cautious"


def test_sentiment_no_reading_neutral():
    r = _read(None)
    assert r["fear_greed_label"] == "no_reading"
    assert r["bias"] == "neutral"


def test_sentiment_spike_queries_listed():
    r = _read(50, spikes=("bitcoin",))
    assert r["spike_queries"] == ["bitcoin"]


# ---------------------------------------------------------------------------
# refresh() orchestration — stubbed network, never raises
# ---------------------------------------------------------------------------

def _patch_fetchers(monkeypatch, gdelt_fail=False, fng_fail=False,
                    trend_fail=False):
    monkeypatch.setattr(
        news, "fetch_fear_greed",
        lambda timeout=10: (_ for _ in ()).throw(RuntimeError("boom"))
        if fng_fail else {"value": 71.0, "classification": "Greed",
                          "delta_7d": 14.0, "history": []})
    monkeypatch.setattr(
        news, "fetch_news_volume",
        lambda query, timeout=20: (_ for _ in ()).throw(ConnectionError("empty"))
        if gdelt_fail else {"query": query, "count_24h": 400.0,
                            "count_7d_avg": 145.71, "spike_ratio": 2.75,
                            "days_sampled": 7, "spike": True})
    monkeypatch.setattr(
        news, "fetch_trending_coins",
        lambda timeout=10: (_ for _ in ()).throw(RuntimeError("429"))
        if trend_fail else [{"name": "Firo", "symbol": "FIRO", "id": "zcoin",
                             "market_cap_rank": 812}])
    # NOTE: the engine's manual GDELT time.sleep pacing was replaced by the
    # shared client's token bucket (intel/keyless_http.py), so there is no
    # sleep to patch out here anymore.


def _refresh_to(tmp_path, monkeypatch, **fail):
    _patch_fetchers(monkeypatch, **fail)
    out = tmp_path / "news_intel.json"
    return news.refresh(out_path=out)


def test_refresh_all_live_payload_shape(tmp_path, monkeypatch):
    p = _refresh_to(tmp_path, monkeypatch)
    assert p["schema_version"] == 1
    assert p["stale"] is False
    assert p["errors"] == []
    assert p["fear_greed"]["value"] == 71.0
    assert len(p["news_volume"]) == 3
    assert all(v["query"] for v in p["news_volume"])
    assert p["trending_coins"][0]["symbol"] == "FIRO"
    assert p["sentiment_read"]["bias"] == "cautious"
    assert set(p["sources"]) == set(news.SOURCES)
    # written atomically to disk
    assert news.load_payload(tmp_path / "news_intel.json")["ts"] == p["ts"]


def test_refresh_partial_failure_stale_not_raising(tmp_path, monkeypatch):
    p = _refresh_to(tmp_path, monkeypatch, gdelt_fail=True, trend_fail=True)
    assert p["stale"] is True
    assert any("news_volume[bitcoin]" in e for e in p["errors"])
    assert any(e.startswith("trending:") for e in p["errors"])
    assert p["fear_greed"]["value"] == 71.0  # good legs still populate
    assert p["news_volume"][0]["count_24h"] is None  # failed leg: None, never invented
    assert p["trending_coins"] == []
    assert p["sentiment_read"]["bias"] == "cautious"


def test_refresh_total_failure_never_raises(tmp_path, monkeypatch):
    p = _refresh_to(tmp_path, monkeypatch, gdelt_fail=True, fng_fail=True,
                    trend_fail=True)
    assert p["stale"] is True
    assert len(p["errors"]) == 1 + 3 + 1
    assert p["fear_greed"]["value"] is None
    assert p["sentiment_read"]["bias"] == "neutral"


# ---------------------------------------------------------------------------
# load_payload / summary_for_status
# ---------------------------------------------------------------------------

def test_load_payload_missing_is_empty(tmp_path):
    assert news.load_payload(tmp_path / "nope.json") == {}


def test_summary_for_status(tmp_path, monkeypatch):
    p = _refresh_to(tmp_path, monkeypatch)
    s = news.summary_for_status(p)
    assert s["available"] is True
    assert s["fear_greed"]["value"] == 71.0
    assert s["sentiment"]["bias"] == "cautious"
    assert s["sentiment"]["spike_queries"] == ["bitcoin", "ethereum",
                                              "cryptocurrency"]
    assert s["volume_spikes"] == 3
    assert s["trending_coins"] == ["FIRO"]
    assert s["stale"] is False


def test_summary_for_status_empty():
    assert news.summary_for_status({}) == {"available": False}
