"""On-chain network intelligence tests — no live network.

All HTTP is stubbed by monkeypatching this module's ``_http_get_json`` /
``_http_get_text`` helpers, so every test runs against fixed fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import onchain as oc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FEES_FIXTURE = {
    "fastestFee": 2,
    "halfHourFee": 1,
    "hourFee": 1,
    "economyFee": 1,
    "minimumFee": 1,
}

MEMPOOL_BLOCKS_FIXTURE = [
    {"blockVSize": 997998.0, "nTx": 4155, "medianFee": 1.10,
     "feeRange": [0.46, 0.55, 0.57, 0.86, 2.0, 3.0, 140.49]},
    {"blockVSize": 997966.0, "nTx": 6559, "medianFee": 0.34,
     "feeRange": [0.30, 0.33, 0.35, 0.38, 0.42, 0.47, 0.52]},
    {"blockVSize": 997998.0, "nTx": 7119, "medianFee": 0.32,
     "feeRange": [0.30, 0.31, 0.31, 0.31, 0.32, 0.32, 0.32]},
    # Catch-all remainder bucket: far larger than one block, must be excluded
    # from the full-projected-block count.
    {"blockVSize": 33358667.0, "nTx": 45122, "medianFee": 0.12,
     "feeRange": [0.099, 0.11, 0.13, 0.15, 0.17, 0.19, 0.20]},
]

TIP_HEIGHT_TEXT = "967776"

HASHRATE_FIXTURE = {
    "status": "ok",
    "name": "Hash Rate",
    "unit": "Hash Rate TH/s",
    "values": [
        {"x": 1787529600, "y": 8.880543248996867e8},
        {"x": 1787616000, "y": 9.505933618644534e8},
        {"x": 1787702400, "y": 9.130699396855934e8},
    ],
}

DIFFICULTY_FIXTURE = {
    "status": "ok",
    "name": "Difficulty",
    "values": [
        {"x": 1787529600, "y": 1.25807076547198e14},
        {"x": 1787616000, "y": 1.25807076547198e14},
        {"x": 1787702400, "y": 1.2580707654719811e14},
    ],
}


def _stub_all(monkeypatch):
    def _get_json(url, timeout):
        if "fees/recommended" in url:
            return dict(FEES_FIXTURE)
        if "fees/mempool-blocks" in url:
            return [dict(b) for b in MEMPOOL_BLOCKS_FIXTURE]
        if "hash-rate" in url:
            return json.loads(json.dumps(HASHRATE_FIXTURE))
        if "difficulty" in url:
            return json.loads(json.dumps(DIFFICULTY_FIXTURE))
        raise AssertionError(f"unexpected url {url}")

    def _get_text(url, timeout):
        assert "tip/height" in url, f"unexpected url {url}"
        return TIP_HEIGHT_TEXT

    monkeypatch.setattr(oc, "_http_get_json", _get_json)
    monkeypatch.setattr(oc, "_http_get_text", _get_text)


# ---------------------------------------------------------------------------
# Fee pressure
# ---------------------------------------------------------------------------

def test_fee_pressure_thresholds():
    assert oc._fee_pressure_label(1) == "calm"
    assert oc._fee_pressure_label(4.99) == "calm"
    assert oc._fee_pressure_label(5) == "normal"
    assert oc._fee_pressure_label(19.9) == "normal"
    assert oc._fee_pressure_label(20) == "elevated"
    assert oc._fee_pressure_label(49.9) == "elevated"
    assert oc._fee_pressure_label(50) == "high"
    assert oc._fee_pressure_label(99.9) == "high"
    assert oc._fee_pressure_label(100) == "extreme"
    assert oc._fee_pressure_label(None) is None


def test_fetch_fees(monkeypatch):
    _stub_all(monkeypatch)
    fees = oc.fetch_fees()
    assert fees["fastest_sat_vb"] == 2.0
    assert fees["half_hour_sat_vb"] == 1.0
    assert fees["hour_sat_vb"] == 1.0
    assert fees["fee_pressure"] == "calm"


def test_fetch_fees_missing_fields(monkeypatch):
    monkeypatch.setattr(oc, "_http_get_json", lambda url, timeout: {})
    fees = oc.fetch_fees()
    assert fees["fastest_sat_vb"] is None
    assert fees["fee_pressure"] is None


# ---------------------------------------------------------------------------
# Mempool / congestion
# ---------------------------------------------------------------------------

def test_congestion_thresholds():
    assert oc._congestion_label(0) == "low"
    assert oc._congestion_label(2) == "low"
    assert oc._congestion_label(3) == "moderate"
    assert oc._congestion_label(5) == "moderate"
    assert oc._congestion_label(6) == "heavy"
    assert oc._congestion_label(8) == "heavy"


def test_fetch_mempool(monkeypatch):
    _stub_all(monkeypatch)
    mem = oc.fetch_mempool()
    # 3 full blocks at ~998k vB; the 33M vB catch-all bucket is NOT counted.
    assert mem["projected_blocks"] == 4
    assert mem["full_projected_blocks"] == 3
    assert mem["congestion"] == "moderate"
    assert mem["tip_height"] == 967776
    assert mem["median_fee_first_block_sat_vb"] == pytest.approx(1.10)


def test_fetch_mempool_empty(monkeypatch):
    monkeypatch.setattr(oc, "_http_get_json", lambda url, timeout: [])
    monkeypatch.setattr(oc, "_http_get_text", lambda url, timeout: "not-a-number")
    mem = oc.fetch_mempool()
    assert mem["projected_blocks"] == 0
    assert mem["full_projected_blocks"] == 0
    assert mem["congestion"] == "low"
    assert mem["tip_height"] is None
    assert mem["median_fee_first_block_sat_vb"] is None


# ---------------------------------------------------------------------------
# Network trends
# ---------------------------------------------------------------------------

def test_trend_pct():
    series = [(1, 100.0), (2, 110.0)]
    assert oc._trend_pct(series) == pytest.approx(10.0)
    assert oc._trend_pct([(1, 0.0), (2, 5.0)]) is None  # zero first point
    assert oc._trend_pct([(1, 100.0)]) is None  # single point
    assert oc._trend_pct([]) is None


def test_parse_chart_series_skips_bad_points():
    data = {"values": [
        {"x": 1, "y": 10.0},
        {"x": 2, "y": "nope"},
        {"x": 3},                       # missing y
        {"y": 12.0},                    # missing x
        {"x": 4, "y": float("inf")},    # non-finite
        {"x": 5, "y": 14.0},
    ]}
    series = oc._parse_chart_series(data)
    assert series == [(1, 10.0), (5, 14.0)]
    assert oc._parse_chart_series({}) == []
    assert oc._parse_chart_series(None) == []


def test_fetch_network(monkeypatch):
    _stub_all(monkeypatch)
    net = oc.fetch_network()
    hr = net["hashrate_th_s"]
    assert hr["latest"] == pytest.approx(9.130699396855934e8)
    # (9.130699396855934e8 - 8.880543248996867e8) / 8.880543248996867e8 * 100
    assert hr["change_30d_pct"] == pytest.approx(2.82, rel=1e-3)
    diff = net["difficulty"]
    assert diff["latest"] == pytest.approx(1.2580707654719811e14)
    assert diff["change_30d_pct"] == pytest.approx(0.0, abs=1e-6)


def test_fetch_network_raises_on_source_failure(monkeypatch):
    def _boom(url, timeout):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(oc, "_http_get_json", _boom)
    with pytest.raises(RuntimeError):
        oc.fetch_network()


# ---------------------------------------------------------------------------
# chain_read (bounded, intelligence-only)
# ---------------------------------------------------------------------------

def test_chain_read_strong_demand():
    read = oc.chain_read(
        {"fee_pressure": "elevated"},
        {"congestion": "heavy"},
        {"hashrate_th_s": {"change_30d_pct": 5.0}},
    )
    assert read["label"] == "strong_demand"
    assert read["bias"] == "constructive"
    assert "INTELLIGENCE ONLY" in read["disclaimer"]


def test_chain_read_cooling():
    read = oc.chain_read(
        {"fee_pressure": "calm"},
        {"congestion": "low"},
        {"hashrate_th_s": {"change_30d_pct": -5.0}},
    )
    assert read["label"] == "cooling"
    assert read["bias"] == "cautious"


def test_chain_read_steady_mixed_signals():
    # Elevated fees but falling hashrate: mixed, must stay neutral.
    read = oc.chain_read(
        {"fee_pressure": "extreme"},
        {"congestion": "heavy"},
        {"hashrate_th_s": {"change_30d_pct": -4.0}},
    )
    assert read["label"] == "steady"
    assert read["bias"] == "neutral"


def test_chain_read_missing_data_stays_neutral():
    read = oc.chain_read({}, {}, {})
    assert read["label"] == "steady"
    assert read["bias"] == "neutral"
    # Calm fees alone (no hashrate trend) is not "cooling".
    read2 = oc.chain_read({"fee_pressure": "calm"}, {}, {})
    assert read2["label"] == "steady"


# ---------------------------------------------------------------------------
# refresh / load_payload / summary_for_status
# ---------------------------------------------------------------------------

def test_refresh_writes_payload(monkeypatch, tmp_path):
    _stub_all(monkeypatch)
    out = tmp_path / "public" / "onchain_intel.json"
    payload = oc.refresh(out_path=out)
    assert out.exists()
    assert payload["schema_version"] == 1
    assert payload["stale"] is False
    assert payload["errors"] == []
    assert set(payload["fees"]) >= {"fastest_sat_vb", "fee_pressure"}
    assert payload["mempool"]["tip_height"] == 967776
    assert payload["network"]["hashrate_th_s"]["latest"] is not None
    assert payload["chain_read"]["label"] in ("strong_demand", "steady", "cooling")
    assert payload["sources"] == oc.SOURCES
    # Round-trip through the file.
    assert oc.load_payload(out)["ts"] == payload["ts"]


def test_refresh_never_raises_marks_stale(monkeypatch, tmp_path):
    def _boom(url, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr(oc, "_http_get_json", _boom)
    monkeypatch.setattr(oc, "_http_get_text", _boom)
    out = tmp_path / "onchain_intel.json"
    payload = oc.refresh(out_path=out)
    assert out.exists()
    assert payload["stale"] is True
    assert len(payload["errors"]) == 3  # fees, mempool, network each isolated
    assert payload["fees"] == {}
    assert payload["chain_read"]["label"] == "steady"


def test_refresh_partial_failure_only_marks_what_failed(monkeypatch, tmp_path):
    def _get_json(url, timeout):
        if "fees/recommended" in url:
            return dict(FEES_FIXTURE)
        raise RuntimeError("mempool-blocks down")

    monkeypatch.setattr(oc, "_http_get_json", _get_json)
    monkeypatch.setattr(oc, "_http_get_text",
                        lambda url, timeout: (_ for _ in ()).throw(RuntimeError("tip down")))
    payload = oc.refresh(out_path=tmp_path / "o.json")
    assert payload["stale"] is True
    assert payload["fees"]["fastest_sat_vb"] == 2.0
    assert any(e.startswith("mempool:") for e in payload["errors"])
    assert payload["mempool"] == {}


def test_load_payload_missing_returns_empty(tmp_path):
    assert oc.load_payload(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("not json {")
    assert oc.load_payload(bad) == {}


def test_summary_for_status():
    assert oc.summary_for_status({}) == {"available": False}
    payload = {
        "ts": "2026-09-19T00:00:00+00:00",
        "stale": False,
        "fees": {"fastest_sat_vb": 2.0, "fee_pressure": "calm"},
        "mempool": {"tip_height": 967776, "congestion": "moderate",
                    "full_projected_blocks": 3},
        "network": {"hashrate_th_s": {"latest": 9.1e8, "change_30d_pct": 2.8},
                     "difficulty": {"latest": 1.2e14, "change_30d_pct": 0.1}},
        "chain_read": {"label": "steady", "bias": "neutral"},
        "sources": ["a"],
    }
    s = oc.summary_for_status(payload)
    assert s["available"] is True
    assert s["fastest_fee_sat_vb"] == 2.0
    assert s["fee_pressure"] == "calm"
    assert s["tip_height"] == 967776
    assert s["congestion"] == "moderate"
    assert s["hashrate_th_s"] == 9.1e8
    assert s["hashrate_30d_pct"] == 2.8
    assert s["chain_read"]["label"] == "steady"
    assert s["stale"] is False
