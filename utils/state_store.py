"""Persistent, crash-safe state in state.json.

The orchestrator reloads this every cycle, so the bot has continuity across
restarts/crashes. Writes are atomic (temp file + os.replace) so a crash mid-
write can never corrupt the file.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict

from paths import state_path

_MAX_HISTORY = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "created_at": _now_iso(),
        "updated_at": None,
        "cycle": 0,
        "mode": "offline-sim",
        "equity_start": None,
        "equity_last": None,
        "premium_collected": 0.0,     # cumulative option premium (wheel)
        "realized_pnl": 0.0,          # cumulative realized P&L (equity + options)
        "positions": {},              # symbol -> position record (see strategies)
        "history": [],                # rolling event log (most recent last)
    }


def load_state(path: str = None) -> Dict[str, Any]:
    path = path or state_path()
    if not os.path.exists(path):
        return default_state()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        # migrate / backfill missing keys against the default schema
        base = default_state()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError):
        # corrupt or unreadable → start clean rather than crash the loop
        return default_state()


def save_state(state: Dict[str, Any], path: str = None) -> None:
    path = path or state_path()
    state["updated_at"] = _now_iso()
    if len(state.get("history", [])) > _MAX_HISTORY:
        state["history"] = state["history"][-_MAX_HISTORY:]
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=False)
        os.replace(tmp, path)  # atomic on POSIX
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def record_event(state: Dict[str, Any], kind: str, detail: Dict[str, Any]) -> None:
    state.setdefault("history", []).append({"ts": _now_iso(), "kind": kind, **detail})
