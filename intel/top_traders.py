"""Top Traders Tracker — intelligence-only snapshot of where the money moves.

Keyless sources (verified live 2026-09-19):
  1. Hyperliquid leaderboard (stats-data.hyperliquid.xyz) — top perp traders
     by windowed PnL; per-trader positioning via api.hyperliquid.xyz/info.
  2. mempool.space — large on-chain BTC transfers ("whale alerts").
  3. SEC EDGAR 13F-HR filings — top institutional holdings (values in the
     filing are in THOUSANDS of USD and are converted to USD here).

Design notes:
  * Every HTTP call carries an explicit timeout; stdlib + ``requests`` only.
  * No secrets, no API keys anywhere. The SEC requires a descriptive
    User-Agent header — it is a static string, not a credential.
  * No invented data: fields the source does not provide are ``None``.
  * ``refresh()`` never raises on source failure — failures are recorded in
    ``errors`` and the payload is marked ``stale``.
  * Signals are INTELLIGENCE ONLY. This module never auto-copies anyone and
    never promises profit.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Source endpoints / constants
# ---------------------------------------------------------------------------

LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
MEMPOOL_RECENT_URL = "https://mempool.space/api/mempool/recent"
COINGECKO_BTC_URL = (
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
)
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"

# SEC blocks default user agents; this static descriptive string is required
# and is NOT a credential of any kind.
SEC_USER_AGENT = "SAHJONY-Capital/1.0 (research; contact@sahjony.com)"

# Funds tracked via 13F-HR (name, 10-digit CIK).
TRACKED_FUNDS = [
    ("Berkshire Hathaway", "0001067983"),
    ("Renaissance Technologies", "0001037389"),
    ("Citadel Advisors", "0001423053"),
    ("Bridgewater Associates", "0001350694"),
    ("Soros Fund Management", "0001029160"),
]

WHALE_THRESHOLD_USD = 1_000_000.0
LEADERBOARD_TTL_S = 21_600  # 6h — the leaderboard payload is ~38MB, cache hard
MAX_POSITION_ADDRESSES = 20  # bounds aggregate_positioning wall-clock time
WHALE_ALERT_CAP = 20
FUND_TOP_POSITIONS = 10

SOURCES = [
    "Hyperliquid stats-data (keyless)",
    "mempool.space (keyless)",
    "SEC EDGAR (keyless)",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value, default: float = 0.0) -> float:
    """Best-effort float conversion; never raises."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _shorten_address(address: str | None) -> str:
    if not address:
        return "—"
    if len(address) <= 12:
        return address
    return f"{address[:6]}…{address[-4:]}"


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


def _http_get_json(url: str, timeout: float, headers: dict | None = None) -> object:
    resp = requests.get(url, timeout=timeout, headers=headers or {})
    resp.raise_for_status()
    return resp.json()


def _http_post_json(url: str, payload: dict, timeout: float) -> object:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Hyperliquid leaderboard
# ---------------------------------------------------------------------------

def _parse_leaderboard_row(raw: dict) -> dict:
    windows: dict[str, dict] = {}
    for entry in raw.get("windowPerformances") or []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            windows[str(entry[0])] = entry[1] or {}
    day = windows.get("day", {})
    week = windows.get("week", {})
    month = windows.get("month", {})
    alltime = windows.get("allTime", {})
    return {
        "eth_address": raw.get("ethAddress"),
        "display_name": raw.get("displayName"),
        "account_value": _f(raw.get("accountValue")),
        "pnl_day": _f(day.get("pnl")),
        "pnl_week": _f(week.get("pnl")),
        "pnl_month": _f(month.get("pnl")),
        "pnl_alltime": _f(alltime.get("pnl")),
        "roi_month": _f(month.get("roi")),
    }


def _read_cache_rows(cache_path: Path) -> list[dict] | None:
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        rows = cached.get("rows") if isinstance(cached, dict) else None
        return rows if isinstance(rows, list) else None
    except (OSError, ValueError):
        return None


