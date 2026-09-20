"""News / Sentiment Intelligence — keyless market-mood snapshot.

Keyless sources (verified live 2026-09-19):
  1. Fear & Greed Index (api.alternative.me/fng, keyless) — VERIFIED LIVE
     2026-09-19 (HTTP 200; 7 data points: value 71 "Greed", 7d delta +14).
  2. CoinGecko trending (api.coingecko.com/api/v3/search/trending, keyless) —
     VERIFIED LIVE 2026-09-19 (HTTP 200; coins list, e.g. FIRO first).
  3. GDELT DOC 2.1 API (api.gdelt.org, keyless) — UNREACHABLE from the build
     host on 2026-09-19 (TLS completes, then "Empty reply from server"; the
     api.gdeltproject.org mirror hangs and returns HTTP 429). The query is
     wired with graceful degradation: when GDELT is unreachable the
     ``news_volume`` entries report ``None`` counts and the failure lands in
     ``errors`` — never invented numbers.

Design notes:
  * Every HTTP call carries an explicit timeout; stdlib + ``requests`` only.
  * No secrets, no API keys anywhere.
  * No invented data: fields a source does not provide are ``None``.
  * ``refresh()`` never raises on source failure — failures are recorded in
    ``errors`` and the payload is marked ``stale``.
  * Sentiment reads are INTELLIGENCE ONLY. This module never emits orders,
    never touches credentials, never promises profit, and never widens the
    risk envelope ($10/order, 12%/position, 70% deployed, 10% daily-drawdown
    halt — frozen, untouched here).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Source endpoints / constants
# ---------------------------------------------------------------------------

FNG_URL = "https://api.alternative.me/fng/?limit=7&format=json"
GDELT_DOC_URL = "https://api.gdelt.org/api/v2/doc/doc"
COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"

# GDELT DOC 2.1 timelinevol: one call per query returns a 7-day series of
# article counts. ``count_24h`` = the most recent day; ``count_7d_avg`` = the
# mean over the window; ``spike_ratio`` = count_24h / count_7d_avg.
GDELT_QUERIES = ["bitcoin", "ethereum", "cryptocurrency"]
GDELT_TIMESPAN = "7days"
GDELT_TIMEOUT = 20.0
FNG_TIMEOUT = 10.0
TRENDING_TIMEOUT = 10.0
TRENDING_COIN_CAP = 7
SPIKE_THRESHOLD = 2.0  # spike_ratio >= this flags a volume spike

SOURCES = [
    "Fear & Greed Index (alternative.me, keyless)",
    "GDELT DOC 2.1 (keyless)",
    "CoinGecko trending (keyless)",
]


# ---------------------------------------------------------------------------
# Small helpers (mirroring intel/top_traders.py)
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value, default=None):
    """Best-effort finite-float conversion; ``None``/non-numeric stay ``None``."""
    try:
        if value is None or value == "":
            return default
        f = float(value)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
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


def _http_get_json(url: str, timeout: float, headers: dict | None = None,
                   params: dict | None = None) -> object:
    resp = requests.get(url, timeout=timeout, headers=headers or {}, params=params or {})
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Fear & Greed Index
# ---------------------------------------------------------------------------

def _parse_fng(data: object) -> dict:
    """Parse the alternative.me /fng payload.

    Returns {"value", "classification", "delta_7d", "history"} — values are
    ``None`` when the source does not provide them; never invented.
    """
    rows = (data or {}).get("data") if isinstance(data, dict) else None
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not rows:
        return {"value": None, "classification": None, "delta_7d": None,
                "history": []}

    def _entry(r: dict) -> dict:
        return {
            "value": _finite(r.get("value")),
            "classification": r.get("value_classification"),
            "timestamp": r.get("timestamp"),
        }

    history = [_entry(r) for r in rows]
    first, last = history[0], history[-1]
    value, classification = first["value"], first["classification"]
    if value is not None and last["value"] is not None:
        delta_7d = round(value - last["value"], 2)
    else:
        delta_7d = None
    return {
        "value": value,
        "classification": classification,
        "delta_7d": delta_7d,
        "history": history,
    }


def fetch_fear_greed(timeout: float = FNG_TIMEOUT) -> dict:
    """Fetch the Fear & Greed Index. Raises on failure."""
    return _parse_fng(_http_get_json(FNG_URL, timeout=timeout))


# ---------------------------------------------------------------------------
# 2. GDELT article volume (timelinevol, 7d window)
# ---------------------------------------------------------------------------

def _parse_gdelt_timelinevol(data: object) -> dict:
    """Parse a GDELT timelinevol payload into 24h / 7d-average article counts.

    Counts come straight from the source's ``volume`` fields; when the
    baseline is 0 ``spike_ratio`` is ``None`` (no invented ratio).
    """
    volumes: list[float] = []
    timeline = (data or {}).get("timeline") if isinstance(data, dict) else None
    if isinstance(timeline, list):
        for block in timeline:
            if not isinstance(block, dict):
                continue
            for point in block.get("data") or []:
                if isinstance(point, dict):
                    v = _finite(point.get("volume"))
                    if v is not None:
                        volumes.append(v)
    if not volumes:
        return {"count_24h": None, "count_7d_avg": None, "spike_ratio": None,
                "days_sampled": 0}
    count_24h = volumes[-1]
    avg = sum(volumes) / len(volumes)
    spike = (count_24h / avg) if avg > 0 else None
    return {
        "count_24h": count_24h,
        "count_7d_avg": round(avg, 2),
        "spike_ratio": round(spike, 2) if spike is not None else None,
        "days_sampled": len(volumes),
    }


def fetch_news_volume(query: str, timeout: float = GDELT_TIMEOUT) -> dict:
    """Article volume for one query over the last 7 days. Raises on failure."""
    data = _http_get_json(
        GDELT_DOC_URL, timeout=timeout,
        params={"query": query, "mode": "timelinevol", "format": "json",
                "timespan": GDELT_TIMESPAN},
    )
    entry = _parse_gdelt_timelinevol(data)
    entry["query"] = query
    entry["spike"] = (entry["spike_ratio"] is not None
                      and entry["spike_ratio"] >= SPIKE_THRESHOLD)
    return entry


# ---------------------------------------------------------------------------
# 3. CoinGecko trending
# ---------------------------------------------------------------------------

def _parse_trending(data: object, cap: int = TRENDING_COIN_CAP) -> list[dict]:
    """Names/symbols only — the endpoint provides no sentiment, none invented."""
    coins = (data or {}).get("coins") if isinstance(data, dict) else None
    out = []
    for entry in (coins or [])[: max(cap, 0)]:
        item = (entry or {}).get("item") if isinstance(entry, dict) else None
        if not isinstance(item, dict):
            continue
        out.append({
            "name": item.get("name"),
            "symbol": item.get("symbol"),
            "id": item.get("id"),
            "market_cap_rank": item.get("market_cap_rank"),
        })
    return out


def fetch_trending_coins(timeout: float = TRENDING_TIMEOUT) -> list[dict]:
    """Currently trending coins (names/symbols). Raises on failure."""
    return _parse_trending(_http_get_json(COINGECKO_TRENDING_URL, timeout=timeout))


# ---------------------------------------------------------------------------
# 4. Bounded sentiment read (INTELLIGENCE ONLY)
# ---------------------------------------------------------------------------

def sentiment_read(fear_greed: dict, news_volume: list[dict]) -> dict:
    """Derive a bounded, labeled sentiment read from the raw inputs.

    Extreme fear (<=20) reads contrarian mildly-bullish; extreme greed (>=80)
    reads cautious. Everything is advisory — the raw inputs always ship
    alongside so the brain can use them directly.
    """
    value = (fear_greed or {}).get("value")
    try:
        v = float(value) if value is not None else None
    except (TypeError, ValueError):
        v = None

    if v is None:
        label, bias = "no_reading", "neutral"
    elif v <= 20:
        label, bias = "extreme_fear", "mildly_bullish_contrarian"
    elif v < 40:
        label, bias = "fear", "cautious_bullish"
    elif v <= 60:
        label, bias = "neutral", "neutral"
    elif v < 80:
        label, bias = "greed", "cautious"
    else:
        label, bias = "extreme_greed", "cautious_bearish"

    spiking = [e.get("query") for e in (news_volume or [])
               if isinstance(e, dict) and e.get("spike")]
    return {
        "label": "INTELLIGENCE ONLY — advisory, never a trade signal",
        "fear_greed_label": label,
        "bias": bias,
        "spike_queries": spiking,
        "ts": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    out_path: str | Path | None = None,
    cache_path: str | Path | None = None,  # kept for API parity with top_traders
) -> dict:
    """Build the full news/sentiment payload and atomically write it to disk.

    Never raises on source failure — each source is isolated with try/except
    and failures are recorded in ``errors`` with ``stale: true``.
    """
    errors: list[str] = []
    root = _repo_root()
    out_path = Path(out_path) if out_path else root / "public" / "news_intel.json"

    fear_greed: dict = {}
    news_volume: list[dict] = []
    trending: list[dict] = []

    try:
        fear_greed = fetch_fear_greed()
    except Exception as exc:
        errors.append(f"fear_greed: {exc}")
        fear_greed = {"value": None, "classification": None, "delta_7d": None,
                      "history": []}

    for i, query in enumerate(GDELT_QUERIES):
        if i:
            time.sleep(2.0)  # courtesy pacing for the keyless GDELT endpoint
        try:
            news_volume.append(fetch_news_volume(query))
        except Exception as exc:
            log.warning("news_volume %r failed: %s", query, exc)
            errors.append(f"news_volume[{query}]: {exc}")
            news_volume.append({"query": query, "count_24h": None,
                                "count_7d_avg": None, "spike_ratio": None,
                                "days_sampled": 0, "spike": False})

    try:
        trending = fetch_trending_coins()
    except Exception as exc:
        errors.append(f"trending: {exc}")
        trending = []

    read = sentiment_read(fear_greed, news_volume)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "stale": bool(errors),
        "errors": errors,
        "fear_greed": fear_greed,
        "news_volume": news_volume,
        "trending_coins": trending,
        "sentiment_read": read,
        "sources": list(SOURCES),
    }
    _atomic_write_json(out_path, payload)
    return payload


def load_payload(path: str | Path | None = None) -> dict:
    """Read a previously written payload; ``{}`` if missing/unparseable."""
    path = Path(path) if path else _repo_root() / "public" / "news_intel.json"
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
    fg = payload.get("fear_greed") or {}
    read = payload.get("sentiment_read") or {}
    trending = payload.get("trending_coins") or []
    volume = payload.get("news_volume") or []
    return {
        "available": True,
        "ts": payload.get("ts"),
        "fear_greed": {
            "value": fg.get("value"),
            "classification": fg.get("classification"),
            "delta_7d": fg.get("delta_7d"),
        },
        "sentiment": {"bias": read.get("bias"),
                      "fear_greed_label": read.get("fear_greed_label"),
                      "spike_queries": read.get("spike_queries") or []},
        "volume_spikes": sum(1 for e in volume if e.get("spike")),
        "trending_coins": [c.get("symbol") for c in trending[:TRENDING_COIN_CAP]
                           if c.get("symbol")],
        "stale": bool(payload.get("stale")),
        "errors": len(payload.get("errors") or []),
        "sources": payload.get("sources") or [],
    }
