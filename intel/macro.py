"""MACRO PULSE — keyless macro backdrop snapshot for the council.

Crypto trades heavily off the macro backdrop: a strong dollar and rising
real yields are classic risk-off headwinds; a soft dollar and falling
yields are risk-on tailwinds. This engine supplies that backdrop as
INTELLIGENCE ONLY — it never emits orders, never touches credentials,
and never promises profit.

Keyless sources (verified live 2026-09-19):
  1. Yahoo Finance v8 chart API (query1.finance.yahoo.com; query2 as
     fallback host) — daily bars, keyless. A static descriptive User-Agent
     is sent on every request (it is NOT a credential; Yahoo rejects
     empty-U_A requests with 401).
       DX-Y.NYB — US Dollar Index spot              (last 100.215)
       ^TNX     — Cboe 10-Year Treasury Note Yield  (last 4.998%)
       GC=F     — Gold front-month futures          (last $4,424.90/oz)
       CL=F     — WTI crude front-month futures     (last $96.08/bbl)
  2. Stooq free CSV (https://stooq.com/q/l/?s=...&f=sd2t2ohlcv&h&e=csv)
     was the first candidate. ATTEMPTED 2026-09-19 and REJECTED: the
     endpoint returns Stooq's "page you requested does not exist" HTML
     for EVERY symbol (including aapl.us), and the quote pages sit
     behind a proof-of-work JavaScript challenge — not keyless-scriptable
     without solving their anti-bot check. Stooq is NOT used.

Design notes:
  * Every HTTP call carries an explicit timeout; stdlib + ``requests`` only.
  * No secrets, no API keys anywhere.
  * One request per symbol per refresh (4 requests), daily bars over a
    ~3-month range — changes and trends are computed from the returned
    bars themselves (no separate history cache needed).
  * The payload is cache-first: when the cache file is younger than
    CACHE_TTL_S, ``refresh()`` serves the last-good payload without any
    network call. On network failure it serves the stale cache (flagged)
    or a payload with ``stale: true`` and the failure in ``errors``.
  * No invented data: fields the source does not provide are ``None``.
  * ``refresh()`` never raises on source failure — failures are recorded
    in ``errors`` and the payload is marked ``stale``.

Backdrop derivation (documented heuristic, bounded and honest):
  * Inputs: the 5-trading-day percent changes of DX-Y.NYB (dollar) and
    ^TNX (10y yield); falls back to 1-day changes when a 5-day window is
    unavailable.
  * "risk-off headwind" (bias "defensive"): DXY 5d >= +0.75% AND 10y 5d
    >= +2.0%  — a rising dollar with rising yields is the classic
    crypto risk-off backdrop.
  * "risk-on tailwind" (bias "supportive"): DXY 5d <= -0.75% AND 10y 5d
    <= -2.0% — a soft dollar with falling yields is the classic
    risk-on backdrop.
  * Anything else (mixed signals): "mixed / neutral", bias "neutral".
  * Missing either input: "unknown — insufficient data", bias "neutral".
  Thresholds are arbitrary judgment calls, documented here so the council
  can weigh them; the backdrop always ships with the raw metrics.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Source endpoints / constants
# ---------------------------------------------------------------------------

YAHOO_CHART_URL = "https://{host}/v8/finance/chart/{symbol}?interval=1d&range=3mo"
YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")

# Static descriptive User-Agent (NOT a credential — Yahoo 401s on empty UA).
YAHOO_USER_AGENT = "SAHJONY-Capital/1.0 (macro research; contact@sahjony.com)"

REQUEST_TIMEOUT_S = 20
CACHE_TTL_S = 21_600  # 6h — macro moves on a daily cadence; dashboard reads the file

# Backdrop thresholds (5-trading-day percent changes; documented heuristic).
DXY_HEADWIND_PCT = 0.75    # DXY +0.75% over 5d
TNX_HEADWIND_PCT = 2.0     # 10y yield +2.0% over 5d
TREND_DEADBAND = 0.001     # last within ±0.1% of 20d SMA counts as "flat"

INSTRUMENTS = [
    {
        "symbol": "DX-Y.NYB",
        "name": "US Dollar Index",
        "unit": "points",
        "why": "Dollar strength is the primary crypto risk-off headwind.",
    },
    {
        "symbol": "^TNX",
        "name": "10-Year Treasury Yield",
        "unit": "percent",
        "why": "Rising yields tighten financial conditions; crypto is duration-sensitive.",
    },
    {
        "symbol": "GC=F",
        "name": "Gold Futures",
        "unit": "USD/oz",
        "why": "Competing hard-asset bid; gold strength confirms risk-off flows.",
    },
    {
        "symbol": "CL=F",
        "name": "WTI Crude Futures",
        "unit": "USD/bbl",
        "why": "Energy inflation pressure feeds the rates backdrop.",
    },
]

SOURCES = [
    "Yahoo Finance v8 chart API (keyless)",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value, default: float | None = None) -> float | None:
    """Best-effort float conversion; never raises. None stays None unless
    a default is given."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _bar_date(ts: float, tz_name: str | None) -> str | None:
    """Exchange-timezone calendar date of a bar timestamp, UTC fallback."""
    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        tz = timezone.utc
    try:
        return datetime.fromtimestamp(ts, tz).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Fetch + parse one instrument
