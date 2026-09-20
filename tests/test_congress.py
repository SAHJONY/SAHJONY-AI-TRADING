"""Congress Intelligence Engine tests — no live network.

All parsing/normalization logic is exercised with fixture payloads; the
network legs (``_fetch_house_filings``, ``_fetch_senate_reports``) are
stubbed or their failure paths asserted without touching the wire.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import congress as cg  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HOUSE_HTML_FIXTURE = """
<table><tbody>
<tr role="row">
  <td data-label="Name" class="memberName">
    <a href="public_disc/ptr-pdfs/2026/20034201.pdf" target="_blank">Alford, Hon. Mark </a>
  </td>
  <td data-label="Office">MO04</td>
  <td data-label="Filing Year">2026</td>
  <td data-label="Filing">PTR Original</td>
</tr>
<tr role="row">
  <td data-label="Name" class="memberName">
    <a href="public_disc/ptr-pdfs/2026/20033751.pdf" target="_blank">Allen, Hon. Richard </a>
  </td>
  <td data-label="Office">GA12</td>
  <td data-label="Filing Year">2026</td>
  <td data-label="Filing">PTR Amendment</td>
</tr>
<tr role="row">
  <td data-label="Name" class="memberName">
    <a href="public_disc/fd-pdfs/2026/10012345.pdf" target="_blank">Barr, Hon. Andy </a>
  </td>
  <td data-label="Office">KY06</td>
  <td data-label="Filing Year">2026</td>
  <td data-label="Filing">FD Original</td>
</tr>
<tr role="row">
  <td data-label="Name" class="memberName">NoLink, Hon. Jane</td>
  <td data-label="Office">TX01</td>
  <td data-label="Filing Year">2026</td>
  <td data-label="Filing">PTR Original</td>
</tr>
</tbody></table>
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_house_ptr_rows_keeps_only_ptr():
    rows = cg._parse_house_ptr_rows(HOUSE_HTML_FIXTURE)
    # 2 PTR rows + 1 PTR row without a link; the FD Original row is excluded.
    assert len(rows) == 3
    assert all(r["filing_type"].startswith("PTR") for r in rows)
    assert all(r["chamber"] == "House" for r in rows)


def test_parse_house_ptr_rows_fields():
    rows = cg._parse_house_ptr_rows(HOUSE_HTML_FIXTURE)
    first = rows[0]
    assert first["member_name"] == "Alford, Hon. Mark"
    assert first["office"] == "MO04"
    assert first["filing_year"] == "2026"
    assert first["filing_type"] == "PTR Original"
    assert first["report_url"] == (
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034201.pdf"
    )
    assert first["granularity"] == "report"
    # Report-level: transaction detail is null, never estimated.
    assert first["asset"] is None
    assert first["transaction_type"] is None
    assert first["amount_range"] is None
    assert first["filed_date"] is None


def test_parse_house_ptr_rows_missing_link_is_none_not_crash():
    rows = cg._parse_house_ptr_rows(HOUSE_HTML_FIXTURE)
    nolink = [r for r in rows if r["member_name"] == "NoLink, Hon. Jane"][0]
    assert nolink["report_url"] is None


def test_parse_house_ptr_rows_empty_html():
    assert cg._parse_house_ptr_rows("") == []
    assert cg._parse_house_ptr_rows(None) == []


# ---------------------------------------------------------------------------
# Crypto screen
# ---------------------------------------------------------------------------

def test_crypto_screen_matches_known_assets():
    assert cg._is_crypto_related("Bitcoin purchase") is True
    assert cg._is_crypto_related("ETH", "some filing") is True
    assert cg._is_crypto_related("Grayscale Bitcoin Trust (GBTC)") is True


def test_crypto_screen_word_boundaries_no_false_positives():
    # "ETHAN" must not match "ETH"; "SOL" inside "CONSOLIDATED" must not match.
    assert cg._is_crypto_related("Ethan Allen Interiors") is False
    assert cg._is_crypto_related("Consolidated Edison Inc") is False
    assert cg._is_crypto_related("Apple Inc Common Stock") is False
    assert cg._is_crypto_related(None, "") is False


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _filing(name, chamber="House", ftype="PTR Original", crypto=False):
    return {
        "member_name": name,
        "chamber": chamber,
        "office": "XX00",
        "filing_year": "2026",
        "filing_type": ftype,
        "filed_date": None,
        "report_url": "https://example.invalid/r.pdf",
        "granularity": "report",
        "transaction_count": None,
        "asset": None,
        "transaction_type": None,
        "amount_range": None,
        "transaction_date": None,
        "crypto_flagged": crypto,
    }


