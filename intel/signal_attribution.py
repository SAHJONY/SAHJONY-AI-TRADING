"""Signal attribution ledger — which intelligence engine actually earned what.

Each cycle the desk's research block produces a council verdict per symbol:
12 persona agents each emit a directional score (-1..1) + confidence, blended
into a composite score and a long-conviction. This module snapshots every
agent's directional input per symbol (plus the advisory board's bounded tilt
when available) — engine name, score, confidence, blend contribution, symbol,
entry price, timestamp, cycle id — then, at FIXED horizons after the snapshot
(1h, 4h, 24h), grades each input against the realized signed price move
measured from the desk's OWN subsequent price observations: the per-cycle
``snap.price`` quotes the desk already fetched through its RealtimeGuard'd
marketdata path. Prices are cache-first by construction — the module never
re-fetches, never calls a broker, never touches the network, and never blocks
the cycle.

One JSONL record per (engine, symbol, horizon) is appended to
``data/signal_attribution.jsonl``. Each record carries the input snapshot,
the realized move, and explicit data-quality flags — a missing price is
``None``, never invented; a missing observation is flagged, never
interpolated.

Rankings report per-engine decayed hit-rate and decayed mean signed return in
bps, mirroring ``intel.council_calibration``'s 20-observation neutrality rule:
an engine is ranked only after 20 graded observations.

WHAT THIS DOES NOT DO — read before using:
  * Attribution is CORRELATIONAL, not causal. A high hit-rate means an
    engine's direction coincided with later moves; it does not prove the
    engine caused, predicted, or could monetize them.
  * Horizons are FIXED (1h / 4h / 24h). No window shopping after the fact.
  * It does NOT widen risk. The $10/order, 12%/position, 70% deployed,
    10% daily-drawdown halt envelope is frozen and untouched here. Rankings
    must never be used to raise conviction, size, or exposure.
  * Unknown = None. Failures are recorded in ``errors``/``stale`` flags;
    refresh paths never raise.

MEASUREMENT ONLY — this module never emits orders, never touches
credentials, never promises profit, and never changes live trading behavior.
It does not clear the circuit breaker, re-arm any data feed, or alter the
trading pipeline in any way.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from paths import home
from utils.logger import get_logger

log = get_logger("signal_attribution")

SCHEMA_VERSION = 1

# Fixed attribution horizons: (label, seconds). Never tuned after the fact.
HORIZONS: Tuple[Tuple[str, int], ...] = (
    ("1h", 3600),
    ("4h", 14400),
    ("24h", 86400),
)

_DECAY = 0.97          # exponential decay on memory (mirrors council_calibration)
_MIN_OBS = 20          # graded observations before an engine is ranked
_DEADBAND = 0.05       # |score| below this = abstention, not graded
_SETTLE_GRACE_S = 48 * 3600   # after horizon+grace with no observation → None, flagged
_PRICE_PRUNE_S = 7 * 86400    # price observations older than this are dropped

_LEDGER_NAME = "signal_attribution.jsonl"
_PENDING_NAME = "signal_attribution_pending.json"
_PRICES_NAME = "signal_attribution_prices.jsonl"
_PUBLIC_NAME = "signal_attribution.json"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _data_dir(base: Optional[str] = None) -> str:
    d = os.path.join(base or home(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def _ledger_path(base: Optional[str] = None) -> str:
    return os.path.join(_data_dir(base), _LEDGER_NAME)


def _pending_path(base: Optional[str] = None) -> str:
    return os.path.join(_data_dir(base), _PENDING_NAME)


def _prices_path(base: Optional[str] = None) -> str:
    return os.path.join(_data_dir(base), _PRICES_NAME)


def _public_path(base: Optional[str] = None) -> str:
    p = os.path.join(base or home(), "public")
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, _PUBLIC_NAME)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _enabled() -> bool:
    return str(os.getenv("SIGNAL_ATTRIBUTION_ENABLED", "1")).strip().lower() not in (
        "0", "false", "no", "off")


def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", prefix=os.path.basename(path) + ".",
                               suffix=".tmp")
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


def _append_jsonl(path: str, record: Dict[str, Any]) -> bool:
    """Append one record; never raises. Returns False on failure."""
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        log.warning("signal-attribution append failed (%s): %s", path, exc)
        return False


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        pass
    return rows


# ---------------------------------------------------------------------------
# 1. Snapshot engine inputs from the verdicts already produced this cycle
# ---------------------------------------------------------------------------

def _direction(score: float) -> Optional[int]:
    if score > _DEADBAND:
        return 1
    if score < -_DEADBAND:
        return -1
    return None


def snapshot_engine_inputs(research: Any, cycle_id: Any,
                           ts: Optional[float] = None,
                           board: Any = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Extract per-engine directional inputs from this cycle's research block.

    Never re-runs an engine — it reads the council ``verdicts`` and board
    tilts already produced. Returns (inputs, errors). An input carries the
    engine name, family, persona, score, confidence, blend contribution
    (``score × confidence`` — the agent's term in the council blend numerator,
    un-normalized), symbol, entry price, timestamp and cycle id.

    Symbols without a valid entry price are skipped (error recorded); a
    missing price is never invented.
    """
    inputs: List[Dict[str, Any]] = []
    errors: List[str] = []
    entry_ts = ts if ts is not None else time.time()
    for r in (research or []):
        try:
            if not isinstance(r, dict):
                errors.append("research entry is not a dict — skipped")
                continue
            symbol = str(r.get("symbol") or "?")
            snap = r.get("snap")
            entry_price = _finite(getattr(snap, "price", None))
            if entry_price is None or entry_price <= 0:
                errors.append(f"{symbol}: no valid entry price — inputs skipped")
                continue
            verdict = r.get("verdict")
            verdicts = list(getattr(verdict, "verdicts", None) or [])
            for v in verdicts:
                try:
                    name = str(getattr(v, "name", "?") or "?")
                    score = _finite(getattr(v, "score", None))
                    conf = _finite(getattr(v, "confidence", None))
                    if score is None:
                        continue
                    score = max(-1.0, min(1.0, score))
                    conf = 0.0 if conf is None else max(0.0, min(1.0, conf))
                    inputs.append({
                        "engine": name,
                        "family": "council",
                        "persona": str(getattr(v, "persona", "") or ""),
                        "score": round(score, 4),
                        "confidence": round(conf, 4),
                        "contribution": round(score * conf, 4),
                        "symbol": symbol,
                        "entry_price": entry_price,
                        "entry_ts": entry_ts,
                        "cycle_id": cycle_id,
                    })
                except Exception as exc:
                    errors.append(f"{symbol}: agent input skipped ({exc})")
            # Advisory board tilt — a bounded directional nudge per symbol.
            try:
                b = (board or {}).get(symbol) if hasattr(board, "get") else None
                tilt = _finite(getattr(b, "tilt", None)) if b is not None else None
                if tilt is not None:
                    gate = _finite(getattr(b, "gate", 1.0)) or 0.0
                    inputs.append({
                        "engine": "advisory_board",
                        "family": "advisory_board",
                        "persona": "bounded conviction tilt",
                        "score": round(max(-0.2, min(0.2, tilt)), 4),
                        "confidence": round(max(0.0, min(1.0, gate)), 4),
                        "contribution": round(tilt * gate, 4),
                        "symbol": symbol,
                        "entry_price": entry_price,
                        "entry_ts": entry_ts,
                        "cycle_id": cycle_id,
                    })
            except Exception as exc:
                errors.append(f"{symbol}: board tilt skipped ({exc})")
        except Exception as exc:
            errors.append(f"research entry skipped ({exc})")
    return inputs, errors


