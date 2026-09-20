"""On-chain network intelligence — keyless Bitcoin network telemetry.

Keyless sources (verified live 2026-09-19):
  1. mempool.space — https://mempool.space/api/v1/fees/recommended
     (recommended fees in sat/vB: fastestFee / halfHourFee / hourFee).
  2. mempool.space — https://mempool.space/api/v1/fees/mempool-blocks
     (projected blocks; a block counts as "full" at >= 950_000 vB, the
     ~1M vB block cap — the final catch-all bucket is much larger and is
     excluded from the full-block count).
  3. mempool.space — https://mempool.space/api/blocks/tip/height
     (chain tip height; plain integer, not JSON).
  4. blockchain.info — https://api.blockchain.info/charts/hash-rate
     ?timespan=30days&format=json (network hashrate in TH/s, daily points).
  5. blockchain.info — https://api.blockchain.info/charts/difficulty
     ?timespan=30days&format=json (network difficulty, daily points).

Design notes:
  * Every HTTP call carries an explicit timeout; stdlib + ``requests`` only.
  * No secrets, no API keys anywhere.
  * No invented data: fields a source does not provide are ``None``.
  * ``refresh()`` never raises on source failure — failures are recorded in
    ``errors`` and the payload is marked ``stale``.
  * Fee-pressure thresholds (sat/vB, documented, advisory only):
    calm < 5, normal 5-20, elevated 20-50, high 50-100, extreme >= 100.
  * Congestion thresholds (full projected blocks, documented):
    low 0-2, moderate 3-5, heavy >= 6.
  * The network-health read is BOUNDED: high/elevated fee pressure plus a
    > +2% 30-day hashrate move reads "strong_demand" (constructive);
    calm fees plus a < -2% hashrate move reads "cooling" (cautious);
    everything else reads "steady" (neutral). It is a demand/security
    gauge — INTELLIGENCE ONLY. This module never emits orders, never
    touches credentials, never widens risk caps, and never promises profit.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Source endpoints / constants
# ---------------------------------------------------------------------------

MEMPOOL_FEES_URL = "https://mempool.space/api/v1/fees/recommended"
MEMPOOL_BLOCKS_URL = "https://mempool.space/api/v1/fees/mempool-blocks"
MEMPOOL_TIP_URL = "https://mempool.space/api/blocks/tip/height"
BLOCKCHAIN_HASHRATE_URL = (
    "https://api.blockchain.info/charts/hash-rate?timespan=30days&format=json"
)
BLOCKCHAIN_DIFFICULTY_URL = (
    "https://api.blockchain.info/charts/difficulty?timespan=30days&format=json"
)

HTTP_TIMEOUT = 15
# ~1M vB block weight cap; a projected block at >=95% of cap counts as full.
FULL_BLOCK_VSIZE_VB = 950_000.0
# The catch-all remainder bucket carries the rest of the mempool and is far
# larger than one block — never counted as a "full projected block".
MAX_SINGLE_BLOCK_VSIZE_VB = 1_100_000.0

SOURCES = [
    "mempool.space fees/recommended (keyless)",
    "mempool.space fees/mempool-blocks (keyless)",
    "mempool.space blocks/tip/height (keyless)",
    "blockchain.info hash-rate 30d (keyless)",
    "blockchain.info difficulty 30d (keyless)",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value) -> float | None:
    """Best-effort float conversion; None on missing / non-finite. Never raises."""
    try:
        if value is None or value == "":
            return None
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


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


def _http_get_json(url: str, timeout: float) -> object:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _http_get_text(url: str, timeout: float) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text.strip()


# ---------------------------------------------------------------------------
# 1. Fee market (mempool.space)
# ---------------------------------------------------------------------------

def fetch_fees(timeout: float = HTTP_TIMEOUT) -> dict:
    """Recommended BTC fees in sat/vB. Raises on failure — caller isolates."""
    data = _http_get_json(MEMPOOL_FEES_URL, timeout=timeout)
    data = data if isinstance(data, dict) else {}
    fastest = _finite(data.get("fastestFee"))
    return {
        "fastest_sat_vb": fastest,
        "half_hour_sat_vb": _finite(data.get("halfHourFee")),
        "hour_sat_vb": _finite(data.get("hourFee")),
        "fee_pressure": _fee_pressure_label(fastest),
    }


def _fee_pressure_label(fastest_sat_vb: float | None) -> str | None:
    """Documented thresholds: calm < 5, normal 5-20, elevated 20-50,
    high 50-100, extreme >= 100 (sat/vB)."""
    if fastest_sat_vb is None:
        return None
    if fastest_sat_vb < 5:
        return "calm"
    if fastest_sat_vb < 20:
        return "normal"
    if fastest_sat_vb < 50:
        return "elevated"
    if fastest_sat_vb < 100:
        return "high"
    return "extreme"


# ---------------------------------------------------------------------------
# 2. Projected blocks / congestion (mempool.space)
# ---------------------------------------------------------------------------

def fetch_mempool(timeout: float = HTTP_TIMEOUT) -> dict:
    """Projected blocks + tip height. Raises on failure — caller isolates."""
    data = _http_get_json(MEMPOOL_BLOCKS_URL, timeout=timeout)
    blocks = [b for b in (data or []) if isinstance(b, dict)]

    full = 0
    for b in blocks:
        vsize = _finite(b.get("blockVSize"))
        if vsize is not None and FULL_BLOCK_VSIZE_VB <= vsize <= MAX_SINGLE_BLOCK_VSIZE_VB:
            full += 1

    first = blocks[0] if blocks else {}
    median_fee = _finite(first.get("medianFee"))

    tip_height: int | None = None
    try:
        tip_height = int(_http_get_text(MEMPOOL_TIP_URL, timeout=timeout))
    except (ValueError, TypeError):
        tip_height = None

    return {
        "tip_height": tip_height,
        "projected_blocks": len(blocks),
        "full_projected_blocks": full,
        "median_fee_first_block_sat_vb": median_fee,
        "congestion": _congestion_label(full),
    }


def _congestion_label(full_blocks: int) -> str:
    """Documented thresholds on full projected blocks:
    low 0-2, moderate 3-5, heavy >= 6."""
    if full_blocks >= 6:
        return "heavy"
    if full_blocks >= 3:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# 3. Network security gauges (blockchain.info 30d charts)
# ---------------------------------------------------------------------------

def _parse_chart_series(data: object) -> list[tuple[int, float]]:
    """Extract [(x, y)] from a blockchain.info chart payload; [] if unusable."""
    if not isinstance(data, dict):
        return []
    values = data.get("values")
    if not isinstance(values, list):
        return []
    series = []
    for point in values:
        if not isinstance(point, dict):
            continue
        y = _finite(point.get("y"))
        x = point.get("x")
        if y is not None and isinstance(x, (int, float)):
            series.append((int(x), y))
    return series


def _trend_pct(series: list[tuple[int, float]]) -> float | None:
    """Honest simple trend: (last - first) / first * 100. None when there is
    no usable pair of endpoints."""
    if len(series) < 2:
        return None
    first = series[0][1]
    last = series[-1][1]
    if not first:
        return None
    return round((last - first) / first * 100.0, 2)


def fetch_network(timeout: float = HTTP_TIMEOUT) -> dict:
    """30-day hashrate + difficulty gauges. Raises on failure — caller
    isolates. Each leg is independent: a dead difficulty endpoint must not
    kill the hashrate read."""
    out = {
        "hashrate_th_s": {"latest": None, "change_30d_pct": None},
        "difficulty": {"latest": None, "change_30d_pct": None},
    }
    try:
        series = _parse_chart_series(_http_get_json(BLOCKCHAIN_HASHRATE_URL, timeout=timeout))
        if series:
            out["hashrate_th_s"]["latest"] = series[-1][1]
            out["hashrate_th_s"]["change_30d_pct"] = _trend_pct(series)
    except Exception as exc:
        log.warning("hashrate chart fetch failed: %s", exc)
        raise
    try:
        series = _parse_chart_series(_http_get_json(BLOCKCHAIN_DIFFICULTY_URL, timeout=timeout))
        if series:
            out["difficulty"]["latest"] = series[-1][1]
            out["difficulty"]["change_30d_pct"] = _trend_pct(series)
    except Exception as exc:
        log.warning("difficulty chart fetch failed: %s", exc)
        raise
    return out


# ---------------------------------------------------------------------------
# 4. Bounded network-health read (INTELLIGENCE ONLY)
# ---------------------------------------------------------------------------

def chain_read(fees: dict, mempool: dict, network: dict) -> dict:
    """Derive a bounded demand/security read from raw metrics.

    - high/elevated fee pressure + > +2% 30d hashrate => strong_demand / constructive
    - calm fee pressure + < -2% 30d hashrate        => cooling / cautious
    - otherwise                                     => steady / neutral

    The read always ships with the raw metrics — it is a gauge, never a
    trade directive. Marked INTELLIGENCE ONLY; nothing here widens risk.
    """
    pressure = (fees or {}).get("fee_pressure")
    hr_change = ((network or {}).get("hashrate_th_s") or {}).get("change_30d_pct")

    if pressure in ("elevated", "high", "extreme") and hr_change is not None and hr_change > 2.0:
        label, bias = "strong_demand", "constructive"
        note = ("Fee pressure is elevated while miner hashrate trends up — "
                "on-chain demand and network security both read firm.")
    elif pressure == "calm" and hr_change is not None and hr_change < -2.0:
        label, bias = "cooling", "cautious"
        note = ("Fee pressure is calm while hashrate trends down — on-chain "
                "demand and miner commitment both read soft.")
    else:
        label, bias = "steady", "neutral"
        note = "No clear on-chain demand/security signal this refresh."

    return {
        "label": label,
        "bias": bias,
        "note": note,
        "disclaimer": "INTELLIGENCE ONLY — a demand/security gauge, not a trade directive",
        "ts": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    out_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> dict:
    """Build the full on-chain payload and atomically write it to disk.

    Never raises on source failure — each source is isolated with try/except
    and failures are recorded in ``errors`` with ``stale: true``.
    ``cache_path`` is accepted for interface symmetry with the other intel
    feeds (the endpoints are light; cache-first serving is handled by the
    caller, mirroring main.py's top-traders wiring).
    """
    errors: list[str] = []
    root = _repo_root()
    out_path = Path(out_path) if out_path else root / "public" / "onchain_intel.json"

    fees: dict = {}
    mempool: dict = {}
    network: dict = {}

    try:
        fees = fetch_fees()
    except Exception as exc:
        errors.append(f"fees: {exc}")

    try:
        mempool = fetch_mempool()
    except Exception as exc:
        errors.append(f"mempool: {exc}")

    try:
        network = fetch_network()
    except Exception as exc:
        errors.append(f"network: {exc}")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "stale": bool(errors),
        "errors": errors,
        "fees": fees,
        "mempool": mempool,
        "network": network,
        "chain_read": chain_read(fees, mempool, network),
        "sources": list(SOURCES),
    }
    _atomic_write_json(out_path, payload)
    return payload


def load_payload(path: str | Path | None = None) -> dict:
    """Read a previously written payload; ``{}`` if missing/unparseable."""
    path = Path(path) if path else _repo_root() / "public" / "onchain_intel.json"
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
    fees = payload.get("fees") or {}
    mempool = payload.get("mempool") or {}
    network = payload.get("network") or {}
    return {
        "available": True,
        "ts": payload.get("ts"),
        "fastest_fee_sat_vb": fees.get("fastest_sat_vb"),
        "fee_pressure": fees.get("fee_pressure"),
        "tip_height": mempool.get("tip_height"),
        "congestion": mempool.get("congestion"),
        "full_projected_blocks": mempool.get("full_projected_blocks"),
        "hashrate_th_s": (network.get("hashrate_th_s") or {}).get("latest"),
        "hashrate_30d_pct": (network.get("hashrate_th_s") or {}).get("change_30d_pct"),
        "difficulty_30d_pct": (network.get("difficulty") or {}).get("change_30d_pct"),
        "chain_read": payload.get("chain_read") or {},
        "stale": bool(payload.get("stale")),
        "sources": payload.get("sources") or [],
    }
