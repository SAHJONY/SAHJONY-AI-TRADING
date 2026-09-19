"""Top Traders Tracker tests — no live network.

All HTTP is stubbed by monkeypatching this module's ``_http_get_json`` /
``_http_post_json`` helpers (and ``requests.get`` where the SEC XML document
is fetched directly).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import top_traders as tt  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LEADERBOARD_FIXTURE = {
    "leaderboardRows": [
        {
            "ethAddress": "0xaaa111aaa111aaa111aaa111aaa111aaa111aaa1",
            "displayName": "WhaleKing",
            "accountValue": "2500000",
            "windowPerformances": [
                ["day", {"pnl": "5000", "roi": "0.002", "vlm": "100000"}],
                ["week", {"pnl": "40000", "roi": "0.016", "vlm": "800000"}],
                ["month", {"pnl": "120000", "roi": "0.05", "vlm": "3000000"}],
                ["allTime", {"pnl": "900000", "roi": "0.4", "vlm": "20000000"}],
            ],
        },
        {
            "ethAddress": "0xbbb222bbb222bbb222bbb222bbb222bbb222bbb2",
            "displayName": None,
            "accountValue": "800000",
            "windowPerformances": [
                ["day", {"pnl": "-1000", "roi": "-0.001", "vlm": "50000"}],
                ["week", {"pnl": "10000", "roi": "0.012", "vlm": "400000"}],
                ["month", {"pnl": "450000", "roi": "0.6", "vlm": "5000000"}],
                ["allTime", {"pnl": "450000", "roi": "0.6", "vlm": "5000000"}],
            ],
        },
    ]
}

INFO_TABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <value>150000</value>
    <shrsOrPrnAmt><sshPrnamt>500000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>BANK OF AMERICA CORP</nameOfIssuer>
    <value>90000</value>
    <shrsOrPrnAmt><sshPrnamt>2000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


def _clearing_state(*, btc=None, eth=None):
    positions = []
    if btc is not None:
        positions.append({"position": {"coin": "BTC", "szi": str(btc)}})
    if eth is not None:
        positions.append({"position": {"coin": "ETH", "szi": str(eth)}})
    return {"assetPositions": positions}


# ---------------------------------------------------------------------------
# Leaderboard parsing / ranking
# ---------------------------------------------------------------------------

def test_leaderboard_parsing_and_null_display_name(monkeypatch, tmp_path):
    monkeypatch.setattr(tt, "_http_get_json", lambda url, timeout, headers=None: LEADERBOARD_FIXTURE)
    rows = tt.fetch_leaderboard(cache_path=tmp_path / "cache.json")
    assert len(rows) == 2

    named, anon = rows
    assert named["display_name"] == "WhaleKing"
    assert named["pnl_month"] == pytest.approx(120000.0)
    assert named["roi_month"] == pytest.approx(0.05)
    assert named["account_value"] == pytest.approx(2_500_000.0)

    # displayName null is preserved (alias fallback happens at ranking time)
    assert anon["display_name"] is None
    assert anon["pnl_month"] == pytest.approx(450000.0)

    # cache was written and is reused when the network dies
    def _boom(url, timeout, headers=None):
        raise ConnectionError("offline")

    monkeypatch.setattr(tt, "_http_get_json", _boom)
    rows2 = tt.fetch_leaderboard(cache_path=tmp_path / "cache.json")
    assert rows2 == rows


def test_leaderboard_failure_no_cache_returns_empty(monkeypatch, tmp_path):
    def _boom(url, timeout, headers=None):
        raise ConnectionError("offline")

    monkeypatch.setattr(tt, "_http_get_json", _boom)
    assert tt.fetch_leaderboard(cache_path=tmp_path / "missing.json") == []


def test_ranking_by_pnl_month_desc(monkeypatch, tmp_path):
    monkeypatch.setattr(tt, "_http_get_json", lambda url, timeout, headers=None: LEADERBOARD_FIXTURE)
    ranked = tt.top_traders(n=20, cache_path=tmp_path / "cache.json")
    assert [t["rank"] for t in ranked] == [1, 2]
    # 0xbbb… has the larger month pnl → rank 1, with shortened wallet alias
    assert ranked[0]["alias_or_wallet"].startswith("0xbbb2")
    assert ranked[0]["alias_or_wallet"].endswith("bbb2")
    assert ranked[0]["pnl"] == pytest.approx(450000.0)
    assert ranked[0]["win_rate"] is None  # source does not provide it — honest null
    assert ranked[0]["venue"] == "Hyperliquid"
    assert ranked[0]["period"] == "30d"
    assert ranked[1]["alias_or_wallet"] == "WhaleKing"


# ---------------------------------------------------------------------------
# Aggregate positioning / copy signal
# ---------------------------------------------------------------------------

def test_aggregate_positioning_two_long_one_short(monkeypatch):
    states = {
        "0xa": _clearing_state(btc="1.5", eth="10"),
        "0xb": _clearing_state(btc="0.25", eth="-5"),
        "0xc": _clearing_state(btc="-2.0", eth="0"),  # short BTC, flat ETH
    }

    def fake_post(url, payload, timeout):
        return states[payload["user"]]

    monkeypatch.setattr(tt, "_http_post_json", fake_post)
    agg = tt.aggregate_positioning(["0xa", "0xb", "0xc"])

    btc, eth = agg["BTC"], agg["ETH"]
    assert (btc["long"], btc["short"], btc["flat"]) == (2, 1, 0)
    assert btc["pct_long"] == pytest.approx(66.7, abs=0.1)
    assert (eth["long"], eth["short"], eth["flat"]) == (1, 1, 1)
    assert eth["pct_long"] == pytest.approx(50.0)
    assert agg["sampled"] == 3
    assert agg["errors"] == 0
    assert agg["ts"]


def test_aggregate_positioning_counts_errors(monkeypatch):
    def fake_post(url, payload, timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr(tt, "_http_post_json", fake_post)
    agg = tt.aggregate_positioning(["0xa"])
    assert agg["sampled"] == 0
    assert agg["errors"] == 1


def test_copy_signal_bias_logic():
    long_agg = {"BTC": {"pct_long": 80.0}, "ETH": {"pct_long": 70.0}}
    sig = tt.copy_signal(long_agg)
    assert sig["net_bias"] == "long"
    assert sig["label"].startswith("INTELLIGENCE ONLY")

    short_agg = {"BTC": {"pct_long": 20.0}, "ETH": {"pct_long": 30.0}}
    assert tt.copy_signal(short_agg)["net_bias"] == "short"

    mixed_agg = {"BTC": {"pct_long": 80.0}, "ETH": {"pct_long": 30.0}}
    assert tt.copy_signal(mixed_agg)["net_bias"] == "mixed"

    boundary = {"BTC": {"pct_long": 55.0}, "ETH": {"pct_long": 55.0}}
    assert tt.copy_signal(boundary)["net_bias"] == "mixed"  # strict >55 / <45

    assert tt.copy_signal({})["net_bias"] == "mixed"  # missing data → neutral


def test_copy_signal_no_directional_positions_is_mixed_not_short():
    # 0% long with zero directional positions is NO signal, not bearish.
    flat_agg = {"BTC": {"pct_long": 0.0, "long": 0, "short": 0, "flat": 20},
                "ETH": {"pct_long": 0.0, "long": 0, "short": 0, "flat": 20},
                "sampled": 20, "errors": 0}
    assert tt.copy_signal(flat_agg)["net_bias"] == "mixed"


def test_refresh_positions_sample_top_ranked_traders(monkeypatch, tmp_path):
    # aggregate_positioning must sample the top-20 by 30d PnL, not the raw
    # leaderboard order (account-value sorted).
    rows = [
        {"eth_address": "0xpoor", "display_name": None, "account_value": 99999999.0,
         "pnl_day": 0.0, "pnl_week": 0.0, "pnl_month": 1.0, "pnl_alltime": 0.0, "roi_month": 0.0},
        {"eth_address": "0xrich", "display_name": None, "account_value": 1.0,
         "pnl_day": 0.0, "pnl_week": 0.0, "pnl_month": 500000.0, "pnl_alltime": 0.0, "roi_month": 0.0},
    ]
    monkeypatch.setattr(tt, "fetch_leaderboard", lambda cache_path=None, ttl_s=0, timeout=30: rows)
    seen = []
    monkeypatch.setattr(tt, "aggregate_positioning",
                        lambda addresses, timeout=10: seen.extend(addresses) or
                        {"BTC": {"pct_long": 50.0, "long": 0, "short": 0, "flat": 0},
                         "ETH": {"pct_long": 50.0, "long": 0, "short": 0, "flat": 0},
                         "sampled": 0, "errors": 0, "ts": "t"})
    monkeypatch.setattr(tt, "fetch_whale_alerts", lambda **k: [])
    monkeypatch.setattr(tt, "fetch_13f_holdings", lambda **k: [])
    out = tmp_path / "out.json"
    tt.refresh(out_path=out, cache_path=tmp_path / "cache.json")
    assert seen and seen[0] == "0xrich"  # ranked-first, not raw-first


# ---------------------------------------------------------------------------
# Whale alerts
# ---------------------------------------------------------------------------

def test_whale_filter_excludes_below_threshold(monkeypatch):
    txs = [
        {"txid": "big1", "value": 2_000_000_000, "vsize": 200, "fee": 1000},   # 20 BTC
        {"txid": "small1", "value": 1_000_000, "vsize": 200, "fee": 500},    # 0.01 BTC
        {"txid": "big2", "value": 100_000_000_000, "vsize": 500, "fee": 9},  # 1000 BTC
    ]
    monkeypatch.setattr(tt, "_http_get_json", lambda url, timeout, headers=None: txs)

    alerts = tt.fetch_whale_alerts(btc_price_usd=100_000.0, threshold_usd=1_000_000)
    txids = [a["txid"] for a in alerts]
    assert "small1" not in txids  # 0.01 BTC * $100k = $1k < $1M threshold
    assert txids == ["big1", "big2"]  # newest-first order preserved

    big1 = alerts[0]
    assert big1["asset"] == "BTC"
    assert big1["amount_btc"] == pytest.approx(20.0)
    assert big1["amount_usd"] == pytest.approx(2_000_000.0)
    assert big1["from"] is None and big1["to"] is None  # not provided — never invented
    assert big1["source"] == "mempool.space"

    # cap at 20
    many = [{"txid": f"t{i}", "value": 100_000_000_000, "vsize": 1, "fee": 1} for i in range(30)]
    monkeypatch.setattr(tt, "_http_get_json", lambda url, timeout, headers=None: many)
    assert len(tt.fetch_whale_alerts(btc_price_usd=100_000.0)) == 20


# ---------------------------------------------------------------------------
# 13F parsing
# ---------------------------------------------------------------------------

def test_13f_xml_parsing_values_x1000():
    positions = tt._parse_infotable_xml(INFO_TABLE_XML)
    assert len(positions) == 2
    # sorted desc by value; values converted from $000s → USD
    assert positions[0]["issuer"] == "APPLE INC"
    assert positions[0]["value_usd"] == pytest.approx(150_000_000.0)
    assert positions[0]["shares"] == 500_000
    assert positions[1]["issuer"] == "BANK OF AMERICA CORP"
    assert positions[1]["value_usd"] == pytest.approx(90_000_000.0)


def test_13f_unit_resolution_dollar_filer_and_issuer_aggregation():
    # Berkshire-style filing: <value> in dollars, not $000s (implied share
    # price $338 is sane; $338,264 is not). Same issuer across two managers
    # must aggregate into one position.
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>AMERICAN EXPRESS CO</nameOfIssuer>
    <value>50419898471</value>
    <shrsOrPrnAmt><sshPrnamt>149061045</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>AMERICAN EXPRESS CO</nameOfIssuer>
    <value>388967882</value>
    <shrsOrPrnAmt><sshPrnamt>1149942</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""
    positions = tt._parse_infotable_xml(xml)
    assert len(positions) == 1
    assert positions[0]["issuer"] == "AMERICAN EXPRESS CO"
    # dollars, not thousands: ~$50.8B, never $50.8T
    assert positions[0]["value_usd"] == pytest.approx(50_808_866_353.0)
    assert positions[0]["shares"] == 150_210_987


def test_13f_fund_flow_and_failed_fund_skipped(monkeypatch):
    monkeypatch.setattr(tt, "TRACKED_FUNDS", [("Good Fund", "0000000001"), ("Bad Fund", "0000000002")])
    monkeypatch.setattr(time, "sleep", lambda s: None)  # skip SEC courtesy pacing in tests

    def fake_get(url, timeout, headers=None):
        if "submissions" in url:
            cik = url.split("CIK")[1].split(".")[0]
            if cik == "0000000002":
                raise ConnectionError("SEC timeout")
            return {
                "filings": {
                    "recent": {
                        "form": ["13F-HR", "4"],
                        "accessionNumber": ["0000000001-26-000001", "0000000001-26-000002"],
                        "filingDate": ["2026-08-14", "2026-08-10"],
                        "reportDate": ["2026-06-30", "2026-06-30"],
                    }
                }
            }
        if "index.json" in url:
            return {"directory": {"item": [{"name": "infotable.xml"}, {"name": "cover.xml"}]}}
        raise AssertionError(f"unexpected url {url}")

    class _Resp:
        text = INFO_TABLE_XML

        def raise_for_status(self):
            pass

    monkeypatch.setattr(tt, "_http_get_json", fake_get)
    monkeypatch.setattr(tt.requests, "get", lambda url, timeout, headers=None: _Resp())

    errors: list = []
    holdings = tt.fetch_13f_holdings(errors=errors)

    assert len(holdings) == 1  # bad fund skipped, never invented
    fund = holdings[0]
    assert fund["fund"] == "Good Fund"
    assert fund["cik"] == "0000000001"
    assert fund["filing_date"] == "2026-08-14"
    assert fund["period_end"] == "2026-06-30"
    assert fund["source"] == "SEC EDGAR 13F-HR"
    assert fund["top_positions"][0]["issuer"] == "APPLE INC"
    assert any("Bad Fund" in e for e in errors)

    # mandatory SEC user agent header is sent
    sent = {}

    def capture_get(url, timeout, headers=None):
        sent.update(headers or {})
        return _Resp()

    monkeypatch.setattr(tt.requests, "get", capture_get)
    monkeypatch.setattr(tt, "_http_get_json", lambda url, timeout, headers=None: sent.update(headers or {}) or fake_get(url, timeout, headers))
    tt.fetch_13f_holdings(errors=[])
    assert sent.get("User-Agent") == tt.SEC_USER_AGENT


# ---------------------------------------------------------------------------
# refresh / load_payload / summary
# ---------------------------------------------------------------------------

def test_refresh_all_sources_failing_is_stale_not_exception(monkeypatch, tmp_path):
    def _boom(*a, **k):
        raise ConnectionError("offline")

    monkeypatch.setattr(tt, "_http_get_json", _boom)
    monkeypatch.setattr(tt, "_http_post_json", _boom)
    monkeypatch.setattr(tt.requests, "get", _boom)

    out = tmp_path / "public" / "top_traders.json"
    payload = tt.refresh(out_path=out, cache_path=tmp_path / "cache.json")

    assert payload["schema_version"] == 1
    assert payload["stale"] is True
    assert len(payload["errors"]) >= 3  # leaderboard, whales, 13f all recorded
    assert set(payload) >= {
        "schema_version", "ts", "stale", "errors", "traders",
        "aggregate_positioning", "copy_signal", "whale_alerts",
        "fund_holdings", "sources",
    }
    assert payload["sources"] == tt.SOURCES
    assert out.exists()

    # written file round-trips through load_payload
    assert tt.load_payload(out) == payload

    summary = tt.summary_for_status(payload)
    assert summary["available"] is True
    assert summary["stale"] is True
    assert summary["trader_count"] == 0
    assert summary["funds_tracked"] == 0


def test_load_payload_missing_file_returns_empty(tmp_path):
    assert tt.load_payload(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert tt.load_payload(bad) == {}


def test_summary_for_status_empty_payload():
    assert tt.summary_for_status({}) == {"available": False}


def test_refresh_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr(tt, "_http_get_json", lambda url, timeout, headers=None: (
        LEADERBOARD_FIXTURE if "hyperliquid" in url else []
    ))
    monkeypatch.setattr(tt, "_http_post_json", lambda url, payload, timeout: _clearing_state(btc="1.0", eth="-2.0"))
    monkeypatch.setattr(tt, "fetch_whale_alerts", lambda **k: [{"asset": "BTC", "txid": "x"}])
    monkeypatch.setattr(tt, "fetch_13f_holdings", lambda timeout=10, errors=None: [{"fund": "F"}])

    out = tmp_path / "top_traders.json"
    payload = tt.refresh(out_path=out, cache_path=tmp_path / "cache.json")

    assert payload["stale"] is False
    assert payload["errors"] == []
    assert len(payload["traders"]) == 2
    assert payload["aggregate_positioning"]["sampled"] == 2
    assert payload["copy_signal"]["net_bias"] == "mixed"  # BTC 100% long, ETH 100% short
    assert payload["whale_alerts"] == [{"asset": "BTC", "txid": "x"}]
    assert payload["fund_holdings"] == [{"fund": "F"}]

    summary = tt.summary_for_status(payload)
    assert summary["top_trader"]["alias"] == payload["traders"][0]["alias_or_wallet"]
    assert summary["whale_alert_count"] == 1
    assert summary["funds_tracked"] == 1
    assert summary["stale"] is False
