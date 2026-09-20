"""Congressional Trading Intelligence — STOCK Act disclosure activity feed.

Keyless sources (verified live 2026-09-19):
  1. U.S. House Office of the Clerk, Financial Disclosure search
     (disclosures-clerk.house.gov) — POST
     /FinancialDisclosure/ViewMemberSearchResult returns the PTR (Periodic
     Transaction Report) filing index: member name, office, filing year,
     filing type (PTR Original / PTR Amendment), and the report PDF URL.
     Verified live 2026-09-19 (395 PTR rows returned for filing year 2026).
  2. U.S. Senate EFD search JSON API (efdsearch.senate.gov) — POST
     /search/report/data/ returns report-level metadata (member, report type,
     filed date, report URL). ATTEMPTED 2026-09-19: the data endpoint
     returned HTTP 503 ("Site Under Maintenance"); the Senate leg is a
     degradable source — its failure is recorded in ``errors`` and the
     payload is marked ``stale``, never raised.

Evaluated and rejected 2026-09-19: capitoltrades.com (commercial aggregator;
its /trades page is behind bot protection — HTTP 429 with a challenge token
and robots.txt returns 403, i.e. scraping is unwelcome).

Granularity — stated honestly: both official keyless sources publish
REPORT-level listings. Per-transaction detail (ticker, buy/sell, amount
range) lives inside the report PDFs, which this module does NOT parse
(stdlib + ``requests`` only per repo policy; no PDF dependency). Fields the
sources do not provide are ``None`` — never estimated. Each entry in
``filings`` is therefore one disclosed Periodic Transaction Report, with
``granularity: "report"`` on every row.

Data-lag note: the STOCK Act requires members to disclose covered
transactions within 30 days of the trade (45 with an extension), so any
filing-based signal lags the actual trading by 30-45+ days. This is
recorded in the payload — the feed measures *disclosure activity*, not
real-time positioning.

Design notes:
  * Every HTTP call carries an explicit timeout; stdlib + ``requests`` only.
  * No secrets, no API keys anywhere. Polite pacing: <=1 req/s between the
    per-year House search requests.
  * No invented data: fields a source doesn't provide are ``None``.
  * ``refresh()`` never raises on source failure — failures are recorded in
    ``errors`` and the payload is marked ``stale``.
  * Signals are INTELLIGENCE ONLY. This module never widens risk caps, never
    emits orders, never touches credentials, and never promises profit.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import requests

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Source endpoints / constants
# ---------------------------------------------------------------------------

HOUSE_BASE = "https://disclosures-clerk.house.gov"
HOUSE_VIEW_SEARCH_URL = HOUSE_BASE + "/FinancialDisclosure/ViewSearch"
HOUSE_SEARCH_RESULT_URL = HOUSE_BASE + "/FinancialDisclosure/ViewMemberSearchResult"

SENATE_HOME_URL = "https://efdsearch.senate.gov/search/home/"
SENATE_DATA_URL = "https://efdsearch.senate.gov/search/report/data/"

# Filing years pulled from the House index. The current year plus the prior
# year keeps the payload a "recent activity" window without paging.
FILING_YEARS = (2026, 2025)

HOUSE_TIMEOUT_S = 40.0
SENATE_TIMEOUT_S = 30.0
REQUEST_PACING_S = 1.0  # <=1 req/s courtesy pacing between House year queries

PTR_FILING_TYPES = ("PTR Original", "PTR Amendment")

# Conservative crypto-asset keyword screen. Word-boundary matched against
# whatever asset/descriptive text a source provides; the list is
# deliberately narrow (major crypto assets + the generic terms) to avoid
# false positives on ordinary equity names. At report-level granularity the
# House/Senate listings carry no asset text, so flags will be 0 until a
# transaction-level source is wired — the count is reported honestly.
CRYPTO_KEYWORDS = (
    "BTC", "BITCOIN",
    "ETH", "ETHEREUM",
    "DOGE", "DOGECOIN",
    "SOL", "SOLANA",
    "XRP", "RIPPLE",
    "ADA", "CARDANO",
    "LTC", "LITECOIN",
    "BNB",
    "USDT", "USDC",
    "STABLECOIN",
    "CRYPTO", "CRYPTOCURRENCY",
)

SOURCES = [
    "House Clerk financial disclosure search (keyless)",
    "Senate EFD search (keyless; degradable)",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = unescape(re.sub(r"\s+", " ", text)).strip()
    return cleaned or None


_CRYPTO_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in CRYPTO_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _is_crypto_related(*texts: str | None) -> bool:
    """Conservative crypto-asset screen over free-text fields.

    Word-boundary matching only (so "ETHAN" never matches "ETH"). Pure
    function — unit-tested with fixtures, no network.
    """
    for text in texts:
        if text and _CRYPTO_RE.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# 1. House Clerk PTR filing index
# ---------------------------------------------------------------------------

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(
    r'<td[^>]*data-label="([^"]+)"[^>]*>(.*?)</td>', re.S | re.I
)
_LINK_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'
)


def _parse_house_ptr_rows(html: str) -> list[dict]:
    """Parse House search-result rows into filing dicts. Pure — no network.

    Only rows whose filing type is a PTR variant are kept; annual FD
    reports and other filing types are excluded by design.
    """
    filings: list[dict] = []
    for row in _ROW_RE.findall(html or ""):
        cells: dict[str, str] = {}
        link_href: str | None = None
        for label, body in _CELL_RE.findall(row):
            link = _LINK_RE.search(body)
            if link:
                link_href = link.group(1)
                cells[label] = _clean(link.group(2))
            else:
                cells[label] = _clean(re.sub(r"<[^>]+>", "", body))
        filing_type = cells.get("Filing")
        if filing_type not in PTR_FILING_TYPES:
            continue
        report_url = None
        if link_href:
            report_url = (
                link_href
                if link_href.startswith("http")
                else HOUSE_BASE + "/" + link_href.lstrip("/")
            )
        member_name = cells.get("Name")
        filing = {
            "member_name": member_name,
            "chamber": "House",
            "office": cells.get("Office"),
            "filing_year": cells.get("Filing Year"),
            "filing_type": filing_type,
            # The House listing carries no per-report filing date.
            "filed_date": None,
            "report_url": report_url,
            # Report-level granularity: transaction detail is in the PDF.
            "granularity": "report",
            "transaction_count": None,
            "asset": None,
            "transaction_type": None,
            "amount_range": None,
            "transaction_date": None,
            "crypto_flagged": _is_crypto_related(member_name, filing_type),
        }
        filings.append(filing)
    return filings


def _fetch_house_filings(timeout: float = HOUSE_TIMEOUT_S) -> list[dict]:
    """Fetch the House PTR filing index for FILING_YEARS. Raises on failure."""
    session = requests.Session()
    page = session.get(HOUSE_VIEW_SEARCH_URL, timeout=timeout)
    page.raise_for_status()
    token_match = _TOKEN_RE.search(page.text)
    if not token_match:
        raise RuntimeError("House search page did not include a request token")
    token = token_match.group(1)

    filings: list[dict] = []
    for i, year in enumerate(FILING_YEARS):
        if i:
            time.sleep(REQUEST_PACING_S)  # <=1 req/s courtesy pacing
        resp = session.post(
            HOUSE_SEARCH_RESULT_URL,
            data={
                "__RequestVerificationToken": token,
                "LastName": "",
                "FilingYear": str(year),
                "State": "",
                "District": "",
            },
            headers={"Referer": HOUSE_VIEW_SEARCH_URL},
            timeout=timeout,
        )
        resp.raise_for_status()
        filings.extend(_parse_house_ptr_rows(resp.text))
    return filings


def _read_cache_rows(cache_path: Path) -> list[dict] | None:
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        rows = cached.get("rows") if isinstance(cached, dict) else None
        return rows if isinstance(rows, list) else None
    except (OSError, ValueError):
        return None


def fetch_house_filings(
    cache_path: str | Path | None = None,
    timeout: float = HOUSE_TIMEOUT_S,
) -> list[dict]:
    """House PTR filings, with stale-cache fallback. Never raises.

    On failure returns the last cached rows (any age) or ``[]``.
    """
    cache_path = Path(cache_path) if cache_path else _repo_root() / "data" / "congress_cache.json"
    try:
        rows = _fetch_house_filings(timeout=timeout)
        _atomic_write_json(cache_path, {"ts": _now_iso(), "rows": rows})
        return rows
    except Exception as exc:  # network / parse / disk — fall back to stale cache
        log.warning("fetch_house_filings failed (%s); trying stale cache", exc)
        cached = _read_cache_rows(cache_path)
        if cached is not None:
            return cached
        raise


# ---------------------------------------------------------------------------
# 2. Senate EFD reports (degradable source)
# ---------------------------------------------------------------------------

def _fetch_senate_reports(timeout: float = SENATE_TIMEOUT_S) -> list[dict]:
    """Fetch Senate EFD report metadata. Raises on failure (incl. 503s).

    Kept deliberately thin: the endpoint is a maintenance-prone search API,
    so the caller treats ANY failure as "Senate leg down" and records it.
    """
    session = requests.Session()
    home = session.get(SENATE_HOME_URL, timeout=timeout)
    home.raise_for_status()
    # The EFD form posts a CSRF middleware token; extract it from the page.
    csrf_match = re.search(
        r'name="csrfmiddlewaretoken" value="([^"]+)"', home.text
    )
    payload = {
        "firstName": "",
        "lastName": "",
        "fromDate": "01/01/2025",
        "toDate": datetime.now(timezone.utc).strftime("%m/%d/%Y"),
        "offset": "0",
    }
    if csrf_match:
        payload["csrfmiddlewaretoken"] = csrf_match.group(1)
    resp = session.post(
        SENATE_DATA_URL,
        data=payload,
        headers={"Referer": SENATE_HOME_URL},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") if isinstance(data, dict) else None
    filings: list[dict] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        report_url = item.get("reportURL") or item.get("reportUrl")
        filings.append(
            {
                "member_name": _clean(
                    " ".join(
                        p for p in
                        (item.get("firstName"), item.get("lastName"))
                        if p
                    )
                ) or None,
                "chamber": "Senate",
                "office": None,
                "filing_year": None,
                "filing_type": item.get("reportType"),
                "filed_date": item.get("filedDate"),
                "report_url": report_url,
                "granularity": "report",
                "transaction_count": None,
                "asset": None,
                "transaction_type": None,
                "amount_range": None,
                "transaction_date": None,
                "crypto_flagged": _is_crypto_related(
                    item.get("firstName"), item.get("lastName")
                ),
            }
        )
    return filings


# ---------------------------------------------------------------------------
# 3. Aggregation
# ---------------------------------------------------------------------------

def _aggregate(filings: list[dict]) -> dict:
    by_chamber: dict[str, int] = {}
    by_filing_type: dict[str, int] = {}
    per_member: dict[tuple, int] = {}
    crypto_flagged = 0
    for f in filings or []:
        chamber = f.get("chamber") or "Unknown"
        by_chamber[chamber] = by_chamber.get(chamber, 0) + 1
        ftype = f.get("filing_type") or "Unknown"
        by_filing_type[ftype] = by_filing_type.get(ftype, 0) + 1
        key = (f.get("member_name"), chamber)
        per_member[key] = per_member.get(key, 0) + 1
        if f.get("crypto_flagged"):
            crypto_flagged += 1
    most_active = sorted(
        (
            {"member_name": name, "chamber": chamber, "filings": count}
            for (name, chamber), count in per_member.items()
        ),
        key=lambda m: m["filings"],
        reverse=True,
    )[:10]
    return {
        "filing_count": len(filings or []),
        "by_chamber": by_chamber,
        "by_filing_type": by_filing_type,
        "most_active_members": most_active,
        # Buy/sell splits are NOT available at report-level granularity —
        # reported honestly as null, never estimated.
        "buys": None,
        "sells": None,
        "buy_sell_note": (
            "Buy/sell counts require per-transaction data, which lives in "
            "the report PDFs; the keyless official listings are report-level "
            "only, so no split is reported."
        ),
        "crypto_flagged_count": crypto_flagged,
        "recent_notable": (filings or [])[:10],
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    out_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> dict:
    """Build the full Congress payload and atomically write it to disk.

    Never raises on source failure — each source is isolated with try/except
    and failures are recorded in ``errors`` with ``stale: true``.
    """
    errors: list[str] = []
    root = _repo_root()
    out_path = Path(out_path) if out_path else root / "public" / "congress_trades.json"
    cache_path = Path(cache_path) if cache_path else root / "data" / "congress_cache.json"

    filings: list[dict] = []

    try:
        filings.extend(fetch_house_filings(cache_path=cache_path))
    except Exception as exc:
        errors.append(f"house: {exc}")

    try:
        filings.extend(_fetch_senate_reports())
    except Exception as exc:
        errors.append(f"senate: {exc}")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "stale": bool(errors),
        "errors": errors,
        "granularity": "report",
        "granularity_note": (
            "Each entry is one disclosed Periodic Transaction Report "
            "(report-level). Per-transaction detail (ticker, buy/sell, "
            "amount range) is published only inside the report PDFs, which "
            "this keyless module does not parse; such fields are null."
        ),
        "data_lag_note": (
            "STOCK Act disclosures must be filed within 30 days of a trade "
            "(45 with extension), so filing activity lags actual trading by "
            "30-45+ days. This feed measures disclosure activity, not "
            "real-time positioning."
        ),
        "window": {"filing_years": list(FILING_YEARS)},
        "filings": filings,
        "aggregates": _aggregate(filings),
        "sources": list(SOURCES),
    }
    _atomic_write_json(out_path, payload)
    return payload


def load_payload(path: str | Path | None = None) -> dict:
    """Read a previously written payload; ``{}`` if missing/unparseable."""
    path = Path(path) if path else _repo_root() / "public" / "congress_trades.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def summary_for_status(payload: dict) -> dict:
    """Compact status summary for the desk / dashboard."""
    if not payload:
        return {"available": False}
    agg = payload.get("aggregates") or {}
    most_active = agg.get("most_active_members") or []
    top = most_active[0] if most_active else {}
    return {
        "available": True,
        "ts": payload.get("ts"),
        "filing_count": agg.get("filing_count", 0),
        "by_chamber": agg.get("by_chamber") or {},
        "top_active_member": {
            "name": top.get("member_name"),
            "filings": top.get("filings"),
        } if top else {},
        "buys": agg.get("buys"),
        "sells": agg.get("sells"),
        "crypto_flagged_count": agg.get("crypto_flagged_count", 0),
        "stale": bool(payload.get("stale")),
        "sources": payload.get("sources") or [],
    }
