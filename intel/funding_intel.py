"""Funding-rate + open-interest intelligence (free public data).

Pulls per-ticker funding rates and open interest from keyless public feeds:
- Hyperliquid (https://api.hyperliquid.xyz/info, metaAndAssetCtxs) — primary
- Binance USDⓈ-M futures (fapi.binance.com) — fallback

Identifies crowded longs/shorts per ticker and emits a CONTRARIAN advisory
input for the council: crowded longs (high positive funding + elevated OI) lean
bearish, crowded shorts lean bullish. Advisory only — a bounded tilt, never an
order, never a cap change.

Timeouts, caching (5 min), source attribution, and abstention on failure.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional

import requests

from utils.logger import get_logger

log = get_logger("funding_intel")

_HL_URL = "https://api.hyperliquid.xyz/info"
_BIN_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"
_BIN_OI = "https://fapi.binance.com/fapi/v1/openInterest"
_TIMEOUT = 10
_CACHE_TTL = 300

_cache: Dict[str, tuple] = {}


def _base_symbol(symbol: str) -> str:
    s = str(symbol or "").upper()
    for sep in ("/", "-", ":"):
        if sep in s:
            s = s.split(sep)[0]
    return s.replace("USDT", "").replace("USD", "").strip() or s


def _cached(key: str) -> Optional[Dict[str, Any]]:
    row = _cache.get(key)
    if row and time.time() - row[0] < _CACHE_TTL:
        return dict(row[1])
    return None


def _store(key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _cache[key] = (time.time(), dict(payload))
    return payload


def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def fetch(symbol: str) -> Dict[str, Any]:
    """Return funding/OI intelligence for a ticker. Never raises; abstains cleanly."""
    base = _base_symbol(symbol)
    key = f"funding:{base}"
    hit = _cached(key)
    if hit is not None:
        return hit
    # 1) Hyperliquid (primary — keyless, has funding + OI in one call)
    try:
        r = requests.post(_HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=_TIMEOUT)
        r.raise_for_status()
        meta, ctxs = r.json()
        names = [u["name"] for u in meta.get("universe", [])]
        if base in names:
            ctx = ctxs[names.index(base)]
            funding = _finite(ctx.get("funding"))
            oi = _finite(ctx.get("openInterest"))
            if funding is not None:
                return _store(key, {
                    "status": "ok", "symbol": base,
                    "funding_rate": funding, "open_interest": oi,
                    "source": "hyperliquid",
                    **crowding(funding, oi),
                })
    except Exception as exc:
        log.info("hyperliquid funding fetch failed for %s: %s", base, exc)
    # 2) Binance fallback (two calls)
    try:
        fr = requests.get(_BIN_FUNDING,
                          params={"symbol": f"{base}USDT", "limit": 1},
                          timeout=_TIMEOUT).json()
        oi = requests.get(_BIN_OI, params={"symbol": f"{base}USDT"},
                          timeout=_TIMEOUT).json()
        funding = _finite((fr or [{}])[0].get("fundingRate")) if isinstance(fr, list) else None
        open_interest = _finite(oi.get("openInterest")) if isinstance(oi, dict) else None
        if funding is not None:
            return _store(key, {
                "status": "ok", "symbol": base,
                "funding_rate": funding, "open_interest": open_interest,
                "source": "binance",
                **crowding(funding, open_interest),
            })
    except Exception as exc:
        log.info("binance funding fetch failed for %s: %s", base, exc)
    return _store(key, {"status": "abstained", "symbol": base,
                        "reason": "funding/OI feeds unreachable", "source": None})


def crowding(funding_rate: Optional[float],
             open_interest: Optional[float]) -> Dict[str, Any]:
    """Classify crowding and emit the contrarian tilt in [-0.15, +0.15].

    Crowded longs (persistently positive funding) => contrarian bearish tilt.
    Thresholds are deliberately wide — only clear extremes move the needle."""
    fr = funding_rate if funding_rate is not None else 0.0
    # 8h funding rate; ±0.05% (0.0005) per 8h is already a crowded extreme in crypto.
    if fr >= 0.0005:
        label, tilt = "crowded_longs", -0.15
    elif fr >= 0.0002:
        label, tilt = "leaning_longs", -0.07
    elif fr <= -0.0005:
        label, tilt = "crowded_shorts", 0.15
    elif fr <= -0.0002:
        label, tilt = "leaning_shorts", 0.07
    else:
        label, tilt = "neutral", 0.0
    return {"crowding": label, "contrarian_tilt": tilt,
            "funding_8h_pct": round(fr * 100, 4)}
