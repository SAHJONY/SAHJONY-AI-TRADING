"""BTC Options-Flow Intelligence — Deribit options skew / positioning snapshot.

Keyless sources (verified live 2026-09-19):
  1. Deribit public API (no auth, no keys) —
     GET /api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option
     returns per-instrument mark IV (``mark_iv``), open interest in BTC
     (``open_interest``), 24h volume in BTC (``volume`` / ``volume_usd``) and
     the underlying price (``underlying_price``). Instrument names carry
     expiry + strike + C/P (e.g. ``BTC-26MAR27-40000-C``).
  2. Deribit public index price (fallback only) —
     GET /api/v2/public/get_index_price?index_name=btc_usd — used only when
     the book summary yields no usable ``underlying_price``.

Design notes:
  * Every HTTP call carries an explicit timeout; stdlib + ``requests`` only.
  * No secrets, no API keys anywhere.
  * No invented data: fields the source does not provide are ``None`` —
    missing IVs are never estimated; they are reported as ``None`` and
    excluded from the OI-weighted averages.
  * ``refresh()`` never raises on source failure — failures are recorded in
    ``errors`` and the payload is marked ``stale``.
  * The flow read is INTELLIGENCE ONLY — a bounded defensive/neutral read
    for the brain, never an order signal, never a profit promise. The risk
    envelope ($10/order, 12% per position, 70% deployed, 10% daily-drawdown
    halt) is frozen and untouched; this module never emits orders.

Reading guide (heuristic thresholds, documented so the brain can reason):
  * ``put_call_oi_ratio`` — OI-weighted defensive positioning. Above
    PUT_CALL_DEFENSIVE (1.25) = heavy put positioning; below
    PUT_CALL_COMPLACENT (0.80) = call-skewed / complacent.
  * ``skew`` — OI-weighted average put IV minus call IV for an expiry, in
    IV points. Above SKEW_DEFENSIVE (+5.0) = puts trading rich = downside
    fear; below SKEW_AGGRESSIVE (-5.0) = calls rich = upside chase.
  * ``term_slope`` — far-expiry OI-weighted IV minus nearest-expiry IV.
    Negative (backwardation) beyond TERM_BKW_THRESHOLD (-5.0) = near-term
    panic bid; strongly positive beyond TERM_CONTANGO_THRESHOLD (+15.0) =
    calm contango.
  Two or more defensive flags → label "defensive"; one → "watch"; none →
  "neutral".
"""

from __future__ import annotations

import json
import logging
import os
import re
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

DERIBIT_BOOK_SUMMARY_URL = (
    "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
    "?currency=BTC&kind=option"
)
DERIBIT_INDEX_PRICE_URL = (
    "https://www.deribit.com/api/v2/public/get_index_price?index_name=btc_usd"
)

CACHE_TTL_S = 900  # 15 min — be polite, the book summary is one bulk call
HTTP_TIMEOUT_S = 20

# Instrument names look like BTC-26MAR27-40000-C (expiry DDMMMYY, strike, C/P).
INSTRUMENT_RE = re.compile(r"^BTC-(\d{2})([A-Z]{3})(\d{2})-([0-9.]+)-([CP])$")
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Flow-read heuristic thresholds (documented so the brain can audit them).
PUT_CALL_DEFENSIVE = 1.25
PUT_CALL_COMPLACENT = 0.80
SKEW_DEFENSIVE = 5.0
SKEW_AGGRESSIVE = -5.0
TERM_BKW_THRESHOLD = -5.0
TERM_CONTANGO_THRESHOLD = 15.0
MIN_NEAR_EXPIRY_OI_BTC = 50.0  # nearest expiry must matter before it counts

SOURCES = [
    "Deribit public book summary (keyless)",
    "Deribit public index price (keyless, fallback only)",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value) -> float | None:
    """Best-effort finite float; None for anything unusable (never raises)."""
    try:
        if value is None or value is False or value is True:
            return None
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


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


# ---------------------------------------------------------------------------
# 1. Fetch the book summary (cache-first)
# ---------------------------------------------------------------------------

