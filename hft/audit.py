"""Append-only JSONL audit log (research simulator).

Every event is written as one JSON object per line with a wall-clock
``ts`` (``time.time_ns()``). The file is opened in append mode and never
truncated by this class.

Never log secrets: before writing, any top-level payload key whose name
contains ``secret``, ``key``, ``token``, or ``password``
(case-insensitive) has its value replaced with ``"[REDACTED]"``. This is
defense in depth — callers must still avoid passing secrets to the log in
the first place. Redaction is shallow (top-level keys only); do not nest
secrets inside nested structures.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

REDACTED = "[REDACTED]"
_REDACT_HINTS = ("secret", "key", "token", "password")


class AuditLog:
    """Append-only JSONL event log.

    Parameters
    ----------
    path:
        File to append to (created if missing, never truncated).
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")

    @staticmethod
    def _redact(payload: Dict[Any, Any]) -> Dict[Any, Any]:
        clean: Dict[Any, Any] = {}
        for k, v in payload.items():
            if any(hint in str(k).lower() for hint in _REDACT_HINTS):
                clean[k] = REDACTED
            else:
                clean[k] = v
        return clean

    def log(self, event_type: str, payload: Dict[Any, Any]) -> None:
        """Append one event. ``event_type`` is a short tag (e.g.
        ``"risk_decision"``); ``payload`` must be JSON-serializable and
        must not contain secrets."""
        record = {"ts": time.time_ns(), "event": event_type}
        record.update(self._redact(dict(payload)))
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