def test_aggregate_counts_and_most_active():
    filings = [
        _filing("Alford, Hon. Mark"),
        _filing("Alford, Hon. Mark"),
        _filing("Allen, Hon. Richard", chamber="Senate"),
        _filing("Barr, Hon. Andy", ftype="PTR Amendment"),
    ]
    agg = cg._aggregate(filings)
    assert agg["filing_count"] == 4
    assert agg["by_chamber"] == {"House": 3, "Senate": 1}
    assert agg["by_filing_type"] == {"PTR Original": 3, "PTR Amendment": 1}
    assert agg["most_active_members"][0]["member_name"] == "Alford, Hon. Mark"
    assert agg["most_active_members"][0]["filings"] == 2


def test_aggregate_buy_sell_honestly_null():
    agg = cg._aggregate([_filing("Alford, Hon. Mark")])
    assert agg["buys"] is None
    assert agg["sells"] is None
    assert "report-level" in agg["buy_sell_note"]


def test_aggregate_crypto_count():
    filings = [_filing("A"), _filing("B", crypto=True)]
    assert cg._aggregate(filings)["crypto_flagged_count"] == 1


def test_aggregate_empty():
    agg = cg._aggregate([])
    assert agg["filing_count"] == 0
    assert agg["most_active_members"] == []


# ---------------------------------------------------------------------------
# refresh() failure isolation (no network)
# ---------------------------------------------------------------------------

def test_refresh_never_raises_and_marks_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "_fetch_house_filings",
                        lambda timeout=40.0: (_ for _ in ()).throw(RuntimeError("net down")))
    monkeypatch.setattr(cg, "_fetch_senate_reports",
                        lambda timeout=30.0: (_ for _ in ()).throw(RuntimeError("503")))
    out = tmp_path / "congress_trades.json"
    payload = cg.refresh(out_path=out, cache_path=tmp_path / "cache.json")
    assert payload["stale"] is True
    assert len(payload["errors"]) == 2
    assert any("house" in e for e in payload["errors"])
    assert any("senate" in e for e in payload["errors"])
    # Atomic write still happened.
    assert json.loads(out.read_text())["stale"] is True


def test_refresh_success_writes_payload(monkeypatch, tmp_path):
    rows = [_filing("Alford, Hon. Mark"), _filing("Lee, Hon. Mike", chamber="Senate")]
    monkeypatch.setattr(cg, "fetch_house_filings", lambda cache_path=None, timeout=40.0: [rows[0]])
    monkeypatch.setattr(cg, "_fetch_senate_reports", lambda timeout=30.0: [rows[1]])
    out = tmp_path / "congress_trades.json"
    payload = cg.refresh(out_path=out, cache_path=tmp_path / "cache.json")
    assert payload["stale"] is False
    assert payload["errors"] == []
    assert payload["aggregates"]["filing_count"] == 2
    assert "30 days" in payload["data_lag_note"] or "30-45" in payload["data_lag_note"]
    assert payload["sources"] == list(cg.SOURCES)


def test_fetch_house_filings_falls_back_to_stale_cache(monkeypatch, tmp_path):
    cache = tmp_path / "cache.json"
    cached_rows = [_filing("Cached, Hon. Member")]
    cache.write_text(json.dumps({"ts": "2026-01-01T00:00:00+00:00", "rows": cached_rows}))
    monkeypatch.setattr(cg, "_fetch_house_filings",
                        lambda timeout=40.0: (_ for _ in ()).throw(RuntimeError("net down")))
    rows = cg.fetch_house_filings(cache_path=cache)
    assert rows == cached_rows


# ---------------------------------------------------------------------------
# load_payload / summary_for_status
# ---------------------------------------------------------------------------

def test_load_payload_missing_returns_empty(tmp_path):
    assert cg.load_payload(tmp_path / "nope.json") == {}


def test_summary_for_status_compact(tmp_path):
    rows = [_filing("Alford, Hon. Mark"), _filing("Alford, Hon. Mark")]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cg, "fetch_house_filings", lambda cache_path=None, timeout=40.0: rows)
    monkeypatch.setattr(cg, "_fetch_senate_reports", lambda timeout=30.0: [])
    out = tmp_path / "congress_trades.json"
    payload = cg.refresh(out_path=out, cache_path=tmp_path / "cache.json")
    summary = cg.summary_for_status(payload)
    assert summary["available"] is True
    assert summary["filing_count"] == 2
    assert summary["top_active_member"]["name"] == "Alford, Hon. Mark"
    assert summary["top_active_member"]["filings"] == 2
    assert summary["stale"] is False
    monkeypatch.undo()


def test_summary_for_status_empty_payload():
    assert cg.summary_for_status({}) == {"available": False}
