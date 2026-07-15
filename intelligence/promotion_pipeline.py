"""Governed Research -> Production promotion pipeline.

This module manages evidence and approvals only.  It deliberately has no broker
or order interface, and Canary/Production transitions are disabled unless the
host application explicitly opts in at construction time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping


STAGES = ("research", "backtest", "walk_forward", "paper", "shadow", "canary", "production")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    blockers: tuple[str, ...]


class PromotionPipeline:
    """Sequential promotion controller backed by the firm's SQLite database."""

    def __init__(self, database, *, allow_canary: bool = False,
                 allow_production: bool = False) -> None:
        self.database = database
        self.allow_canary = bool(allow_canary)
        self.allow_production = bool(allow_production)

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

    def snapshot(self, audit_limit: int = 50) -> Dict[str, Any]:
        rows = self.database.promotion_candidates()
        return {
            "stages": list(STAGES),
            "candidates": rows,
            "audit": self.database.promotion_events(audit_limit),
            "canary_enabled": self.allow_canary,
            "production_enabled": self.allow_production,
            "execution_authority": False,
            "policy": "sequential evidence gates and explicit human approval; no execution authority",
        }

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