def fetch_leaderboard(
    cache_path: str | Path | None = None,
    ttl_s: int = LEADERBOARD_TTL_S,
    timeout: float = 30,
) -> list[dict]:
    """Fetch + parse the Hyperliquid leaderboard.

    The raw payload is ~38MB, so it is cached to ``cache_path`` for ``ttl_s``.
    On failure returns the last cached rows (any age) or ``[]``; never raises.
    """
    cache_path = Path(cache_path) if cache_path else _repo_root() / "data" / "top_traders_cache.json"

    if ttl_s > 0 and cache_path.exists():
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < ttl_s:
                rows = _read_cache_rows(cache_path)
                if rows is not None:
                    return rows
        except OSError:
            pass

    try:
        data = _http_get_json(LEADERBOARD_URL, timeout=timeout)
        raw_rows = data.get("leaderboardRows") if isinstance(data, dict) else None
        rows = [_parse_leaderboard_row(r) for r in (raw_rows or []) if isinstance(r, dict)]
        _atomic_write_json(cache_path, {"ts": _now_iso(), "rows": rows})
        return rows
    except Exception as exc:  # network / parse / disk — fall back to stale cache
        log.warning("fetch_leaderboard failed (%s); trying stale cache", exc)
        return _read_cache_rows(cache_path) or []


def _rank_traders(rows: list[dict], n: int = 20) -> list[dict]:
    ordered = sorted(rows, key=lambda r: r.get("pnl_month", 0.0), reverse=True)[: max(n, 0)]
    ts = _now_iso()
    ranked = []
    for i, r in enumerate(ordered, start=1):
        ranked.append(
            {
                "rank": i,
                "alias_or_wallet": r.get("display_name") or _shorten_address(r.get("eth_address")),
                "venue": "Hyperliquid",
                "pnl": r.get("pnl_month", 0.0),
                "roi_month": r.get("roi_month", 0.0),
                "account_value": r.get("account_value", 0.0),
                # The leaderboard feed does not publish win rate — reported
                # honestly as null rather than estimated.
                "win_rate": None,
                "period": "30d",
                "last_updated": ts,
            }
        )
    return ranked


def top_traders(n: int = 20, cache_path: str | Path | None = None) -> list[dict]:
    """Top ``n`` Hyperliquid traders ranked by 30-day PnL (descending)."""
    return _rank_traders(fetch_leaderboard(cache_path=cache_path), n)


# ---------------------------------------------------------------------------
# 2. Aggregate positioning (per-trader clearinghouse state)
# ---------------------------------------------------------------------------

def aggregate_positioning(addresses: list[str], timeout: float = 10) -> dict:
    """Aggregate long/short positioning for BTC and ETH across addresses.

    For each address the Hyperliquid ``clearinghouseState`` is read and the
    sign of ``szi`` for BTC/ETH is tallied. Addresses that fail are counted
    in ``errors``; never raises.
    """
    stats = {coin: {"long": 0, "short": 0, "flat": 0} for coin in ("BTC", "ETH")}
    sampled = 0
    errors = 0

    for address in list(addresses or [])[:MAX_POSITION_ADDRESSES]:
        try:
            data = _http_post_json(
                HYPERLIQUID_INFO_URL,
                {"type": "clearinghouseState", "user": address},
                timeout=timeout,
            )
            positions: dict[str, float | None] = {}
            asset_positions = data.get("assetPositions") if isinstance(data, dict) else None
            for ap in asset_positions or []:
                pos = (ap or {}).get("position") or {}
                coin = pos.get("coin")
                if coin in stats:
                    positions[coin] = _f(pos.get("szi"), default=None) if pos.get("szi") is not None else None
            for coin, tally in stats.items():
                szi = positions.get(coin)
                if szi is None:
                    tally["flat"] += 1
                elif szi > 0:
                    tally["long"] += 1
                elif szi < 0:
                    tally["short"] += 1
                else:
                    tally["flat"] += 1
            sampled += 1
        except Exception as exc:
            errors += 1
            log.warning("aggregate_positioning failed for %s: %s", _shorten_address(address), exc)

    out: dict = {}
    for coin, tally in stats.items():
        directional = tally["long"] + tally["short"]
        pct_long = (100.0 * tally["long"] / directional) if directional else 0.0
        out[coin] = {
            "pct_long": round(pct_long, 1),
            "long": tally["long"],
            "short": tally["short"],
            "flat": tally["flat"],
        }
    out.update({"sampled": sampled, "errors": errors, "ts": _now_iso()})
    return out