def _save_pending(inputs: List[Dict[str, Any]], base: Optional[str] = None) -> int:
    """Persist fresh snapshots into the pending store. Returns count saved."""
    if not inputs:
        return 0
    path = _pending_path(base)
    try:
        store: Dict[str, Any] = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                obj = json.load(fh)
            if isinstance(obj, dict):
                store = obj
        except (OSError, ValueError):
            store = {}
        snaps = store.setdefault("snapshots", {})
        n = 0
        for i in inputs:
            sid = f"{i['entry_ts']:.0f}:{i['symbol']}:{i['engine']}"
            snap = snaps.get(sid)
            if snap is None:
                snap = {
                    "snapshot_id": sid,
                    "symbol": i["symbol"],
                    "entry_price": i["entry_price"],
                    "entry_ts": i["entry_ts"],
                    "cycle_id": i["cycle_id"],
                    "engines": [],
                    "horizons": {label: {"settled": False, "settled_ts": None}
                                 for label, _ in HORIZONS},
                }
                snaps[sid] = snap
            # de-dupe engines within one snapshot
            if not any(e["engine"] == i["engine"] for e in snap["engines"]):
                snap["engines"].append({
                    "engine": i["engine"], "family": i["family"],
                    "persona": i["persona"], "score": i["score"],
                    "confidence": i["confidence"],
                    "contribution": i["contribution"]})
                n += 1
        _atomic_write_json(path, {"schema_version": SCHEMA_VERSION,
                                  "snapshots": snaps})
        return n
    except Exception as exc:
        log.warning("pending snapshot save failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# 2. The desk's own price observations (cache-first, never re-fetched)
# ---------------------------------------------------------------------------

def record_observations(research: Any, ts: Optional[float] = None,
                        base: Optional[str] = None) -> int:
    """Append this cycle's observed prices (one record per symbol).

    Prices come from the research block's ``snap.price`` — quotes the desk
    already fetched through its RealtimeGuard'd marketdata path this cycle.
    Nothing is re-fetched; invalid prices are skipped, never invented.
    Returns the number of observations recorded.
    """
    when = ts if ts is not None else time.time()
    n = 0
    for r in (research or []):
        try:
            if not isinstance(r, dict):
                continue
            symbol = str(r.get("symbol") or "?")
            price = _finite(getattr(r.get("snap"), "price", None))
            if price is None or price <= 0:
                continue
            if _append_jsonl(_prices_path(base),
                             {"symbol": symbol, "price": price,
                              "ts": when, "iso": _now_iso()}):
                n += 1
        except Exception as exc:
            log.warning("observation record skipped: %s", exc)
    _prune_prices(when, base)
    return n


def _prune_prices(now_ts: float, base: Optional[str] = None) -> None:
    """Drop price observations older than _PRICE_PRUNE_S (keeps the file bounded)."""
    path = _prices_path(base)
    try:
        if not os.path.exists(path):
            return
        rows = _read_jsonl(path)
        cutoff = now_ts - _PRICE_PRUNE_S
        kept = [r for r in rows if _finite(r.get("ts")) is not None
                and _finite(r.get("ts")) >= cutoff]
        if len(kept) != len(rows):
            tmp = path + ".prune.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                for r in kept:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, path)
    except Exception as exc:
        log.warning("price log prune skipped: %s", exc)


def _load_observations(base: Optional[str] = None) -> Dict[str, List[Tuple[float, float]]]:
    """symbol → sorted [(ts, price)] of the desk's own observations."""
    obs: Dict[str, List[Tuple[float, float]]] = {}
    for r in _read_jsonl(_prices_path(base)):
        try:
            sym = str(r.get("symbol") or "")
            price = _finite(r.get("price"))
            ts = _finite(r.get("ts"))
            if not sym or price is None or price <= 0 or ts is None:
                continue
            obs.setdefault(sym, []).append((ts, price))
        except Exception:
            continue
    for sym in obs:
        obs[sym].sort(key=lambda x: x[0])
    return obs


def _first_observation_at_or_after(series: List[Tuple[float, float]],
                                   at_ts: float) -> Optional[Tuple[float, float]]:
    """The first observation with ts >= at_ts. No interpolation, ever."""
    for ts, price in series:
        if ts >= at_ts:
            return ts, price
    return None


# ---------------------------------------------------------------------------
# 3. Settle matured horizons → one JSONL record per (engine, symbol, horizon)
# ---------------------------------------------------------------------------

def _settle_snapshot(snap: Dict[str, Any],
                     observations: Dict[str, List[Tuple[float, float]]],
                     now_ts: float) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Settle whichever horizons of one snapshot have matured.

    A horizon matures at entry_ts + horizon_s. It settles against the first
    desk observation at/after that instant. A horizon that has matured but has
    no observation yet stays pending until the grace period expires, after
    which it settles as missing (None + flags) instead of inventing a price.
    Returns (ledger_records, errors).
    """
    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    symbol = str(snap.get("symbol") or "?")
    entry_price = _finite(snap.get("entry_price"))
    entry_ts = _finite(snap.get("entry_ts"))
    if entry_price is None or entry_price <= 0 or entry_ts is None:
        errors.append(f"{symbol}: snapshot lacks a valid entry — cannot settle")
        for label, _ in HORIZONS:
            snap["horizons"][label] = {"settled": True,
                                       "settled_ts": now_ts,
                                       "note": "invalid_entry"}
        return records, errors
    series = observations.get(symbol, [])
    for label, horizon_s in HORIZONS:
        hz = snap["horizons"].get(label) or {}
        if hz.get("settled"):
            continue
        target = entry_ts + horizon_s
        if now_ts < target:
            continue  # not matured yet — stays pending
        found = _first_observation_at_or_after(series, target)
        flags: List[str] = []
        realized_price: Optional[float] = None
        realized_ts: Optional[float] = None
        realized_bps: Optional[float] = None
        if found is None:
            if now_ts >= target + _SETTLE_GRACE_S:
                flags.append("no_observation_after_grace")
            else:
                continue  # grace not expired — keep waiting for observations
        else:
            realized_ts, realized_price = found
            if realized_price and realized_price > 0:
                realized_bps = round(
                    (realized_price - entry_price) / entry_price * 10000.0, 2)
            else:
                realized_price = None
                flags.append("price_missing")
        for eng in snap.get("engines") or []:
            direction = _direction(_finite(eng.get("score")) or 0.0)
            graded = direction is not None and realized_bps is not None
            if direction is None:
                flags_e = flags + ["abstention"]
            elif realized_bps is None:
                flags_e = flags + ["not_graded"]
            else:
                flags_e = flags
            signed = (round(direction * realized_bps, 2)
                      if graded else None)
            hit = (signed > 0) if graded else None
            records.append({
                "schema_version": SCHEMA_VERSION,
                "snapshot_id": snap.get("snapshot_id"),
                "engine": eng.get("engine"),
                "family": eng.get("family"),
                "symbol": symbol,
                "cycle_id": snap.get("cycle_id"),
                "entry_ts": entry_ts,
                "entry_price": entry_price,
                "input": {
                    "score": eng.get("score"),
                    "confidence": eng.get("confidence"),
                    "contribution": eng.get("contribution"),
                },
                "horizon": label,
                "horizon_s": horizon_s,
                "realized_ts": realized_ts,
                "realized_price": realized_price,
                "realized_return_bps": realized_bps,
                "direction": direction,
                "graded": graded,
                "signed_return_bps": signed,
                "hit": hit,
                "flags": flags_e,
                "recorded_ts": _now_iso(),
            })
        snap["horizons"][label] = {"settled": True, "settled_ts": now_ts}
    return records, errors


def settle_matured(now_ts: Optional[float] = None,
                   base: Optional[str] = None) -> Dict[str, Any]:
    """Settle every pending snapshot whose horizons have matured.

    Appends one JSONL record per (engine, symbol, horizon) to the ledger.
    Never raises; returns a stats dict.
    """
    stats = {"settled_records": 0, "pending_remaining": 0,
             "snapshots_cleared": 0, "errors": []}
    try:
        now = now_ts if now_ts is not None else time.time()
        path = _pending_path(base)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                store = json.load(fh)
        except (OSError, ValueError):
            return stats
        snaps = (store.get("snapshots") if isinstance(store, dict) else {}) or {}
        if not snaps:
            return stats
        observations = _load_observations(base)
        ledger = _ledger_path(base)
        remaining: Dict[str, Any] = {}
        for sid, snap in snaps.items():
            if not isinstance(snap, dict):
                continue
            records, errs = _settle_snapshot(snap, observations, now)
            stats["errors"].extend(errs)
            for rec in records:
                if _append_jsonl(ledger, rec):
                    stats["settled_records"] += 1
                else:
                    stats["errors"].append("ledger append failed")
            if all((snap.get("horizons") or {}).get(label, {}).get("settled")
                   for label, _ in HORIZONS):
                stats["snapshots_cleared"] += 1
            else:
                remaining[sid] = snap
        stats["pending_remaining"] = len(remaining)
        try:
            _atomic_write_json(path, {"schema_version": SCHEMA_VERSION,
                                      "snapshots": remaining})
        except Exception as exc:
            stats["errors"].append(f"pending store write failed: {exc}")
        return stats
    except Exception as exc:  # settling never breaks the cycle
        log.warning("settle_matured skipped: %s", exc)
        stats["errors"].append(str(exc))
        return stats


# ---------------------------------------------------------------------------
# 4. Rankings — decayed hit-rate and mean signed return, 20-obs gating
# ---------------------------------------------------------------------------

def _iter_graded(ledger_rows: List[Dict[str, Any]]):
    for r in ledger_rows:
        if not r.get("graded"):
            continue
        signed = _finite(r.get("signed_return_bps"))
        if signed is None:
            continue
        engine = str(r.get("engine") or "?")
        yield engine, str(r.get("family") or "?"), bool(r.get("hit")), signed


def rankings(ledger_rows: Optional[List[Dict[str, Any]]] = None,
             base: Optional[str] = None) -> List[Dict[str, Any]]:
    """Per-engine decayed hit-rate and decayed mean signed return (bps).

    Mirrors ``intel.council_calibration``: exponential decay (_DECAY) so
    recent observations weigh more, and an engine is ranked only after
    _MIN_OBS graded observations — before that it reports ``ranked: False``
    with no hit-rate, exactly like the council's 20-observation neutrality
    rule. Ranked engines sort by decayed mean signed return, descending.
    """
    rows = ledger_rows if ledger_rows is not None else _read_jsonl(_ledger_path(base))
    mem: Dict[str, Dict[str, float]] = {}
    fam: Dict[str, str] = {}
    for engine, family, hit, signed in _iter_graded(rows):
        fam.setdefault(engine, family)
        m = mem.get(engine, {"n": 0.0, "h": 0.0, "s": 0.0})
        m["n"] = m["n"] * _DECAY + 1.0
        m["h"] = m["h"] * _DECAY + (1.0 if hit else 0.0)
        m["s"] = m["s"] * _DECAY + signed
        mem[engine] = m
    out: List[Dict[str, Any]] = []
    for engine, m in mem.items():
        n = m["n"]
        ranked = n >= _MIN_OBS
        out.append({
            "engine": engine,
            "family": fam.get(engine, "?"),
            "observations": round(n, 2),
            "ranked": ranked,
            "decayed_hit_rate": round(m["h"] / n, 3) if ranked else None,
            "decayed_mean_signed_bps": round(m["s"] / n, 2) if ranked else None,
        })
    out.sort(key=lambda e: (not e["ranked"],
                            -(e["decayed_mean_signed_bps"] or 0.0),
                            e["engine"]))
    return out


# ---------------------------------------------------------------------------
# Orchestration: refresh() / load_payload() / summary_for_status()
# ---------------------------------------------------------------------------

def refresh(research: Any = None, cycle_id: Any = None, board: Any = None,
            *, now_ts: Optional[float] = None,
            base: Optional[str] = None) -> Dict[str, Any]:
    """One measurement pass for the cycle. Never raises.

    1. Snapshots this cycle's engine inputs (from the verdicts already
       produced — engines are never re-run).
    2. Records this cycle's observed prices (the desk's own quotes).
    3. Settles any matured horizons against the price observations.
    4. Writes the public payload and returns it.

    Respects SIGNAL_ATTRIBUTION_ENABLED (default on).
    """
    errors: List[str] = []
    try:
        if not _enabled():
            return {"schema_version": SCHEMA_VERSION, "ts": _now_iso(),
                    "enabled": False, "stale": False, "errors": [],
                    "note": "disabled via SIGNAL_ATTRIBUTION_ENABLED"}
        now = now_ts if now_ts is not None else time.time()
        base = base or None

        # 1) snapshot engine inputs
        try:
            inputs, snap_errors = snapshot_engine_inputs(research, cycle_id,
                                                         ts=now, board=board)
            errors.extend(snap_errors)
            saved = _save_pending(inputs, base)
        except Exception as exc:
            errors.append(f"snapshot failed: {exc}")
            inputs, saved = [], 0

        # 2) record the desk's own price observations
        try:
            obs_n = record_observations(research, ts=now, base=base)
        except Exception as exc:
            errors.append(f"observation record failed: {exc}")
            obs_n = 0

        # 3) settle matured horizons
        try:
            settle = settle_matured(now_ts=now, base=base)
            errors.extend(settle.get("errors") or [])
        except Exception as exc:
            errors.append(f"settle failed: {exc}")
            settle = {"settled_records": 0, "pending_remaining": 0,
                      "snapshots_cleared": 0}

        ledger_rows = _read_jsonl(_ledger_path(base))
        ranks = rankings(ledger_rows)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ts": _now_iso(),
            "enabled": True,
            "stale": bool(errors),
            "errors": errors,
            "cycle_id": cycle_id,
            "snapshots_saved": saved,
            "observations_recorded": obs_n,
            "settled_records": settle.get("settled_records", 0),
            "snapshots_cleared": settle.get("snapshots_cleared", 0),
            "pending_snapshots": settle.get("pending_remaining", 0),
            "ledger_records": len(ledger_rows),
            "horizons": [{"label": l, "seconds": s} for l, s in HORIZONS],
            "rankings": ranks,
            "disclaimer": ("attribution is correlational, not causal; "
                           "rankings must never be used to widen risk"),
        }
        try:
            _atomic_write_json(_public_path(base), payload)
        except Exception as exc:
            errors.append(f"public payload write failed: {exc}")
            payload["errors"] = errors
            payload["stale"] = True
        return payload
    except Exception as exc:  # measurement never breaks the cycle
        log.warning("signal-attribution refresh skipped: %s", exc)
        return {"schema_version": SCHEMA_VERSION, "ts": _now_iso(),
                "enabled": True, "stale": True,
                "errors": [f"refresh failed: {exc}"],
                "cycle_id": cycle_id}


def load_payload(path: Optional[str] = None,
                 base: Optional[str] = None) -> Dict[str, Any]:
    """Read the last public payload; ``{}`` when missing/unparseable."""
    p = path or _public_path(base)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def summary_for_status(payload: Optional[Dict[str, Any]] = None,
                       base: Optional[str] = None) -> Dict[str, Any]:
    """Compact dashboard summary: rankings, pending load, freshness."""
    if payload is None:
        payload = load_payload(base=base)
    if not payload:
        return {"available": False}
    ranks = payload.get("rankings") or []
    ranked = [r for r in ranks if r.get("ranked")]
    return {
        "available": True,
        "enabled": bool(payload.get("enabled", True)),
        "ts": payload.get("ts"),
        "ledger_records": payload.get("ledger_records"),
        "pending_snapshots": payload.get("pending_snapshots"),
        "engines_tracked": len(ranks),
        "engines_ranked": len(ranked),
        "min_observations": _MIN_OBS,
        "decay": _DECAY,
        "top": [{"engine": r["engine"],
                 "hit_rate": r["decayed_hit_rate"],
                 "mean_signed_bps": r["decayed_mean_signed_bps"]}
                for r in ranked[:3]],
        "bottom": [{"engine": r["engine"],
                    "hit_rate": r["decayed_hit_rate"],
                    "mean_signed_bps": r["decayed_mean_signed_bps"]}
                   for r in ranked[-3:][::-1]] if ranked else [],
        "stale": bool(payload.get("stale")),
        "errors": len(payload.get("errors") or []),
        "disclaimer": payload.get("disclaimer"),
    }
