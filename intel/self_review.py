"""Self-evaluation loop (nightly review agent).

Once per day the review agent:
1. Scores recent decisions — post-mortem win-rates by strategy/symbol/regime,
   council calibration accuracy, Hermes strategy weights.
2. Writes evidence-based lessons into the shared knowledge base
   (knowledge.append_lesson — secret-free, fault-isolated).
3. Flags degrading strategies for the promotion pipeline — and, with
   AUTO_DEMOTE enabled, DEMOTES strategies whose rolling accuracy drops below
   threshold one stage (e.g. live → canary → paper) with the reason recorded.
   Promotion back up requires re-passing the walk-forward gate (the pipeline
   already enforces evidence per stage; demotion events are audit-logged).

It never invents lessons: every lesson cites the evidence (counts, win-rates).
It never touches risk caps, order flow, or credentials.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

log = get_logger("self_review")

_DEMOTE_WIN_RATE = 0.35   # rolling win-rate below this (with enough obs) → demote
_DEMOTE_MIN_OBS = 20
_STAGES = ("research", "backtest", "walk_forward", "paper", "shadow", "canary", "production")
# Evidence keys that gate stages ABOVE a demotion target. Clearing them makes
# stale evidence fail the gate's predecessor checks, so re-promotion needs
# FRESH recorded walk-forward evidence — fail-closed.
_HIGHER_STAGE_EVIDENCE = {
    "walk_forward": ("backtest_passed",),
    "paper": ("walk_forward_passed",),
    "shadow": ("paper_observations", "paper_sharpe", "paper_max_drawdown"),
    "canary": ("shadow_observations", "shadow_sharpe", "shadow_max_drawdown",
               "calibration_error"),
    "production": ("canary_observations", "risk_review_passed"),
}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


class SelfReview:
    def __init__(self, cfg=None, trade_memory=None, promotion=None):
        self.cfg = cfg
        self.trade_memory = trade_memory
        self.promotion = promotion
        self.enabled = str(os.getenv("SELF_REVIEW_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")
        self.auto_demote = str(os.getenv("AUTO_DEMOTE_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")

    def due(self, state: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            return (state.get("self_review") or {}).get("last_run") != _today()
        except Exception:
            return False

    def run(self, state: Dict[str, Any], db=None) -> Dict[str, Any]:
        """Run the nightly review. Fault-isolated: never raises."""
        report: Dict[str, Any] = {"ran": False, "date": _today(), "lessons": [],
                                  "demotions": [], "flags": [], "scores": {}}
        try:
            if not self.due(state):
                return report
            mem = self.trade_memory
            pms = mem._all() if mem is not None else []
            recent = pms[-60:] if len(pms) > 60 else pms

            # 1) score decisions by strategy
            by_strat: Dict[str, List[float]] = {}
            for pm in recent:
                by_strat.setdefault(str(pm.get("strategy") or "?"), []).append(
                    _finite(pm.get("realized_pnl")))
            scores = {}
            for name, pnls in by_strat.items():
                wins = sum(1 for p in pnls if p > 0)
                scores[name] = {"n": len(pnls),
                                "win_rate": round(wins / len(pnls), 3) if pnls else None,
                                "total_pnl": round(sum(pnls), 2)}
            report["scores"] = scores

            # council agent accuracy snapshot
            try:
                from intel.council_calibration import CouncilCalibration
                report["council_accuracy"] = CouncilCalibration().accuracy(state)
            except Exception:
                report["council_accuracy"] = {}

            # 2) evidence-based lessons → knowledge base
            lessons: List[str] = []
            if mem is not None:
                lessons.extend(mem.lessons(limit=20))
            for name, s in scores.items():
                if s["n"] >= _DEMOTE_MIN_OBS and s["win_rate"] is not None:
                    lessons.append(
                        f"strategy '{name}': {s['win_rate']:.0%} win-rate over last "
                        f"{s['n']} closes (${s['total_pnl']:+.2f} total)")
            lessons = lessons[:30]
            report["lessons"] = lessons
            try:
                from intelligence import knowledge
                for lesson in lessons:
                    knowledge.append_lesson({"ts": datetime.now(timezone.utc).isoformat(),
                                             "source": "self_review", "text": lesson})
            except Exception as exc:
                log.warning("lesson persist failed: %s", exc)

            # 3) flag + auto-demote degrading strategies
            demotions, flags = self._review_strategies(state, scores, db)
            report["demotions"] = demotions
            report["flags"] = flags

            state.setdefault("self_review", {})["last_run"] = _today()
            state["self_review"]["last_report"] = {
                "date": report["date"], "lessons": len(lessons),
                "demotions": len(demotions), "flags": len(flags)}
            report["ran"] = True
            return report
        except Exception as exc:  # review never breaks the desk
            log.warning("self-review failed: %s", exc)
            return report

    def _review_strategies(self, state: Dict[str, Any],
                           scores: Dict[str, Dict[str, Any]], db) -> tuple:
        demotions: List[Dict[str, Any]] = []
        flags: List[str] = []
        promo = self.promotion
        if promo is None:
            # still flag from scores even without pipeline access
            for name, s in scores.items():
                if (s["n"] or 0) >= _DEMOTE_MIN_OBS and (s["win_rate"] or 1.0) < _DEMOTE_WIN_RATE:
                    flags.append(f"{name}: win-rate {s['win_rate']:.0%} below "
                                 f"{_DEMOTE_WIN_RATE:.0%} over {s['n']} closes")
            return demotions, flags
        try:
            candidates = promo.database.promotion_candidates()
        except Exception as exc:
            log.warning("promotion candidates unreadable: %s", exc)
            return demotions, flags
        for cand in candidates or []:
            key = str(cand.get("key") or "")
            stage = str(cand.get("stage") or "research")
            s = scores.get(key) or scores.get(str(cand.get("name") or ""))
            if not s or (s["n"] or 0) < _DEMOTE_MIN_OBS:
                continue
            wr = s["win_rate"]
            if wr is None or wr >= _DEMOTE_WIN_RATE:
                continue
            reason = (f"self-review auto-demotion: rolling win-rate {wr:.0%} < "
                      f"{_DEMOTE_WIN_RATE:.0%} over last {s['n']} closes "
                      f"(${s['total_pnl']:+.2f}); re-promotion requires the "
                      f"walk-forward gate")
            flags.append(f"{key}: {reason}")
            if not self.auto_demote:
                continue
            if stage in ("canary", "production", "shadow"):
                try:
                    target = _STAGES[max(0, _STAGES.index(stage) - 1)]
                    res = promo.demote(key, actor="self-review",
                                       reason=reason, target_stage=target,
                                       detail={"win_rate": wr, "n": s["n"],
                                               "total_pnl": s["total_pnl"]})
                    # Stale-evidence invalidation: strip evidence/approvals
                    # gating stages ABOVE the demotion target so re-promotion
                    # must re-satisfy the walk-forward gate from scratch.
                    cleared: List[str] = []
                    try:
                        cand_after = promo.database.promotion_candidate(key) or {}
                        ev = dict(cand_after.get("evidence") or {})
                        appr = dict(cand_after.get("approvals") or {})
                        tgt_idx = _STAGES.index(target)
                        for st in _STAGES[tgt_idx + 1:]:
                            for field in _HIGHER_STAGE_EVIDENCE.get(st, ()):
                                if field in ev:
                                    del ev[field]
                                    cleared.append(field)
                            if st in appr:
                                del appr[st]
                                cleared.append(f"approval:{st}")
                        promo.database.update_promotion_candidate(
                            key, evidence=ev, approvals=appr)
                    except Exception as exc:
                        log.warning("evidence invalidation for %s failed: %s", key, exc)
                    demotions.append({"key": key, "from": res.get("from_stage"),
                                      "to": res.get("to_stage"), "reason": reason,
                                      "evidence_invalidated": sorted(cleared)})
                    log.info("auto-demoted %s %s → %s", key, stage, target)
                except Exception as exc:
                    log.warning("auto-demotion of %s failed: %s", key, exc)
                    flags.append(f"{key}: demotion FAILED ({exc}) — manual review needed")
        return demotions, flags