# ---------------------------------------------------------------------------

def _fetch_bars(symbol: str, timeout: float = REQUEST_TIMEOUT_S) -> tuple[list[tuple[float, float]], str | None]:
    """Fetch daily (timestamp, close) bars for a symbol from Yahoo chart API.

    Tries the configured hosts in order. Returns ``(bars, tz_name)``.
    Raises on failure (callers isolate per-instrument).
    """
    headers = {"User-Agent": YAHOO_USER_AGENT}
    last_exc: Exception | None = None
    for host in YAHOO_HOSTS:
        url = YAHOO_CHART_URL.format(host=host, symbol=symbol)
        try:
            data = _http_get_json(url, timeout=timeout, headers=headers)
            result = (data or {}).get("chart", {}).get("result") or []
            if not result:
                raise ValueError("no chart result")
            row = result[0]
            meta = row.get("meta") or {}
            stamps = row.get("timestamp") or []
            closes = ((row.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            bars = [
                (float(ts), float(c))
                for ts, c in zip(stamps, closes)
                if ts is not None and c is not None
            ]
            if not bars:
                raise ValueError("no usable close bars")
            return bars, meta.get("exchangeTimezoneName")
        except Exception as exc:
            last_exc = exc
            log.warning("macro fetch %s via %s failed: %s", symbol, host, exc)
    raise RuntimeError(f"all Yahoo hosts failed for {symbol}: {last_exc}")


def _parse_instrument(spec: dict, bars: list[tuple[float, float]], tz_name: str | None) -> dict:
    """Compute last / 1d / 5d changes / 20d trend from daily bars."""
    closes = [c for _, c in bars]
    last = closes[-1]
    chg_1d = (last / closes[-2] - 1.0) * 100.0 if len(closes) >= 2 else None
    chg_5d = (last / closes[-6] - 1.0) * 100.0 if len(closes) >= 6 else None
    trend_20d: str | None = None
    if len(closes) >= 20:
        sma20 = sum(closes[-20:]) / 20.0
        if sma20 > 0:
            ratio = last / sma20
            if ratio > 1.0 + TREND_DEADBAND:
                trend_20d = "up"
            elif ratio < 1.0 - TREND_DEADBAND:
                trend_20d = "down"
            else:
                trend_20d = "flat"
    return {
        "symbol": spec["symbol"],
        "name": spec["name"],
        "unit": spec["unit"],
        "last": round(last, 4),
        "as_of": _bar_date(bars[-1][0], tz_name),
        "chg_1d_pct": round(chg_1d, 3) if chg_1d is not None else None,
        "chg_5d_pct": round(chg_5d, 3) if chg_5d is not None else None,
        "trend_20d": trend_20d,
        "bars": len(closes),
    }


def fetch_instrument(spec: dict, timeout: float = REQUEST_TIMEOUT_S) -> dict:
    """Fetch + parse one instrument. Raises on failure."""
    bars, tz_name = _fetch_bars(spec["symbol"], timeout=timeout)
    return _parse_instrument(spec, bars, tz_name)


# ---------------------------------------------------------------------------
# Backdrop derivation
# ---------------------------------------------------------------------------

def _by_symbol(instruments: list[dict], symbol: str) -> dict:
    return next((i for i in instruments if i.get("symbol") == symbol), {})


def derive_backdrop(instruments: list[dict]) -> dict:
    """Bounded macro read from DXY + 10y yield momentum.

    Labels are ALWAYS prefixed "INTELLIGENCE ONLY" — the council weighs the
    raw metrics, never this label alone.
    """
    dxy = _by_symbol(instruments, "DX-Y.NYB")
    tnx = _by_symbol(instruments, "^TNX")
    # Prefer 5-day momentum; fall back to 1-day when a 5d window is missing.
    dxy_m = dxy.get("chg_5d_pct") if dxy.get("chg_5d_pct") is not None else dxy.get("chg_1d_pct")
    tnx_m = tnx.get("chg_5d_pct") if tnx.get("chg_5d_pct") is not None else tnx.get("chg_1d_pct")
    window = "5d" if dxy.get("chg_5d_pct") is not None and tnx.get("chg_5d_pct") is not None else "1d"

    base = {"window": window, "dxy_chg_pct": dxy_m, "tnx_chg_pct": tnx_m}

    if dxy_m is None or tnx_m is None:
        return {
            **base,
            "label": "INTELLIGENCE ONLY — unknown — insufficient data",
            "bias": "neutral",
            "rationale": (
                "DXY or 10y-yield momentum is unavailable, so no directional "
                "macro read is derived. The council should use the raw "
                "instrument metrics only."
            ),
        }

    rationale = (
        f"DXY {dxy_m:+.2f}% and 10y yield {tnx_m:+.2f}% over the last {window}."
    )
    if dxy_m >= DXY_HEADWIND_PCT and tnx_m >= TNX_HEADWIND_PCT:
        return {
            **base,
            "label": "INTELLIGENCE ONLY — risk-off headwind for crypto",
            "bias": "defensive",
            "rationale": (
                rationale + " A rising dollar with rising yields is the classic "
                "crypto risk-off backdrop: tighter financial conditions, "
                "stronger USD bid against BTC."
            ),
        }
    if dxy_m <= -DXY_HEADWIND_PCT and tnx_m <= -TNX_HEADWIND_PCT:
        return {
            **base,
            "label": "INTELLIGENCE ONLY — risk-on tailwind for crypto",
            "bias": "supportive",
            "rationale": (
                rationale + " A soft dollar with falling yields is the classic "
                "crypto risk-on backdrop: looser financial conditions, "
                "harder for the dollar to crowd out BTC."
            ),
        }
    return {
        **base,
        "label": "INTELLIGENCE ONLY — mixed / neutral",
        "bias": "neutral",
        "rationale": (
            rationale + " Dollar and yields are not moving together — no clear "
            "directional macro read for crypto."
        ),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    out_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> dict:
    """Build the MACRO PULSE payload and atomically write it to disk.

    Cache-first: when the cache file is younger than ``CACHE_TTL_S`` the
    last-good payload is served without any network call. Every source is
    isolated with try/except — failures land in ``errors`` with
    ``stale: true``; ``refresh()`` never raises.
    """
    errors: list[str] = []
    root = _repo_root()
    out_path = Path(out_path) if out_path else root / "public" / "macro_pulse.json"
    cache_path = Path(cache_path) if cache_path else root / "data" / "macro_pulse_cache.json"

    def _serve_cache(reason: str) -> dict | None:
        try:
            with open(cache_path, encoding="utf-8") as fh:
                cached = json.load(fh)
            if isinstance(cached, dict) and cached.get("instruments"):
                payload = dict(cached)
                payload["stale"] = True
                payload["errors"] = [*payload.get("errors", []), reason]
                _atomic_write_json(out_path, payload)
                log.info("macro_pulse serving stale cache (%s)", reason)
                return payload
        except (OSError, ValueError) as exc:
            log.warning("macro_pulse cache unreadable: %s", exc)
        return None

    # Cache-first: skip the network entirely when the last-good payload is fresh.
    try:
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_TTL_S:
            cached = _serve_cache(f"cache fresh ({age:.0f}s old) — no network refresh")
            if cached:
                cached["stale"] = False
                cached["errors"] = []
                _atomic_write_json(out_path, cached)
                return cached
    except OSError:
        pass

    instruments: list[dict] = []
    for spec in INSTRUMENTS:
        try:
            instruments.append(fetch_instrument(spec))
        except Exception as exc:
            msg = f"{spec['symbol']}: {exc}"
            log.warning("macro_pulse instrument failed: %s", msg)
            errors.append(msg)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "stale": bool(errors) or not instruments,
        "errors": errors,
        "instruments": instruments,
        "backdrop": derive_backdrop(instruments),
        "sources": list(SOURCES),
    }

    if instruments:
        # Persist the last-good payload (served stale on the next failure).
        try:
            _atomic_write_json(cache_path, payload)
        except Exception as exc:
            log.warning("macro_pulse cache write failed: %s", exc)
    else:
        # Total failure: serve any stale cache rather than an empty payload.
        stale = _serve_cache("all instruments failed — serving stale cache")
        if stale:
            return stale

    _atomic_write_json(out_path, payload)
    return payload


def load_payload(path: str | Path | None = None) -> dict:
    """Read a previously written payload; ``{}`` if missing/unparseable."""
    path = Path(path) if path else _repo_root() / "public" / "macro_pulse.json"
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
    instruments = payload.get("instruments") or []
    return {
        "available": True,
        "ts": payload.get("ts"),
        "instrument_count": len(instruments),
        "backdrop": payload.get("backdrop") or {},
        "instruments": [
            {
                "symbol": i.get("symbol"),
                "last": i.get("last"),
                "chg_5d_pct": i.get("chg_5d_pct"),
                "trend_20d": i.get("trend_20d"),
            }
            for i in instruments
        ],
        "stale": bool(payload.get("stale")),
        "sources": payload.get("sources") or [],
    }