def copy_signal(agg: dict) -> dict:
    """Derive a directional read from aggregate positioning.

    A 0% long reading with zero directional positions is *no signal*, not a
    bearish one — so when neither asset has any long or short to count, the
    bias is "mixed" (neutral), never "short".
    """
    btc_d = (agg or {}).get("BTC", {}) or {}
    eth_d = (agg or {}).get("ETH", {}) or {}
    btc = btc_d.get("pct_long", 50.0)
    eth = eth_d.get("pct_long", 50.0)
    try:
        btc, eth = float(btc), float(eth)
    except (TypeError, ValueError):
        btc, eth = 50.0, 50.0

    def _directional(d: dict):
        """Total long+short count, or None when the payload carries no counts."""
        l, s = d.get("long"), d.get("short")
        if l is None and s is None:
            return None
        try:
            return int(l or 0) + int(s or 0)
        except (TypeError, ValueError):
            return None

    dir_btc, dir_eth = _directional(btc_d), _directional(eth_d)
    if (dir_btc is not None and dir_eth is not None
            and dir_btc == 0 and dir_eth == 0):
        # A 0% long reading with zero directional positions sampled is *no
        # signal*, not a bearish one — report neutral, never "short".
        net_bias = "mixed"
    elif btc > 55 and eth > 55:
        net_bias = "long"
    elif btc < 45 and eth < 45:
        net_bias = "short"
    else:
        net_bias = "mixed"
    return {
        "label": "INTELLIGENCE ONLY — not auto-copying",
        "assets": {"BTC": btc, "ETH": eth},
        "net_bias": net_bias,
        "ts": _now_iso(),
    }


# ---------------------------------------------------------------------------
# 3. Whale feed (mempool.space)
# ---------------------------------------------------------------------------

def fetch_whale_alerts(
    btc_price_usd: float | None = None,
    threshold_usd: float = WHALE_THRESHOLD_USD,
    timeout: float = 10,
) -> list[dict]:
    """Large BTC transfers from mempool.space, newest first, capped at 20.

    ``from``/``to`` are not provided by the endpoint and are reported as
    ``None`` — never invented.
    """
    if btc_price_usd is None:
        price_data = _http_get_json(COINGECKO_BTC_URL, timeout=timeout)
        btc_price_usd = float(price_data["bitcoin"]["usd"])
    price = float(btc_price_usd)

    txs = _http_get_json(MEMPOOL_RECENT_URL, timeout=timeout)
    alerts = []
    for tx in txs or []:
        if not isinstance(tx, dict):
            continue
        sats = _f(tx.get("value"))
        amount_btc = sats / 100_000_000
        amount_usd = amount_btc * price
        if amount_usd >= threshold_usd:
            alerts.append(
                {
                    "asset": "BTC",
                    "amount_usd": round(amount_usd, 2),
                    "amount_btc": round(amount_btc, 8),
                    "txid": tx.get("txid"),
                    "from": None,
                    "to": None,
                    "ts": _now_iso(),
                    "source": "mempool.space",
                }
            )
    return alerts[:WHALE_ALERT_CAP]


# ---------------------------------------------------------------------------
# 4. SEC EDGAR 13F holdings
# ---------------------------------------------------------------------------

def _pick_infotable(items: list[dict]) -> dict | None:
    xmls = [it for it in items if str(it.get("name", "")).lower().endswith(".xml")]
    if not xmls:
        return None
    for it in xmls:
        if "infotable" in str(it.get("name", "")).lower():
            return it
    # The information table is the holdings data — always the large XML. Cover
    # pages (primary_doc.xml) are a few KB; never pick those by accident.
    def _size(it: dict) -> int:
        try:
            return int(str(it.get("size") or 0))
        except (TypeError, ValueError):
            return 0
    candidates = [it for it in xmls
                  if "cover" not in str(it.get("name", "")).lower()
                  and "primary" not in str(it.get("name", "")).lower()]
    pool = candidates or xmls
    return max(pool, key=_size)


