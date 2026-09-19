"""Daily brief — the concise morning report.

Generated once per calendar day (America/Chicago) from REAL status data:
performance, decisions, lessons, today's posture. Rendered two ways:
1. a dashboard panel (status.json → public/index.html "Morning Brief" section)
2. a committed Markdown file: public/daily_brief.md

No invented figures: when a data source is empty the section says so
explicitly ("no closed trades yet", "insufficient history"). Stale state is
labeled with its as-of timestamp.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from utils.logger import get_logger

log = get_logger("daily_brief")

_TZ = ZoneInfo("America/Chicago")
_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "public", "daily_brief.md")


def _today_local() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def due(state: Dict[str, Any]) -> bool:
    try:
        return (state.get("daily_brief") or {}).get("date") != _today_local()
    except Exception:
        return False


def build(*, state: Dict[str, Any], db=None, hermes_report=None,
          healing: Optional[Dict[str, Any]] = None,
          exec_quality: Optional[Dict[str, Any]] = None,
          correlation: Optional[Dict[str, Any]] = None,
          funding_notes: Optional[List[str]] = None,
          trade_memory=None) -> Dict[str, Any]:
    """Assemble the brief from real inputs. Never raises; sections degrade to
    explicit 'no data' lines instead of invented numbers."""
    sections: Dict[str, Any] = {}
    lines: List[str] = []
    today = _today_local()
    now_ct = datetime.now(_TZ).strftime("%Y-%m-%d %H:%M %Z")
    lines.append(f"# Morning Brief — {today}")
    lines.append(f"_Generated {now_ct} from live desk state. Figures are real; "
                 f"empty sections say so._\n")

    # ── performance ──
    eq_start = _finite(state.get("equity_start"))
    eq_last = _finite(state.get("equity_last"))
    realized = _finite(state.get("realized_pnl"))
    if eq_start > 0 and eq_last > 0:
        ret = eq_last / eq_start - 1.0
        perf = (f"Equity ${eq_last:,.2f} (start ${eq_start:,.2f}, "
                f"{ret:+.2%} total), realized P&L ${realized:+,.2f}.")
    else:
        perf = "No equity baseline yet — desk has not completed a cycle."
    sections["performance"] = perf
    lines.append("## Performance"); lines.append(perf)

    # ── decisions (last 24h of post-mortems + open positions) ──
    decisions: List[str] = []
    try:
        pms = (trade_memory._all() if trade_memory is not None else [])[-10:]
        for pm in reversed(pms):
            decisions.append(
                f"{pm.get('symbol')} {pm.get('side')}: "
                f"${_finite(pm.get('realized_pnl')):+.2f} "
                f"({pm.get('regime_at_entry', 'unknown')} regime, "
                f"{pm.get('strategy', '?')})")
    except Exception:
        pass
    positions = state.get("positions") or {}
    if positions:
        decisions.append(f"Open positions: {len(positions)} "
                         f"({', '.join(sorted(positions)[:8])})")
    if not decisions:
        decisions.append("No closed trades and no open positions in the window.")
    sections["decisions"] = decisions
    lines.append("\n## Decisions (recent)"); lines.extend(f"- {d}" for d in decisions)

    # ── lessons ──
    lessons: List[str] = []
    try:
        lessons = (trade_memory.lessons(limit=10) if trade_memory is not None else [])
    except Exception:
        pass
    try:
        sr = (state.get("self_review") or {}).get("last_report") or {}
        if sr.get("demotions"):
            lessons.append(f"Self-review demoted {sr['demotions']} strategy(ies) "
                           f"on rolling accuracy — see promotion audit.")
    except Exception:
        pass
    if not lessons:
        lessons.append("No lessons recorded yet — the desk is still gathering evidence.")
    sections["lessons"] = lessons[:10]
    lines.append("\n## Lessons"); lines.extend(f"- {l}" for l in lessons[:10])

    # ── today's posture ──
    posture: List[str] = []
    halt = state.get("_last_halt") or {}
    if halt.get("halted"):
        posture.append(f"NEW RISK HALTED: {halt.get('reason', 'no reason recorded')}")
    else:
        posture.append("Desk is armed for new risk (all governors green).")
    if healing:
        h = healing.get("health") or {}
        bad = [k for k, v in h.items() if isinstance(v, dict) and v.get("state") != "healthy"]
        if bad:
            posture.append(f"Watch: {', '.join(bad)} not healthy — "
                           f"see healing log ({len(healing.get('log', []))} actions).")
        esc = healing.get("escalation")
        if esc:
            posture.append(f"ESCALATION: {esc.get('note', '')}")
    if correlation and correlation.get("status") == "ok":
        posture.append(f"Correlation-adjusted exposure: ${correlation['effective']:,.0f} "
                       f"effective vs ${correlation['nominal']:,.0f} nominal "
                       f"({correlation.get('advice', '')}).")
    if exec_quality and exec_quality.get("fills_measured"):
        avg = exec_quality.get("avg_slippage_bps")
        posture.append(f"Execution quality: {exec_quality['fills_measured']} fills, "
                       f"avg slippage {avg} bps." if avg is not None
                       else "Execution quality: fills measured, no slippage data yet.")
    if funding_notes:
        posture.extend(funding_notes[:4])
    sections["posture"] = posture
    lines.append("\n## Today's posture"); lines.extend(f"- {p}" for p in posture)

    lines.append(f"\n---\n_Brief generated from desk state at {now_ct}. "
                 f"Nothing in this file is projected or invented._")
    markdown = "\n".join(lines)
    return {"date": today, "generated_at": now_ct, "sections": sections,
            "markdown": markdown}


def publish(brief: Dict[str, Any], state: Dict[str, Any],
            path: Optional[str] = None) -> Optional[str]:
    """Write public/daily_brief.md and stamp state. Returns the path or None."""
    try:
        target = path or _PATH
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(brief["markdown"] + "\n")
        state.setdefault("daily_brief", {})["date"] = brief["date"]
        state["daily_brief"]["path"] = "public/daily_brief.md"
        return target
    except Exception as exc:
        log.warning("daily brief publish failed: %s", exc)
        return None