def _read_cache(cache_path: Path) -> list[dict] | None:
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        rows = cached.get("rows") if isinstance(cached, dict) else None
        return rows if isinstance(rows, list) else None
    except (OSError, ValueError):
        return None


def fetch_book_summary(
    cache_path: str | Path | None = None,
    ttl_s: int = CACHE_TTL_S,
    timeout: float = HTTP_TIMEOUT_S,
) -> tuple[list[dict], float | None]:
    """Fetch the Deribit BTC option book summary.

    Returns ``(instruments, underlying_price)``. ``underlying_price`` is the
    median of the per-instrument ``underlying_price`` fields; when none are
    usable, a single fallback index-price call is attempted. On failure the
    last cached rows (any age) are returned; never raises.
    """
    cache_path = Path(cache_path) if cache_path else _repo_root() / "data" / "options_flow_cache.json"

    if ttl_s > 0 and cache_path.exists():
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < ttl_s:
                rows = _read_cache(cache_path)
                if rows is not None:
                    return rows, _median_underlying(rows)
        except OSError:
            pass

    rows: list[dict] = []
    underlying: float | None = None
    try:
        data = _http_get_json(DERIBIT_BOOK_SUMMARY_URL, timeout=timeout)
        result = data.get("result") if isinstance(data, dict) else None
        rows = [r for r in (result or []) if isinstance(r, dict)]
        if not rows:
            raise RuntimeError("Deribit returned an empty result list")
        _atomic_write_json(cache_path, {"ts": _now_iso(), "rows": rows})
        underlying = _median_underlying(rows)
    except Exception as exc:  # network / parse / disk — fall back to stale cache
        log.warning("fetch_book_summary failed (%s); trying stale cache", exc)
        rows = _read_cache(cache_path) or []
        underlying = _median_underlying(rows) if rows else None

    if underlying is None and rows:
        # Fallback only: one index-price call when the book summary carries no
        # usable underlying price.
        try:
            data = _http_get_json(DERIBIT_INDEX_PRICE_URL, timeout=timeout)
            underlying = _finite((data.get("result") or {}).get("index_price") if isinstance(data, dict) else None)
        except Exception as exc:
            log.warning("index-price fallback failed (%s)", exc)
    return rows, underlying


