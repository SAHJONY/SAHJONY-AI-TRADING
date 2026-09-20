"""Segmented cycle-latency telemetry — ADVISORY / MEASUREMENT ONLY.

What this is: a tiny, dependency-free segment timer for the desk cycle. Each
cycle records wall-clock durations for named segments (feed_refresh,
risk_checks, council_deliberate, brain_call, order_submission, reporting, and
the post-cycle intel feeds), keeps rolling p50/p95/p99 per segment in memory
(bounded), and persists them to a small JSON file so they survive restarts.

What this is NOT: a performance fix. This module will NOT make the desk
faster. Its value is:

  * operational — catching latency degradation early (e.g. the p99 of
    feed_refresh tripling week over week is visible in the dashboard's
    "latency" block and in the self-heal snapshot before anyone waits on a
    page);
  * epistemic — it quantifies exactly why latency-sensitive alphas are
    off-limits here: the desk runs on 15-minute GitHub Actions cycles, and
    these numbers make that constraint concrete instead of theoretical.

Hard guarantees (do not weaken):
  * advisory/measurement only — never emits orders, never touches
    credentials, never changes the $10/order, 12%/position, 70% deployed,
    10% daily-drawdown-halt risk envelope;
  * never raises — a timer failure degrades to "telemetry unavailable" for
    that cycle; the trading cycle always continues;
  * no network calls, no heavy computation in the hot path (a couple of
    dict ops + perf_counter per segment; one small JSON write per cycle);
  * no invented data — segments that did not run are ABSENT from the
    summary, never zero-filled;
  * never clears the circuit breaker, re-arms the data feed, or alters live
    trading behavior in any way.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# ── tunables (env-overridable) ───────────────────────────────────────────────
_MAX_CYCLES = int(os.getenv("LATENCY_MAX_CYCLES", "720") or 720)   # ~7.5d @15m
_STALE_AFTER_S = float(os.getenv("LATENCY_STALE_AFTER_S", "86400") or 86400)
_TREND_MIN_SAMPLES = 10        # need this many samples before calling a trend
_TREND_DEGRADED_RATIO = 3.0   # "p99 tripled" → degraded
_ENABLED = str(os.getenv("LATENCY_TELEMETRY_ENABLED", "1")).strip().lower() not in (
    "0", "false", "no", "off")

_NOOP_SUMMARY = {"enabled": False, "unavailable": True, "stale": True,
                 "cycles_recorded": 0, "segments": {}, "notes": ["disabled"]}


# ── percentile math (stdlib only) ────────────────────────────────────────────
def percentile(sorted_values: List[float], q: float) -> Optional[float]:
    """Linear-interpolation percentile of an already-sorted list. None when empty."""
    if not sorted_values:
        return None
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    q = max(0.0, min(1.0, q))
    pos = (n - 1) * q
    lo = int(pos)
    if lo >= n - 1:
        return float(sorted_values[-1])
    frac = pos - lo
    return float(sorted_values[lo] + frac * (sorted_values[lo + 1] - sorted_values[lo]))


# ── persistence ──────────────────────────────────────────────────────────────
def _default_path() -> str:
    try:
        from paths import latency_path
        return latency_path()
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "data", "latency_telemetry.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_records(path: str) -> List[Dict[str, Any]]:
    """Bounded list of {ts, durations}. Returns [] on any failure — never raises."""
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        recs = data.get("cycles") if isinstance(data, dict) else None
        if not isinstance(recs, list):
            return []
        clean = [r for r in recs
                 if isinstance(r, dict) and isinstance(r.get("durations"), dict)]
        return clean[-_MAX_CYCLES:]
    except Exception:
        return []


def _save_records(path: str, records: List[Dict[str, Any]]) -> None:
    """Atomic best-effort write of the bounded record list. Never raises."""
    try:
        records = records[-_MAX_CYCLES:]
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "cycles": records}, fh)
        os.replace(tmp, path)
    except Exception:
        pass


# ── summary ──────────────────────────────────────────────────────────────────
def summarize(records: List[Dict[str, Any]],
              stale_after_s: float = _STALE_AFTER_S) -> Dict[str, Any]:
    """Rolling per-segment p50/p95/p99 + staleness + trend flags.

    Missing segments are absent (not zero-filled). Never raises.
    """
    try:
        now = datetime.now(timezone.utc)
        newest_ts: Optional[str] = None
        newest_age_s: Optional[float] = None
        if records:
            try:
                newest_ts = str(records[-1].get("ts"))
                newest_age_s = (now - datetime.fromisoformat(newest_ts)).total_seconds()
            except Exception:
                newest_age_s = None
        stale = (not records) or (newest_age_s is not None and newest_age_s > stale_after_s)

        by_segment: Dict[str, List[float]] = {}
        for r in records:
            for name, dur in (r.get("durations") or {}).items():
                try:
                    d = float(dur)
                except (TypeError, ValueError):
                    continue
                if d >= 0:
                    by_segment.setdefault(str(name), []).append(d)

        segments: Dict[str, Dict[str, Any]] = {}
        degraded_segments: List[str] = []
        for name, samples in sorted(by_segment.items()):
            n = len(samples)
            ordered = list(samples)          # insertion order == time order
            samples = sorted(samples)        # sorted copy for percentiles
            seg: Dict[str, Any] = {
                "n": n,
                "p50": percentile(samples, 0.50),
                "p95": percentile(samples, 0.95),
                "p99": percentile(samples, 0.99),
                "last": ordered[-1] if ordered else None,
                "trend_ratio": None,
                "degraded": False,
            }
            # trend: p99 of the newer half of the window (in TIME order) vs
            # the older half — a "tripling week over week" shows up here as
            # trend_ratio >= 3.
            if n >= _TREND_MIN_SAMPLES:
                half = n // 2
                older = percentile(sorted(ordered[:half]), 0.99)
                newer = percentile(sorted(ordered[half:]), 0.99)
                if older and older > 0 and newer is not None:
                    ratio = newer / older
                    seg["trend_ratio"] = round(ratio, 3)
                    if ratio >= _TREND_DEGRADED_RATIO:
                        seg["degraded"] = True
                        degraded_segments.append(name)
            # round for a compact dashboard payload
            for k in ("p50", "p95", "p99", "last"):
                if seg[k] is not None:
                    seg[k] = round(seg[k], 3)
            segments[name] = seg

        notes = []
        if not records:
            notes.append("no latency samples recorded yet")
        elif stale:
            notes.append(f"telemetry stale: newest sample older than {stale_after_s:g}s")
        try:
            interrupted_n = sum(1 for r in records if r.get("interrupted"))
        except Exception:
            interrupted_n = 0
        if interrupted_n:
            notes.append(f"{interrupted_n} interrupted cycle(s) recorded — "
                         "partial segments only")
        if degraded_segments:
            notes.append("degraded (p99 trend ≥ 3×): " + ", ".join(degraded_segments))

        return {
            "enabled": True,
            "unavailable": False,
            "stale": bool(stale),
            "cycles_recorded": len(records),
            "newest_ts": newest_ts,
            "segments": segments,
            "degraded_segments": degraded_segments,
            "notes": notes,
        }
    except Exception:
        return {"enabled": False, "unavailable": True, "stale": True,
                "cycles_recorded": 0, "segments": {},
                "notes": ["summary computation failed — telemetry unavailable"]}


# ── cycle recorder ───────────────────────────────────────────────────────────
class CycleRecorder:
    """Per-cycle collector. All methods are fault-isolated: nothing raises."""

    def __init__(self, path: Optional[str] = None,
                 enabled: bool = _ENABLED,
                 max_cycles: int = _MAX_CYCLES):
        self.enabled = bool(enabled)
        self.path = path or _default_path()
        self.max_cycles = max(1, int(max_cycles))
        self.durations: Dict[str, float] = {}
        self.failures = 0            # timer-internal failures this cycle
        self.interrupted = False     # cycle raised before finishing
        self.committed = False
        self._records: List[Dict[str, Any]] = []
        if self.enabled:
            self._records = _load_records(self.path)

    def note(self, name: str, seconds: float) -> None:
        """Add a manual duration sample. Same name accumulates within a cycle."""
        try:
            if not self.enabled:
                return
            d = float(seconds)
            if d < 0 or d != d:      # reject negatives / NaN
                return
            self.durations[str(name)] = self.durations.get(str(name), 0.0) + d
        except Exception:
            self.failures += 1

    def segment(self, name: str):
        """Context manager (and decorator) timing one segment."""
        recorder = self
        nm = str(name)

        class _Segment:
            def __enter__(self):
                try:
                    self._start = time.perf_counter() if recorder.enabled else None
                except Exception:
                    self._start = None
                    recorder.failures += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                try:
                    if self._start is not None:
                        recorder.note(nm, time.perf_counter() - self._start)
                except Exception:
                    recorder.failures += 1
                return False  # NEVER swallow the timed code's exceptions

            def __call__(self, fn: Callable):
                def wrapper(*a, **k):
                    with recorder.segment(nm):
                        return fn(*a, **k)
                wrapper.__name__ = getattr(fn, "__name__", "wrapped")
                return wrapper

        return _Segment()

    def commit(self) -> None:
        """Append this cycle's durations to the rolling store and persist."""
        try:
            if not self.enabled or self.committed:
                return
            self._records.append({"ts": _now_iso(),
                                  "durations": dict(self.durations),
                                  "interrupted": self.interrupted,
                                  "timer_failures": self.failures})
            self._records = self._records[-self.max_cycles:]
            _save_records(self.path, self._records)
            self.committed = True
        except Exception:
            self.failures += 1

    def summary(self) -> Dict[str, Any]:
        """Rolling summary including this cycle's completed segments so far."""
        try:
            if not self.enabled:
                return dict(_NOOP_SUMMARY)
            records = list(self._records)
            if self.durations:
                records.append({"ts": _now_iso(),
                                "durations": dict(self.durations)})
            out = summarize(records)
            if self.failures or self.interrupted:
                out = dict(out)
                out["unavailable"] = self.failures > 0
                notes = list(out.get("notes", []))
                if self.failures:
                    notes.append(f"{self.failures} timer failure(s) this cycle — "
                                 "telemetry unavailable for affected segments")
                if self.interrupted:
                    notes.append("cycle interrupted — partial segments only")
                out["notes"] = notes
            return out
        except Exception:
            return {"enabled": False, "unavailable": True, "stale": True,
                    "cycles_recorded": 0, "segments": {},
                    "notes": ["summary failed — telemetry unavailable"]}


