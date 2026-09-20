"""Research-hypothesis registry and trial accounting.

The institutional answer to p-hacking: every research hypothesis is
PRE-REGISTERED before it is tested, with a declared trial budget (the maximum
number of configurations/variations that may be evaluated under it) and success
criteria declared up front. Every backtest/validation run is logged against a
hypothesis id and consumes one trial. The multiple-testing-adjusted Sharpe
hurdle in ``backtest/validation.py`` then reads its honest trial count from
this registry instead of accepting a hand-passed number.

Storage: append-only JSONL at ``data/research_registry.jsonl`` under
SAHJONY_HOME (isolated per desk), the same convention as
``intel/trade_memory.py``.

HONESTY CONTRACT (read this before relying on the numbers):
* The registry prevents fooling yourself ONLY if hypotheses are actually
  registered before testing. It cannot detect unlogged offline experiments,
  runs in another process, or a different SAHJONY_HOME. A trial count is an
  honest floor, never a ceiling.
* Unknowns are recorded as unknown/None — never invented. An unknown
  hypothesis id means ``get_trial_count()`` returns None, not 0.

Advisory/measurement ONLY. This module never emits orders, never touches
credentials, never changes the risk envelope, and never raises on I/O failure
(fault-isolated: failures degrade to a no-op and are logged).
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - exercised when imported from the repo tree
    from paths import home
except Exception:  # pragma: no cover
    def home() -> str:  # type: ignore[misc]
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:  # pragma: no cover
    from utils.logger import get_logger
except Exception:  # pragma: no cover
    import logging

    def get_logger(name: str):  # type: ignore[misc]
        return logging.getLogger(name)

log = get_logger("research_registry")

# hypothesis ids: short, readable, filesystem/log-safe
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Status values a hypothesis can hold. Transitions only move forward and are
# recorded as new events — a record is never edited in place.
_STATUS_OPEN = "open"
_STATUS_VALIDATED = "validated"
_STATUS_REJECTED = "rejected"
_STATUS_WITHDRAWN = "withdrawn"
_STATUS_SUPERSEDED = "superseded"
_FINAL_STATUSES = {_STATUS_VALIDATED, _STATUS_REJECTED, _STATUS_WITHDRAWN,
                   _STATUS_SUPERSEDED}

_UNREGISTERED = "__unregistered__"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    return str(os.getenv("RESEARCH_REGISTRY_ENABLED", "1")).strip().lower() not in (
        "0", "false", "no", "off")


def _valid_id(hypothesis_id: Any) -> bool:
    return isinstance(hypothesis_id, str) and bool(_ID_RE.match(hypothesis_id))


class ResearchRegistry:
    """Append-only registry of research hypotheses with trial accounting.

    Records are immutable once written: registration and status transitions
    are appended as new JSONL events. A hypothesis can be marked
    validated/rejected/withdrawn/superseded, but never edited or deleted.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(home(), "data", "research_registry.jsonl")
        self._lock = threading.Lock()
        self._mem: Optional[List[Dict[str, Any]]] = None  # lazy-loaded cache

    # ── internals ─────────────────────────────────────────────────────────
    def _append(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Append one event to the JSONL ledger. Returns the event, or None if
        persistence is disabled or fails (fault-isolated: never raises)."""
        if not _enabled():
            return None
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, default=str) + "\n")
            with self._lock:
                if self._mem is not None:
                    self._mem.append(event)
            return event
        except Exception as exc:
            log.warning("research_registry persist failed (degraded): %s", exc)
            return None

    def _all(self) -> List[Dict[str, Any]]:
        """All events, oldest first. Lazy-loads from disk once; bad lines are
        skipped, never raised."""
        with self._lock:
            if self._mem is not None:
                return list(self._mem)
            rows: List[Dict[str, Any]] = []
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
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
            self._mem = rows
            return list(rows)

    def _hypotheses(self) -> Dict[str, Dict[str, Any]]:
        """Current view: hypothesis id -> latest registration + status."""
        hyps: Dict[str, Dict[str, Any]] = {}
        for ev in self._all():
            kind = ev.get("event")
            hid = ev.get("hypothesis_id")
            if kind == "registered" and _valid_id(hid):
                hyps[str(hid)] = {"record": ev, "status": _STATUS_OPEN,
                                  "superseded_by": None, "status_ts": None,
                                  "status_note": ""}
            elif kind == "status" and str(hid) in hyps:
                hyps[str(hid)]["status"] = str(ev.get("status") or _STATUS_OPEN)
                hyps[str(hid)]["status_ts"] = ev.get("ts")
                hyps[str(hid)]["status_note"] = ev.get("note") or ""
                if ev.get("status") == _STATUS_SUPERSEDED:
                    hyps[str(hid)]["superseded_by"] = ev.get("superseded_by")
        return hyps

    def _trial_events(self) -> List[Dict[str, Any]]:
        return [ev for ev in self._all() if ev.get("event") == "trial"]

    # ── registration ──────────────────────────────────────────────────────
    def register_hypothesis(self, hypothesis_id: str, statement: str,
                            trial_budget: int, validation_procedure: str,
                            success_criteria: str,
                            supersedes: Optional[str] = None) -> Dict[str, Any]:
        """Pre-register a hypothesis BEFORE testing it.

        Raises ValueError on a bad id, non-positive budget, empty statement, or
        a duplicate id (append-only: an existing hypothesis is never
        overwritten — supersede it instead).
        """
        if not _valid_id(hypothesis_id):
            raise ValueError(f"invalid hypothesis_id: {hypothesis_id!r}")
        statement = (statement or "").strip()
        if not statement:
            raise ValueError("statement must be non-empty")
        try:
            budget = int(trial_budget)
        except (TypeError, ValueError):
            raise ValueError(f"trial_budget must be a positive int, got {trial_budget!r}")
        if budget < 1:
            raise ValueError(f"trial_budget must be >= 1, got {budget}")
        validation_procedure = (validation_procedure or "").strip()
        success_criteria = (success_criteria or "").strip()
        if self.get_hypothesis(hypothesis_id) is not None:
            raise ValueError(
                f"hypothesis '{hypothesis_id}' already registered (append-only: "
                "supersede it instead of re-registering)")
        if supersedes is not None:
            if self.get_hypothesis(supersedes) is None:
                raise ValueError(f"supersedes target '{supersedes}' is not registered")
            self.mark_superseded(supersedes, superseded_by=hypothesis_id,
                                 note="superseded by re-registration")
        event = {
            "event": "registered",
            "ts": _now(),
            "hypothesis_id": hypothesis_id,
            "statement": statement,
            "trial_budget": budget,
            "validation_procedure": validation_procedure or None,
            "success_criteria": success_criteria or None,
            "supersedes": supersedes,
        }
        wrote = self._append(event)
        return wrote if wrote is not None else event

    # ── trial accounting ──────────────────────────────────────────────────
    def record_trial(self, hypothesis_id: Optional[str],
                     config: Optional[Dict[str, Any]] = None,
                     note: str = "") -> Optional[Dict[str, Any]]:
        """Log one backtest/validation run and consume one trial.

        A run with no (or an unknown) hypothesis id is logged as unregistered —
        visible in reports, never silently counted as zero. Returns the trial
        event (with the new consumed count and an overrun flag) or None if the
        registry is disabled / persistence failed.
        """
        hid = hypothesis_id if _valid_id(hypothesis_id) else None
        known = hid is not None and self.get_hypothesis(hid) is not None
        consumed = (self.get_trial_count(hid) or 0) + 1 if known else None
        budget = None
        overrun = None
        if known:
            budget = int(self.get_hypothesis(hid)["record"].get("trial_budget") or 0)
            overrun = consumed > budget if consumed is not None else None
        event = {
            "event": "trial",
            "ts": _now(),
            "hypothesis_id": hid,
            "registered": bool(known),
            "trial_number": consumed,   # per-hypothesis sequence; None if unregistered
            "trial_budget": budget,
            "budget_overrun": bool(overrun) if overrun is not None else None,
            "config": config if isinstance(config, dict) else None,
            "note": (note or "").strip() or None,
        }
        return self._append(event)

    def get_trial_count(self, hypothesis_id: str) -> Optional[int]:
        """Honest number of trials consumed under a hypothesis.

        Returns None (never invented) when the hypothesis is unknown — callers
        must treat None as "unknown", NOT as zero. ``backtest/validation.py``
        uses this instead of a hand-passed number.
        """
        if not _valid_id(hypothesis_id):
            return None
        if self.get_hypothesis(hypothesis_id) is None:
            return None
        return sum(1 for ev in self._trial_events()
                   if ev.get("hypothesis_id") == hypothesis_id)

    def unregistered_runs(self) -> List[Dict[str, Any]]:
        """Trial events with no known hypothesis — the visible audit trail of
        runs that could not be honestly counted."""
        return [ev for ev in self._trial_events() if not ev.get("registered")]

    # ── status transitions (append-only) ──────────────────────────────────
    def _transition(self, hypothesis_id: str, status: str,
                    note: str = "", **extra: Any) -> Dict[str, Any]:
        if self.get_hypothesis(hypothesis_id) is None:
            raise ValueError(f"hypothesis '{hypothesis_id}' is not registered")
        current = self._hypotheses()[hypothesis_id]["status"]
        if current in _FINAL_STATUSES and status != current:
            raise ValueError(
                f"hypothesis '{hypothesis_id}' is already '{current}' "
                "(final; append-only)")
        event = {"event": "status", "ts": _now(), "hypothesis_id": hypothesis_id,
                 "status": status, "note": (note or "").strip() or None}
        event.update(extra)
        wrote = self._append(event)
        return wrote if wrote is not None else event

    def mark_validated(self, hypothesis_id: str, note: str = "") -> Dict[str, Any]:
        """Close a hypothesis as validated (success criteria met)."""
        return self._transition(hypothesis_id, _STATUS_VALIDATED, note)

    def mark_rejected(self, hypothesis_id: str, note: str = "") -> Dict[str, Any]:
        """Close a hypothesis as rejected (criteria not met)."""
        return self._transition(hypothesis_id, _STATUS_REJECTED, note)

    def mark_withdrawn(self, hypothesis_id: str, note: str = "") -> Dict[str, Any]:
        """Withdraw a hypothesis before its budget is consumed."""
        return self._transition(hypothesis_id, _STATUS_WITHDRAWN, note)

    def mark_superseded(self, hypothesis_id: str,
                        superseded_by: Optional[str] = None,
                        note: str = "") -> Dict[str, Any]:
        """Mark a hypothesis superseded by a newer registration."""
        return self._transition(hypothesis_id, _STATUS_SUPERSEDED, note,
                                superseded_by=superseded_by)

    # ── reads ─────────────────────────────────────────────────────────────
    def get_hypothesis(self, hypothesis_id: str) -> Optional[Dict[str, Any]]:
        """Latest registration + status for one hypothesis, or None if unknown."""
        return self._hypotheses().get(str(hypothesis_id))

    def list_hypotheses(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """All hypotheses (optionally filtered by status), oldest first."""
        out = []
        for hid, view in self._hypotheses().items():
            if status is not None and view["status"] != status:
                continue
            rec = dict(view["record"])
            consumed = self.get_trial_count(hid) or 0
            budget = int(rec.get("trial_budget") or 0)
            out.append({
                "hypothesis_id": hid,
                "statement": rec.get("statement"),
                "registered_ts": rec.get("ts"),
                "trial_budget": budget,
                "trials_consumed": consumed,
                "trials_remaining": max(0, budget - consumed),
                "budget_overrun": consumed > budget,
                "status": view["status"],
                "status_ts": view.get("status_ts"),
                "status_note": view.get("status_note"),
                "superseded_by": view.get("superseded_by"),
                "validation_procedure": rec.get("validation_procedure"),
                "success_criteria": rec.get("success_criteria"),
            })
        out.sort(key=lambda h: (h["registered_ts"] or "", h["hypothesis_id"]))
        return out

    def summary_for_status(self) -> Dict[str, Any]:
        """Dashboard block: counts, trial accounting, and overrun flags.
        Fault-isolated: any failure yields a marked-down block, never a crash."""
        try:
            hyps = self.list_hypotheses()
            by_status = {s: 0 for s in
                         (_STATUS_OPEN, _STATUS_VALIDATED, _STATUS_REJECTED,
                          _STATUS_WITHDRAWN, _STATUS_SUPERSEDED)}
            for h in hyps:
                by_status[h["status"]] = by_status.get(h["status"], 0) + 1
            overruns = [h["hypothesis_id"] for h in hyps if h["budget_overrun"]]
            return {
                "available": True,
                "enabled": _enabled(),
                "path": self.path,
                "hypotheses_total": len(hyps),
                "by_status": by_status,
                "open": by_status[_STATUS_OPEN],
                "validated": by_status[_STATUS_VALIDATED],
                "rejected": by_status[_STATUS_REJECTED],
                "trials_consumed_total": sum(h["trials_consumed"] for h in hyps),
                "trial_budget_total": sum(h["trial_budget"] for h in hyps),
                "budget_overruns": overruns,
                "budget_overrun_count": len(overruns),
                "unregistered_runs": len(self.unregistered_runs()),
                "hypotheses": hyps,
            }
        except Exception as exc:
            return {"available": False, "error": type(exc).__name__}

    def report_text(self) -> str:
        """CLI-style human report: open/validated/rejected, trials consumed vs
        budget, overruns flagged. Never raises."""
        try:
            s = self.summary_for_status()
            if not s.get("available"):
                return "research registry: unavailable (%s)" % s.get("error", "?")
            lines = [
                "RESEARCH REGISTRY — hypothesis pre-registration + trial accounting",
                f"path: {s['path']}  (enabled={s['enabled']})",
                f"hypotheses: {s['hypotheses_total']} total — "
                f"{s['open']} open / {s['validated']} validated / "
                f"{s['rejected']} rejected",
                f"trials consumed: {s['trials_consumed_total']} "
                f"(budget total {s['trial_budget_total']})",
            ]
            for h in s["hypotheses"]:
                flag = "  !! BUDGET OVERRUN" if h["budget_overrun"] else ""
                lines.append(
                    f"  [{h['status']:<10}] {h['hypothesis_id']}: "
                    f"trials {h['trials_consumed']}/{h['trial_budget']} — "
                    f"{(h['statement'] or '')[:80]}{flag}")
            if s["budget_overruns"]:
                lines.append("budget overruns: " + ", ".join(s["budget_overruns"]))
            if s["unregistered_runs"]:
                lines.append(
                    f"unregistered runs: {s['unregistered_runs']} "
                    "(logged, NOT counted in any hypothesis)")
            else:
                lines.append("unregistered runs: 0")
            lines.append(
                "note: counts cover only logged runs; unlogged offline experiments "
                "are invisible to this registry")
            return "\n".join(lines)
        except Exception as exc:  # pragma: no cover
            return f"research registry report failed: {type(exc).__name__}"


# ── process-level default (per-desk path via SAHJONY_HOME) ────────────────
_default: Optional[ResearchRegistry] = None
_default_lock = threading.Lock()


def default_registry() -> ResearchRegistry:
    """The desk's registry (data/research_registry.jsonl under SAHJONY_HOME)."""
    global _default
    with _default_lock:
        if _default is None:
            _default = ResearchRegistry()
        return _default


def reset_default_registry() -> None:
    """Test hook: drop the cached default so a fresh path can be used."""
    global _default
    with _default_lock:
        _default = None