def _resolve_13f_unit(raw_positions: list[tuple]) -> float:
    """Return the USD multiplier for a filing's <value> numbers.

    The 13F-HR spec says <value> is in $000s, but several large filers report
    plain dollars. A filer uses one unit consistently, so we take a majority
    vote across entries: the implied per-share price is only sane under the
    filer's true unit. Ties / no-share entries fall back to the spec ($000s).
    """
    votes_dollars = votes_thousands = 0
    for value_raw, shares in raw_positions:
        if value_raw <= 0 or shares <= 0:
            continue
        px_thousands = value_raw * 1000.0 / shares
        px_dollars = value_raw / shares
        t_ok = 0.05 <= px_thousands <= 200_000.0
        d_ok = 0.05 <= px_dollars <= 200_000.0
        if d_ok and not t_ok:
            votes_dollars += 1
        elif t_ok and not d_ok:
            votes_thousands += 1
    if votes_dollars > votes_thousands:
        return 1.0
    return 1000.0


def _parse_infotable_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    raw: list[tuple] = []
    for table in root.findall(".//{*}infoTable"):
        def _text(tag: str) -> str:
            el = table.find(f".//{{*}}{tag}")
            return (el.text or "").strip() if el is not None and el.text else ""

        issuer = _text("nameOfIssuer")
        if not issuer:
            continue
        raw.append((issuer, _f(_text("value")), _f(_text("sshPrnamt"))))
    unit = _resolve_13f_unit([(v, s) for _, v, s in raw])
    # Aggregate by issuer: one filer often splits a holding across managers.
    by_issuer: dict[str, dict] = {}
    for issuer, value_raw, shares in raw:
        slot = by_issuer.setdefault(issuer, {"issuer": issuer, "value_usd": 0.0, "shares": 0})
        slot["value_usd"] += round(value_raw * unit, 2)
        try:
            slot["shares"] += int(shares)
        except (TypeError, ValueError):
            pass
    positions = sorted(by_issuer.values(), key=lambda p: p["value_usd"], reverse=True)
    return positions[:FUND_TOP_POSITIONS]


def _fetch_fund_13f(name: str, cik: str, timeout: float) -> dict:
    """Fetch one fund's latest 13F-HR top holdings. Raises on failure."""
    subs = _http_get_json(
        SEC_SUBMISSIONS_URL.format(cik=cik), timeout=timeout, headers={"User-Agent": SEC_USER_AGENT}
    )
    recent = (subs or {}).get("filings", {}).get("recent", {})
    forms = recent.get("form", []) or []
    idx = next((i for i, f in enumerate(forms) if f == "13F-HR"), None)
    if idx is None:
        raise ValueError("no 13F-HR filing in recent submissions")

    accessions = recent.get("accessionNumber", []) or []
    filing_dates = recent.get("filingDate", []) or []
    report_dates = recent.get("reportDate", []) or []
    acc_nodash = str(accessions[idx]).replace("-", "")
    cik_nz = str(int(cik))  # archives path uses the CIK without leading zeros

    index = _http_get_json(
        SEC_ARCHIVES_URL.format(cik=cik_nz, acc=acc_nodash, name="index.json"),
        timeout=timeout,
        headers={"User-Agent": SEC_USER_AGENT},
    )
    items = ((index or {}).get("directory", {}) or {}).get("item", []) or []
    doc = _pick_infotable(items)
    if doc is None:
        raise ValueError("no information-table XML found in filing index")

    resp = requests.get(
        SEC_ARCHIVES_URL.format(cik=cik_nz, acc=acc_nodash, name=doc["name"]),
        timeout=timeout,
        headers={"User-Agent": SEC_USER_AGENT},
    )
    resp.raise_for_status()

    return {
        "fund": name,
        "cik": cik,
        "top_positions": _parse_infotable_xml(resp.text),
        "filing_date": filing_dates[idx] if idx < len(filing_dates) else None,
        "period_end": report_dates[idx] if idx < len(report_dates) else None,
        "source": "SEC EDGAR 13F-HR",
    }