# ── active-cycle wiring (lets run_cycle instrument without signature changes) ─
_ACTIVE: List[CycleRecorder] = []


@contextmanager
def cycle(path: Optional[str] = None, enabled: bool = _ENABLED):
    """Wrap one desk cycle. Commits the cycle on exit (even on exception);
    never raises."""
    rec = CycleRecorder(path=path, enabled=enabled)
    _ACTIVE.append(rec)
    try:
        yield rec
    except Exception as exc:
        try:
            rec.interrupted = True
        except Exception:
            pass
        raise
    finally:
        _ACTIVE.pop() if _ACTIVE and _ACTIVE[-1] is rec else None
        try:
            rec.commit()
        except Exception:
            pass


def _active() -> Optional[CycleRecorder]:
    try:
        return _ACTIVE[-1] if _ACTIVE else None
    except Exception:
        return None


def segment(name: str):
    """Time one segment of the active cycle. Outside a cycle (or disabled),
    a no-op that never raises. Usable as a context manager or decorator."""
    rec = _active()
    if rec is None or not rec.enabled:
        @contextmanager
        def _noop():
            yield None
        cm = _noop()

        def _decorator(fn: Callable):
            def wrapper(*a, **k):
                return fn(*a, **k)
            wrapper.__name__ = getattr(fn, "__name__", "wrapped")
            return wrapper
        cm.__call__ = _decorator  # type: ignore[attr-defined]
        return cm
    return rec.segment(name)


def current_summary() -> Optional[Dict[str, Any]]:
    """Summary of the active cycle's recorder (committed history + in-flight
    segments). None outside a cycle. Never raises — returns a degraded
    payload instead."""
    try:
        rec = _active()
        return rec.summary() if rec is not None else None
    except Exception:
        return {"enabled": False, "unavailable": True, "stale": True,
                "cycles_recorded": 0, "segments": {},
                "notes": ["current summary failed — telemetry unavailable"]}


def get_summary(path: Optional[str] = None) -> Dict[str, Any]:
    """Read-only summary straight from the persisted file — for the reporter
    and the watchdog. Never raises; never touches trading state."""
    try:
        if not _ENABLED:
            return dict(_NOOP_SUMMARY)
        return summarize(_load_records(path or _default_path()))
    except Exception:
        return {"enabled": False, "unavailable": True, "stale": True,
                "cycles_recorded": 0, "segments": {},
                "notes": ["store read failed — telemetry unavailable"]}