def _median_underlying(rows: list[dict]) -> float | None:
    vals = sorted(v for v in (_finite(r.get("underlying_price")) for r in rows) if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


# ---------------------------------------------------------------------------
# 2. Per-expiry aggregation
# ---------------------------------------------------------------------------

def _parse_expiry(name: str) -> tuple[str | None, str | None]:
    """Return (expiry_iso, kind) for a Deribit option instrument name.

    Names look like ``BTC-26MAR27-40000-C`` → (``2027-03-26``, ``call``).
    Anything else → (None, None); never raises.
    """
    m = INSTRUMENT_RE.match(str(name or ""))
    if not m:
        return None, None
    day, mon, yr2 = m.group(1), m.group(2), m.group(3)
    kind = "call" if m.group(5) == "C" else "put"
    month = MONTHS.get(mon)
    if month is None:
        return None, None
    try:
        year = 2000 + int(yr2)
        dt = datetime(year, month, int(day))
        # Deribit options expire at 08:00 UTC; day-level ISO date is enough.
        return dt.strftime("%Y-%m-%d"), kind
    except ValueError:
        return None, None


def aggregate_expiries(
    rows: list[dict], underlying_price: float | None
) -> tuple[list[dict], dict]:
    """Aggregate per-expiry put/call OI, OI-weighted IVs, and totals.

    Only rows whose instrument name parses are counted. Instruments with
    zero/None open interest contribute nothing (they are noise — thousands
    of illiquid strikes). Returns ``(expiries, totals)``.
    """
    by_expiry: dict[str, dict] = {}
    total_oi_btc = 0.0
    total_vol_btc = 0.0
    total_vol_usd = 0.0

    for row in rows:
        expiry_iso, kind = _parse_expiry(row.get("instrument_name"))
        if expiry_iso is None or kind is None:
            continue
        oi = _finite(row.get("open_interest"))
        if oi is None or oi <= 0:
            continue
        iv = _finite(row.get("mark_iv"))  # IV points, e.g. 56.43
        vol = _finite(row.get("volume"))
        vol_usd = _finite(row.get("volume_usd"))

        slot = by_expiry.setdefault(expiry_iso, {
            "expiry": expiry_iso,
            "put_oi": 0.0, "call_oi": 0.0,
            "put_iv_w": 0.0, "put_iv_n": 0.0,
            "call_iv_w": 0.0, "call_iv_n": 0.0,
            "iv_w": 0.0, "iv_n": 0.0,  # overall OI-weighted IV (term structure)
            "contracts": 0,
        })
        slot[f"{kind}_oi"] += oi
        slot["contracts"] += 1
        if iv is not None and iv > 0:
            slot[f"{kind}_iv_w"] += oi * iv
            slot[f"{kind}_iv_n"] += oi
            slot["iv_w"] += oi * iv
            slot["iv_n"] += oi

        total_oi_btc += oi
        if vol is not None and vol > 0:
            total_vol_btc += vol
        if vol_usd is not None and vol_usd > 0:
            total_vol_usd += vol_usd

    expiries = []
    for expiry_iso in sorted(by_expiry):
        s = by_expiry[expiry_iso]
        put_iv = s["put_iv_w"] / s["put_iv_n"] if s["put_iv_n"] else None
        call_iv = s["call_iv_w"] / s["call_iv_n"] if s["call_iv_n"] else None
        avg_iv = s["iv_w"] / s["iv_n"] if s["iv_n"] else None
        expiries.append({
            "expiry": expiry_iso,
            "put_oi": round(s["put_oi"], 2),
            "call_oi": round(s["call_oi"], 2),
            "put_call_oi_ratio": round(s["put_oi"] / s["call_oi"], 3)
            if s["call_oi"] > 0 else None,
            "put_iv_avg": round(put_iv, 2) if put_iv is not None else None,
            "call_iv_avg": round(call_iv, 2) if call_iv is not None else None,
            # Skew proxy: puts trading rich relative to calls = downside fear.
            "skew": round(put_iv - call_iv, 2)
            if put_iv is not None and call_iv is not None else None,
            "avg_iv": round(avg_iv, 2) if avg_iv is not None else None,
            "total_oi_btc": round(s["put_oi"] + s["call_oi"], 2),
            "contracts": s["contracts"],
        })

    totals = {
        "option_oi_btc": round(total_oi_btc, 2),
        "option_oi_usd": round(total_oi_btc * underlying_price, 2)
        if total_oi_btc and underlying_price else None,
        "volume_24h_btc": round(total_vol_btc, 2),
        "volume_24h_usd": round(total_vol_usd, 2),
    }
    return expiries, totals


# ---------------------------------------------------------------------------
# 3. Bounded flow read
# ---------------------------------------------------------------------------

def flow_read(expiries: list[dict]) -> dict:
    """Derive a bounded crash-risk/defensive read from per-expiry metrics.

    Uses the aggregate put/call OI ratio, the nearest-expiry skew, and the
    term-structure slope (far IV − near IV). Empty/degenerate input → neutral
    with flags explaining why; never "defensive" on missing data.
    """
    label = "INTELLIGENCE ONLY — not a trade signal"
    flags: list[str] = []
    defensive = 0

    total_put = sum(e["put_oi"] for e in expiries)
    total_call = sum(e["call_oi"] for e in expiries)
    pc_ratio = (total_put / total_call) if total_call > 0 else None

    near = expiries[0] if expiries else None
    far = expiries[-1] if expiries and len(expiries) > 1 else None

    if pc_ratio is not None:
        if pc_ratio >= PUT_CALL_DEFENSIVE:
            defensive += 1
            flags.append(f"put/call OI ratio {pc_ratio:.2f} ≥ {PUT_CALL_DEFENSIVE} (heavy put positioning)")
        elif pc_ratio <= PUT_CALL_COMPLACENT:
            flags.append(f"put/call OI ratio {pc_ratio:.2f} ≤ {PUT_CALL_COMPLACENT} (call-skewed / complacent)")

    if near and near.get("skew") is not None and near["total_oi_btc"] >= MIN_NEAR_EXPIRY_OI_BTC:
        skew = near["skew"]
        if skew >= SKEW_DEFENSIVE:
            defensive += 1
            flags.append(f"nearest-expiry put skew +{skew:.1f} IV points (puts trading rich)")
        elif skew <= SKEW_AGGRESSIVE:
            flags.append(f"nearest-expiry put skew {skew:.1f} IV points (calls trading rich)")

    term_slope = None
    if (near and far and near.get("avg_iv") is not None
            and far.get("avg_iv") is not None and far["expiry"] != near["expiry"]):
        term_slope = far["avg_iv"] - near["avg_iv"]
        if term_slope <= TERM_BKW_THRESHOLD:
            defensive += 1
            flags.append(f"term-structure backwardation {term_slope:.1f} (near-term panic bid)")
        elif term_slope >= TERM_CONTANGO_THRESHOLD:
            flags.append(f"term-structure steep contango +{term_slope:.1f} (calm far-end bid)")

    if defensive >= 2:
        bias = "defensive"
    elif defensive == 1:
        bias = "watch"
    else:
        bias = "neutral"
    if not expiries:
        flags.append("no usable option data — neutral by default")
        bias = "neutral"

    return {
        "label": label,
        "bias": bias,
        "put_call_oi_ratio": round(pc_ratio, 3) if pc_ratio is not None else None,
        "nearest_expiry_skew": near.get("skew") if near else None,
        "term_slope": round(term_slope, 2) if term_slope is not None else None,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refresh(
    out_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> dict:
    """Build the full BTC options-flow payload and atomically write it to disk.

    Never raises on source failure — failures are recorded in ``errors``
    with ``stale: true``.
    """
    errors: list[str] = []
    root = _repo_root()
    out_path = Path(out_path) if out_path else root / "public" / "options_flow.json"
    cache_path = Path(cache_path) if cache_path else root / "data" / "options_flow_cache.json"

    expiries: list[dict] = []
    totals: dict = {}
    flow: dict = {}
    underlying_price: float | None = None

    try:
        rows, underlying_price = fetch_book_summary(cache_path=cache_path)
        if not rows:
            raise RuntimeError("Deribit book summary returned no rows (network + cache empty)")
        expiries, totals = aggregate_expiries(rows, underlying_price)
        flow = flow_read(expiries)
    except Exception as exc:
        errors.append(f"deribit_book_summary: {exc}")
        flow = flow_read([])

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "stale": bool(errors),
        "errors": errors,
        "underlying_price": underlying_price,
        "expiries": expiries,
        "totals": totals,
        "flow_read": flow,
        "sources": list(SOURCES),
    }
    _atomic_write_json(out_path, payload)
    return payload


def load_payload(path: str | Path | None = None) -> dict:
    """Read a previously written payload; ``{}`` if missing/unparseable."""
    path = Path(path) if path else _repo_root() / "public" / "options_flow.json"
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
    flow = payload.get("flow_read") or {}
    totals = payload.get("totals") or {}
    expiries = payload.get("expiries") or []
    return {
        "available": True,
        "ts": payload.get("ts"),
        "underlying_price": payload.get("underlying_price"),
        "flow_read": {
            "label": flow.get("label"),
            "bias": flow.get("bias"),
            "put_call_oi_ratio": flow.get("put_call_oi_ratio"),
            "nearest_expiry_skew": flow.get("nearest_expiry_skew"),
            "term_slope": flow.get("term_slope"),
            "flags": flow.get("flags") or [],
        },
        "option_oi_usd": totals.get("option_oi_usd"),
        "volume_24h_usd": totals.get("volume_24h_usd"),
        "expiry_count": len(expiries),
        "stale": bool(payload.get("stale")),
        "sources": payload.get("sources") or [],
    }
