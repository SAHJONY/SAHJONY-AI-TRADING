"""IntelDesk — runs the 8-agent Intel Workforce inside the trading cycle.

Every agent is wrapped in its own fault isolation: on ANY exception the agent
produces an ABSTAINED finding with a reason instead of failing the cycle.
``run()`` itself never raises. Advisory only — no agent here can emit an
order, change a risk cap, or touch the live-trading arming chain.
"""
from __future__ import annotations

from typing import Any, Dict, List

from intel.workforce.agents import (
    ALL_INTEL_AGENTS,
    IntelAgent,
    IntelFinding,
    _now,
)
from utils.logger import get_logger

log = get_logger("intel-desk")


class IntelDesk:
    """ctx keys: ``client``, ``db``, ``state``, ``cfg``, ``tickers`` (list[str]),
    ``research`` (the council verdicts per ticker), ``reconciliation`` (optional)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.agents: List[IntelAgent] = list(ALL_INTEL_AGENTS)

    def _fallback(self, agent: Any, reason: str) -> IntelFinding:
        name = str(getattr(agent, "name", "Intel Agent"))
        role = str(getattr(agent, "role", "Advisory"))
        return IntelFinding(
            name=name,
            role=role,
            status="abstained",
            finding=(f"{name} failed this cycle: {reason}. "
                     "No numbers were estimated in place of the missing output."),
            conviction_delta=0.0,
            confidence=0.0,
            rationale=str(reason)[:220],
            inputs=[],
            ts=_now(),
            abstain_reason=str(reason),
        ).clamp()

    def run(self, ctx: Dict[str, Any]) -> List[IntelFinding]:
        findings: List[IntelFinding] = []
        for agent in self.agents:
            try:
                try:
                    f = agent.evaluate(ctx or {})
                except Exception as exc:  # one bad agent never sinks the desk
                    f = self._fallback(
                        agent, f"{type(exc).__name__}: {str(exc)[:200]}")
                if not isinstance(f, IntelFinding):
                    f = self._fallback(
                        agent,
                        f"returned {type(f).__name__} instead of IntelFinding")
                f.clamp()
                # De-risk-only agents (RiskOfficer) may subtract conviction but
                # never add it — belt and braces over the agent's own min(0,·).
                if getattr(agent, "derisk_only", False) and f.conviction_delta > 0:
                    f.conviction_delta = 0.0
                if f.status == "abstained":
                    f.conviction_delta = 0.0
                    f.confidence = 0.0
                findings.append(f)
            except Exception as exc:  # the desk itself never raises
                log.error("intel desk fault for %s: %s",
                          getattr(agent, "name", "?"), exc)
                try:
                    findings.append(self._fallback(
                        agent, f"desk fault: {type(exc).__name__}"))
                except Exception:
                    pass
        return findings
