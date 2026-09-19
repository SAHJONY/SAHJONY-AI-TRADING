"""Shared cross-desk knowledge — the "training / shared knowledge" bus.

Lets two desks that trade the SAME universe learn from each other: a paper
"trainer" desk (e.g. Alpaca crypto, more capital + looser gates → explores more
setups) and the live real-money desk (Robinhood crypto, conservative). Both read
and contribute to one pool of realized strategy outcomes, so each desk's Hermes
computes its bounded capital weights from the COMBINED evidence, not just its own.

What's shared: Hermes' decayed per-strategy win/observation counts (``mem['strat']``
— the exact input that becomes the ``[0.70, 1.15]``-clamped strategy_weights) plus
council hit-rates. NOT positions, cash, or account identifiers — sizing decisions
stay per-desk; only the *calibration* is pooled.

Storage: a single secret-free ``public/knowledge.json`` at the repo root — a FIXED
path, deliberately NOT ``SAHJONY_HOME``-routed, so isolated desks share one file
(persisted across cron runs via git). Fully fault-isolated: any read/write problem
degrades to empty/no-op and the trading loop never depends on this succeeding.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from paths import _REPO
from utils.logger import get_logger

log = get_logger("knowledge")


def _path() -> str:
    return os.path.join(_REPO, "public", "knowledge.json")


def load_strat() -> Dict[str, Dict[str, float]]:
    """Return the shared per-strategy memory {name: {'n','w'}}, sanitized.
    Empty dict on any problem (missing file, bad JSON, malformed entries)."""
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for name, v in (data.get("strat") or {}).items():
        try:
            n = float(v.get("n", 0.0))
            w = float(v.get("w", 0.0))
        except (TypeError, ValueError, AttributeError):
            continue
        # w is a decayed win-count, so 0 <= w <= n by construction; clamp to be safe.
        if n >= 0.0 and w >= 0.0:
            out[str(name)] = {"n": n, "w": min(w, n)}
    return out


def save(strat: Dict[str, Dict[str, float]], hit_rates: Dict[str, float],
         *, role: str, cycle: int, ts: str) -> None:
    """Persist the merged strategy pool + hit-rates. Fault-isolated (never raises)."""
    try:
        clean = {}
        for name, v in (strat or {}).items():
            try:
                clean[str(name)] = {"n": round(float(v["n"]), 4),
                                    "w": round(float(v["w"]), 4)}
            except (TypeError, ValueError, KeyError):
                continue
        payload: Dict[str, Any] = {
            "strat": clean,
            "hit_rates": {str(k): float(v) for k, v in (hit_rates or {}).items()
                          if isinstance(v, (int, float))},
            "updated": ts,
            "cycle": cycle,
            "last_writer": role,
        }
        # Preserve sidecar data written by append_lesson() (lessons) and any
        # other keys we don't own: save() rebuilds its own fields, never
        # erases the rest of the shared knowledge base.
        try:
            with open(_path(), "r", encoding="utf-8") as fh:
                prior = json.load(fh)
            if isinstance(prior, dict):
                for k, v in prior.items():
                    if k not in payload:
                        payload[k] = v
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except OSError as exc:
        log.warning("could not write shared knowledge: %s", exc)


_LESSON_CAP = 200


def append_lesson(lesson: Dict[str, Any]) -> None:
    """Append one evidence-based lesson to the shared knowledge base.

    Lessons ride alongside (never overwrite) the strategy pool written by
    save(). Secret-free, fault-isolated: any problem degrades to a no-op.
    """
    try:
        path = _path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        lessons = data.get("lessons")
        if not isinstance(lessons, list):
            lessons = []
        text = str((lesson or {}).get("text") or "").strip()
        if not text:
            return
        lessons.append({
            "ts": str((lesson or {}).get("ts") or ""),
            "source": str((lesson or {}).get("source") or "unknown"),
            "text": text[:500],
        })
        data["lessons"] = lessons[-_LESSON_CAP:]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError as exc:
        log.warning("could not append lesson: %s", exc)
