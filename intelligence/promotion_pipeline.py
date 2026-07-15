"""Governed Research -> Production promotion pipeline.

This module manages evidence and approvals only.  It deliberately has no broker
or order interface, and Canary/Production transitions are disabled unless the
host application explicitly opts in at construction time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Any, Dict, Iterable, Mapping


STAGES = ("research", "backtest", "walk_forward", "paper", "shadow", "canary", "production")
ARTIFACT_STAGES = ("backtest", "walk_forward", "paper", "shadow", "canary")
MAX_DRAWDOWN = {"backtest": 0.25, "walk_forward": 0.20, "paper": 0.15,
                "shadow": 0.10, "canary": 0.05}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    blockers: tuple[str, ...]


class PromotionPipeline:
    """Sequential promotion controller backed by the firm's SQLite database."""

    def __init__(self, database, *, allow_canary: bool = False,
                 allow_production: bool = False, artifact_signing_key: str | bytes | None = None,
                 require_signatures: bool = False) -> None:
        self.database = database
        self.allow_canary = bool(allow_canary)
        self.allow_production = bool(allow_production)
        self.artifact_signing_key = (artifact_signing_key.encode() if isinstance(artifact_signing_key, str)
                                     else artifact_signing_key)
        self.require_signatures = bool(require_signatures)

    def register(self, key: str, name: str, kind: str = "strategy") -> Dict[str, Any]:
        return self.database.upsert_promotion_candidate(key, name, kind)

    def sync(self, candidates: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
        for item in candidates:
            self.register(str(item["key"]), str(item.get("name") or item["key"]),
                          str(item.get("kind") or "strategy"))
        return self.database.promotion_candidates()

    def update_evidence(self, key: str, evidence: Mapping[str, Any],
                        *, actor: str = "system") -> Dict[str, Any]:
        current = self._candidate(key)
        merged = dict(current.get("evidence") or {})
        merged.update(dict(evidence))
        self.database.update_promotion_candidate(key, evidence=merged)
        self.database.log_promotion_event(
            key, current["stage"], current["stage"], "evidence", actor,
            True, "evidence updated", {"fields": sorted(evidence)},
        )
        return self._candidate(key)

    def evaluate(self, key: str, target_stage: str | None = None) -> GateResult:
        candidate = self._candidate(key)
        current = candidate["stage"]
        target = target_stage or self._next(current)
        blockers: list[str] = []
        if target not in STAGES:
            return GateResult(False, (f"unknown target stage: {target}",))
        if STAGES.index(target) != STAGES.index(current) + 1:
            blockers.append("promotions must advance exactly one stage")
        evidence = candidate.get("evidence") or {}
        approvals = candidate.get("approvals") or {}
        if not blockers:
            blockers.extend(self._evidence_blockers(target, evidence, approvals))
        return GateResult(not blockers, tuple(blockers))

    def promote(self, key: str, *, actor: str, reason: str,
                target_stage: str | None = None, human_approved: bool = False) -> Dict[str, Any]:
        candidate = self._candidate(key)
        current = candidate["stage"]
        target = target_stage or self._next(current)
        if human_approved:
            approvals = dict(candidate.get("approvals") or {})
            approvals[target] = {"actor": actor, "ts": _now(), "reason": reason}
            self.database.update_promotion_candidate(key, approvals=approvals)
        result = self.evaluate(key, target)
        detail = {"blockers": list(result.blockers), "human_approved": bool(human_approved)}
        self.database.log_promotion_event(
            key, current, target, "promotion", actor, result.allowed, reason, detail,
        )
        if result.allowed:
            self.database.update_promotion_candidate(key, stage=target)
        return {"key": key, "from_stage": current, "to_stage": target,
                "promoted": result.allowed, "blockers": list(result.blockers)}

    def demote(self, key: str, *, actor: str, reason: str,
               target_stage: str | None = None) -> Dict[str, Any]:
        candidate = self._candidate(key)
        current = candidate["stage"]
        current_index = STAGES.index(current)
        target = target_stage or STAGES[max(0, current_index - 1)]
        if target not in STAGES or STAGES.index(target) >= current_index:
            raise ValueError("demotion target must be lower than the current stage")
        self.database.log_promotion_event(
            key, current, target, "demotion", actor, True, reason, {},
        )
        self.database.update_promotion_candidate(key, stage=target)
        return {"key": key, "from_stage": current, "to_stage": target, "demoted": True}

    @staticmethod
    def artifact_hash(artifact_content: Mapping[str, Any]) -> str:
        canonical = json.dumps(dict(artifact_content), sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode()
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def sign_artifact(artifact_content: Mapping[str, Any], signing_key: str | bytes) -> str:
        key = signing_key.encode() if isinstance(signing_key, str) else signing_key
        return hmac.new(key, PromotionPipeline.artifact_hash(artifact_content).encode(),
                        hashlib.sha256).hexdigest()

    def ingest_artifact(self, artifact: Mapping[str, Any], *, actor: str = "evidence-ingestor") -> Dict[str, Any]:
        """Verify, append, merge metrics, and apply fail-closed demotion checks."""
        required = {"artifact_id", "candidate_key", "stage", "created_at", "source",
                    "payload", "payload_hash"}
        missing = sorted(required - set(artifact))
        if missing:
            raise ValueError(f"artifact missing fields: {', '.join(missing)}")
        key, stage = str(artifact["candidate_key"]), str(artifact["stage"])
        self._candidate(key)
        if stage not in ARTIFACT_STAGES:
            raise ValueError(f"unsupported evidence stage: {stage}")
        payload = dict(artifact["payload"])
        content = {name: artifact[name] for name in
                   ("artifact_id", "candidate_key", "stage", "created_at", "source", "payload")}
        expected_hash = self.artifact_hash(content)
        if not hmac.compare_digest(str(artifact["payload_hash"]), expected_hash):
            raise ValueError("artifact payload hash mismatch")
        signature = artifact.get("signature")
        signed = False
        if signature:
            if not self.artifact_signing_key:
                raise ValueError("signed artifact cannot be verified without a signing key")
            expected_signature = self.sign_artifact(content, self.artifact_signing_key)
            if not hmac.compare_digest(str(signature), expected_signature):
                raise ValueError("artifact signature verification failed")
            signed = True
        elif self.require_signatures:
            raise ValueError("artifact signature required by host policy")
        existing = self.database.promotion_artifact(str(artifact["artifact_id"]))
        if existing:
            if existing["payload_hash"] != expected_hash:
                raise ValueError("artifact id already exists with different content")
            return {"artifact_id": existing["artifact_id"], "verified": True,
                    "signed": bool(existing.get("signature")), "duplicate": True,
                    "breaches": [], "demotion": None, "execution_authority": False}
        metrics = payload.get("metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError("artifact payload.metrics must be an object")
        normalized = self._validate_metrics(stage, metrics)
        stored = self.database.record_promotion_artifact({
            **dict(artifact), "candidate_key": key, "stage": stage, "payload": payload,
            "payload_hash": expected_hash, "verified": True, "signature": signature,
            "signer": artifact.get("signer") if signed else None,
        })
        evidence = {f"{stage}_{name}": value for name, value in normalized.items()}
        if stage in ("backtest", "walk_forward"):
            evidence[f"{stage}_passed"] = not self._metric_breaches(stage, normalized)
        self.update_evidence(key, evidence, actor=actor)
        breaches = self._metric_breaches(stage, normalized)
        demotion = None
        candidate = self._candidate(key)
        if breaches and STAGES.index(candidate["stage"]) > 0:
            demotion = self.demote(
                key, actor="automatic-risk-monitor",
                reason="; ".join(breaches),
            )
        self.database.log_promotion_event(
            key, candidate["stage"], candidate["stage"], "artifact_ingestion", actor,
            not breaches, "verified evidence artifact ingested",
            {"artifact_id": stored["artifact_id"], "stage": stage, "signed": signed,
             "breaches": breaches},
        )
        return {"artifact_id": stored["artifact_id"], "verified": True, "signed": signed,
                "duplicate": False,
                "breaches": breaches, "demotion": demotion, "execution_authority": False}

    def snapshot(self, audit_limit: int = 50) -> Dict[str, Any]:
        rows = self.database.promotion_candidates()
        return {
            "stages": list(STAGES),
            "candidates": rows,
            "audit": self.database.promotion_events(audit_limit),
            "artifacts": self.database.promotion_artifacts(audit_limit),
            "canary_enabled": self.allow_canary,
            "production_enabled": self.allow_production,
            "execution_authority": False,
            "policy": "sequential evidence gates and explicit human approval; no execution authority",
        }

    @staticmethod
    def _validate_metrics(stage: str, metrics: Mapping[str, Any]) -> Dict[str, Any]:
        required = {"observations", "sharpe", "max_drawdown", "data_quality",
                    "operational_health"}
        if stage in ("shadow", "canary"):
            required.add("calibration_error")
        missing = sorted(name for name in required if name not in metrics)
        if missing:
            raise ValueError(f"artifact metrics missing: {', '.join(missing)}")
        values = {name: float(metrics[name]) for name in required}
        if values["observations"] < 0:
            raise ValueError("artifact observations cannot be negative")
        for name in ("max_drawdown", "data_quality", "operational_health"):
            if not 0.0 <= values[name] <= 1.0:
                raise ValueError(f"artifact {name} must be between 0 and 1")
        if "calibration_error" in values and not 0.0 <= values["calibration_error"] <= 1.0:
            raise ValueError("artifact calibration_error must be between 0 and 1")
        return values

    @staticmethod
    def _metric_breaches(stage: str, metrics: Mapping[str, float]) -> list[str]:
        breaches = []
        if metrics["max_drawdown"] > MAX_DRAWDOWN[stage]:
            breaches.append(f"{stage} drawdown exceeds {MAX_DRAWDOWN[stage]:.0%}")
        if metrics["data_quality"] < 0.98:
            breaches.append("data quality below 98%")
        if metrics["operational_health"] < 0.95:
            breaches.append("operational health below 95%")
        if stage in ("shadow", "canary") and metrics["calibration_error"] > 0.15:
            breaches.append("calibration error exceeds 15%")
        return breaches

    def _candidate(self, key: str) -> Dict[str, Any]:
        candidate = self.database.promotion_candidate(key)
        if not candidate:
            raise KeyError(f"unknown promotion candidate: {key}")
        return candidate

    @staticmethod
    def _next(stage: str) -> str:
        index = STAGES.index(stage)
        return STAGES[min(index + 1, len(STAGES) - 1)]

    def _evidence_blockers(self, target: str, evidence: Mapping[str, Any],
                           approvals: Mapping[str, Any]) -> list[str]:
        blockers: list[str] = []
        required_flags = {
            "backtest": "research_reviewed",
            "walk_forward": "backtest_passed",
            "paper": "walk_forward_passed",
        }
        flag = required_flags.get(target)
        if flag and not evidence.get(flag):
            blockers.append(f"missing evidence: {flag}")
        if target == "shadow":
            if int(evidence.get("paper_observations", 0) or 0) < 20:
                blockers.append("paper observations below 20")
            if float(evidence.get("paper_sharpe", 0.0) or 0.0) < 0.0:
                blockers.append("paper Sharpe is negative")
            paper_dd = evidence.get("paper_max_drawdown")
            if float(1.0 if paper_dd is None else paper_dd) > 0.15:
                blockers.append("paper drawdown exceeds 15%")
        if target == "canary":
            if int(evidence.get("shadow_observations", 0) or 0) < 100:
                blockers.append("shadow observations below 100")
            if float(evidence.get("shadow_sharpe", 0.0) or 0.0) < 0.25:
                blockers.append("shadow Sharpe below 0.25")
            shadow_dd = evidence.get("shadow_max_drawdown")
            if float(1.0 if shadow_dd is None else shadow_dd) > 0.10:
                blockers.append("shadow drawdown exceeds 10%")
            if not approvals.get("canary"):
                blockers.append("explicit human canary approval missing")
            if not self.allow_canary:
                blockers.append("canary stage disabled by host policy")
        if target == "production":
            if int(evidence.get("canary_observations", 0) or 0) < 50:
                blockers.append("canary observations below 50")
            if not evidence.get("risk_review_passed"):
                blockers.append("independent risk review missing")
            if not approvals.get("production"):
                blockers.append("explicit human production approval missing")
            if not self.allow_production:
                blockers.append("production stage disabled by host policy")
        return blockers
