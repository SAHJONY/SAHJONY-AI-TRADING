"""Canonical, signed evidence producers with a durable local write-ahead queue.

This module intentionally imports no broker, order, portfolio, or execution code.
Canary is an observation stage only; producing an artifact grants no authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any, Callable, Mapping

ARTIFACT_SCHEMA_VERSION = "1.0"
DEFAULT_SOURCES = {
    "backtest": "backtest-runner", "walk_forward": "walk-forward-evaluator",
    "paper": "paper-result-recorder", "shadow": "shadow-evaluator",
    "canary": "canary-monitor",
}


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest_content(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {name: envelope[name] for name in (
        "schema_version", "artifact_id", "candidate_id", "stage", "timestamp",
        "source", "metrics", "key_id",
    )}


def artifact_digest(envelope: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(digest_content(envelope)).encode()).hexdigest()


def artifact_signature(digest: str, key: str | bytes) -> str:
    raw = key.encode() if isinstance(key, str) else key
    return hmac.new(raw, digest.encode(), hashlib.sha256).hexdigest()


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class EvidenceProducer:
    """Emit immutable envelopes and deliver them from a durable WAL idempotently."""

    def __init__(self, stage: str, *, source: str | None = None,
                 queue_dir: str | Path = "data/promotion_queue",
                 signing_keys: Mapping[str, str | bytes] | None = None,
                 active_key_id: str = "unsigned", allowed_sources: set[str] | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        if stage not in DEFAULT_SOURCES:
            raise ValueError(f"unsupported evidence stage: {stage}")
        self.stage = stage
        self.source = source or DEFAULT_SOURCES[stage]
        self.allowed_sources = allowed_sources or set(DEFAULT_SOURCES.values())
        if self.source not in self.allowed_sources:
            raise ValueError(f"evidence source is not allowlisted: {self.source}")
        self.signing_keys = dict(signing_keys or {})
        self.active_key_id = active_key_id
        if self.signing_keys and active_key_id not in self.signing_keys:
            raise ValueError("active signing key id is absent from key ring")
        self.root = Path(queue_dir)
        self.pending = self.root / "pending"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "producer_state.json"
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def emit(self, candidate_id: str, metrics: Mapping[str, Any], *,
             timestamp: datetime | None = None) -> dict[str, Any]:
        if not candidate_id.strip() or not isinstance(metrics, Mapping):
            raise ValueError("candidate_id and metrics object are required")
        state = self._state()
        now = _utc(timestamp or self.clock())
        previous = state.get("last_timestamp")
        if previous:
            last = datetime.fromisoformat(previous.replace("Z", "+00:00"))
            if now <= last:
                now = last + timedelta(microseconds=1)
        stamp = _iso(now)
        envelope: dict[str, Any] = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_id": f"{self.stage}-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex}",
            "candidate_id": candidate_id, "stage": self.stage, "timestamp": stamp,
            "source": self.source, "metrics": dict(metrics),
            "key_id": self.active_key_id if self.signing_keys else "unsigned",
        }
        envelope["digest"] = artifact_digest(envelope)
        envelope["signature"] = (artifact_signature(envelope["digest"],
                                                    self.signing_keys[self.active_key_id])
                                   if self.signing_keys else None)
        # WAL durability precedes returning the artifact or attempting delivery.
        self._atomic_json(self.pending / f"{envelope['artifact_id']}.json", envelope)
        state.update(last_timestamp=stamp, last_emitted_at=stamp,
                     last_artifact_id=envelope["artifact_id"], last_error=None)
        self._write_state(state)
        return envelope

    def deliver(self, artifact: Mapping[str, Any], sink: Callable[[Mapping[str, Any]], Any]) -> Any:
        artifact_id = str(artifact["artifact_id"])
        path = self.pending / f"{artifact_id}.json"
        if not path.exists():
            self._atomic_json(path, artifact)
        try:
            result = sink(dict(artifact))
        except Exception as exc:
            state = self._state()
            state.update(last_error=f"{type(exc).__name__}: {exc}",
                         last_attempt_at=_iso(_utc(self.clock())))
            self._write_state(state)
            raise
        path.unlink(missing_ok=True)
        state = self._state()
        state.update(last_delivered_at=_iso(_utc(self.clock())), last_error=None)
        self._write_state(state)
        return result

    def retry(self, sink: Callable[[Mapping[str, Any]], Any]) -> list[Any]:
        results = []
        for path in sorted(self.pending.glob("*.json")):
            artifact = json.loads(path.read_text())
            results.append(self.deliver(artifact, sink))
        return results

    def health(self) -> dict[str, Any]:
        pending = sorted(self.pending.glob("*.json"))
        state = self._state()
        return {"stage": self.stage, "source": self.source, "pending": len(pending),
                "oldest_pending_at": (_iso(datetime.fromtimestamp(pending[0].stat().st_mtime,
                                           timezone.utc)) if pending else None), **state,
                "execution_authority": False}

    def _state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            raise RuntimeError("producer state is unreadable; refusing to emit")

    def _write_state(self, state: Mapping[str, Any]) -> None:
        self._atomic_json(self.state_path, state)

    @staticmethod
    def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(canonical_json(value) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


class BacktestEvidenceProducer(EvidenceProducer):
    def __init__(self, **kwargs: Any): super().__init__("backtest", **kwargs)
class WalkForwardEvidenceProducer(EvidenceProducer):
    def __init__(self, **kwargs: Any): super().__init__("walk_forward", **kwargs)
class PaperEvidenceProducer(EvidenceProducer):
    def __init__(self, **kwargs: Any): super().__init__("paper", **kwargs)
class ShadowEvidenceProducer(EvidenceProducer):
    def __init__(self, **kwargs: Any): super().__init__("shadow", **kwargs)
class CanaryEvidenceProducer(EvidenceProducer):
    """Evidence-only canary monitor; cannot activate or execute a strategy."""
    def __init__(self, **kwargs: Any): super().__init__("canary", **kwargs)


def producer_health(queue_dir: str | Path = "data/promotion_queue") -> dict[str, Any]:
    root = Path(queue_dir)
    pending = list(root.glob("**/pending/*.json")) if root.exists() else []
    states = []
    for path in root.glob("**/producer_state.json") if root.exists() else []:
        try:
            states.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            states.append({"last_error": f"unreadable producer state: {path}"})
    emitted = sorted((s.get("last_emitted_at") for s in states if s.get("last_emitted_at")), reverse=True)
    delivered = sorted((s.get("last_delivered_at") for s in states if s.get("last_delivered_at")), reverse=True)
    errors = [s["last_error"] for s in states if s.get("last_error")]
    return {"pending": len(pending), "producer_count": len(states),
            "freshness_timestamp": emitted[0] if emitted else None,
            "last_delivered_at": delivered[0] if delivered else None,
            "last_error": errors[0] if errors else None, "execution_authority": False}