def fetch_13f_holdings(timeout: float = 10, errors: list | None = None) -> list[dict]:
    """Top holdings for each tracked fund. A fund that fails is skipped and
    recorded in ``errors`` — never invented."""
    if errors is None:
        errors = []
    holdings = []
    for i, (name, cik) in enumerate(TRACKED_FUNDS):
        if i:
            time.sleep(1.0)  # ≤1 req/s courtesy pacing for SEC EDGAR
        try:
            holdings.append(_fetch_fund_13f(name, cik, timeout))
        except Exception as exc:
            msg = f"13F {name} ({cik}): {exc}"
            log.warning(msg)
            errors.append(msg)
    return holdings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    out_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> dict:
    """Build the full Top Traders payload and atomically write it to disk.

    Never raises on source failure — each source is isolated with try/except
    and failures are recorded in ``errors`` with ``stale: true``.
    """
    errors: list[str] = []
    root = _repo_root()
    out_path = Path(out_path) if out_path else root / "public" / "top_traders.json"
    cache_path = Path(cache_path) if cache_path else root / "data" / "top_traders_cache.json"

    traders: list[dict] = []
    agg: dict = {}
    signal: dict = {}
    whales: list[dict] = []
    funds: list[dict] = []

    try:
        rows = fetch_leaderboard(cache_path=cache_path)
        if not rows:
            raise RuntimeError("leaderboard returned no rows (network + cache empty)")
        ranked_rows = sorted(rows, key=lambda r: r.get("pnl_month", 0.0) or 0.0,
                             reverse=True)
        traders = _rank_traders(ranked_rows)
        # Position sample = the top-ranked traders by 30d PnL, not the raw
        # leaderboard order (which is account-value sorted).
        addresses = [r.get("eth_address") for r in ranked_rows[:MAX_POSITION_ADDRESSES]
                     if r.get("eth_address")]
        try:
            agg = aggregate_positioning(addresses)
        except Exception as exc:  # defensive — aggregate_positioning already guards per-address
            errors.append(f"aggregate_positioning: {exc}")
            agg = {"BTC": {}, "ETH": {}, "sampled": 0, "errors": 0, "ts": _now_iso()}
        signal = copy_signal(agg)
    except Exception as exc:
        errors.append(f"leaderboard: {exc}")
        signal = copy_signal({})

    try:
        whales = fetch_whale_alerts()
    except Exception as exc:
        errors.append(f"whale_alerts: {exc}")

    try:
        funds = fetch_13f_holdings(errors=errors)
    except Exception as exc:  # defensive — fetch_13f_holdings already guards per-fund
        errors.append(f"13f: {exc}")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "stale": bool(errors),
        "errors": errors,
        "traders": traders,
        "aggregate_positioning": agg,
        "copy_signal": signal,
        "whale_alerts": whales,
        "fund_holdings": funds,
        "sources": list(SOURCES),
    }
    _atomic_write_json(out_path, payload)
    return payload


def load_payload(path: str | Path | None = None) -> dict:
    """Read a previously written payload; ``{}`` if missing/unparseable."""
    path = Path(path) if path else _repo_root() / "public" / "top_traders.json"
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
    traders = payload.get("traders") or []
    top = traders[0] if traders else {}
    return {
        "available": True,
        "ts": payload.get("ts"),
        "trader_count": len(traders),
        "top_trader": {"alias": top.get("alias_or_wallet"), "pnl": top.get("pnl")},
        "copy_signal": payload.get("copy_signal") or {},
        "whale_alert_count": len(payload.get("whale_alerts") or []),
        "funds_tracked": len(payload.get("fund_holdings") or []),
        "stale": bool(payload.get("stale")),
        "sources": payload.get("sources") or [],
    }
