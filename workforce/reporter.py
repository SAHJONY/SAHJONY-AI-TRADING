"""Reporter — emits the owner dashboard snapshot and a console health board.

The dashboard (public/index.html) renders public/status.json verbatim, so this
module is the single source of the dashboard's data schema. No secrets are ever
written here — only fund state, agent verdicts, and accounting.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict

from config import Config

# The 12-agent roster + operational workforce, surfaced to the dashboard.
AGENT_ROSTER = [
    ("Citadel Systematic", "Trend / systematic execution"),
    ("Two Sigma Backtest", "Statistical expectancy"),
    ("Bridgewater Risk", "Risk parity / vol targeting"),
    ("Renaissance Patterns", "Mean-reversion"),
    ("Goldman Technical", "Technical analysis"),
    ("JPMorgan Fundamental", "Valuation proxy"),
    ("D.E. Shaw Options", "Vol surface / premium"),
    ("AQR Factor", "Multi-factor investing"),
    ("Citadel Securities MM", "Order-flow microstructure (VPIN)"),
    ("Millennium Pod", "Residual alpha / beta-neutrality"),
    ("Renaissance Medallion", "Regime (HMM) / cointegration"),
    ("Sovereign Wealth", "Secular macro / SAA"),
]
WORKFORCE = [
    ("Research Desk", "Convenes the 12-agent council per ticker"),
    ("Chief Strategist (AI Brain)", "Claude — synthesizes council + counsellors"),
    ("Counsellors", "OpenAI (GPT) + Grok (xAI) — advisory"),
    ("Portfolio Manager", "Strategy assignment + conviction sizing"),
    ("Wheel Options Desk", "Cash-secured puts → covered calls"),
    ("Equity Ladder Desk", "Trailing ratchet + averaging-in"),
    ("Risk Officer", "Hard allocation & total-deployed gatekeeper"),
    ("Execution Trader", "Routes orders to Alpaca paper / sim"),
    ("Treasurer + CRM", "SQLite ledger, investor accounting"),
    ("Reporter", "This dashboard"),
]


# Env-var catalog surfaced to the dashboard's Environment page. We report only
# NAMES + whether each is set (never values), so the static page is secret-free.
ENV_CATALOG = [
    ("ALPACA_API_KEY", "Broker", True, "Alpaca paper API key"),
    ("ALPACA_SECRET_KEY", "Broker", True, "Alpaca paper secret"),
    ("ALPACA_PAPER", "Broker", False, "true = paper (keep true)"),
    ("TICKERS", "Universe", False, "Comma-separated tickers"),
    ("BENCHMARK", "Universe", False, "Benchmark for beta-neutrality"),
    ("ANTHROPIC_API_KEY", "AI Brain", True, "Claude — PRIMARY brain"),
    ("ANTHROPIC_MODEL", "AI Brain", False, "default claude-opus-4-8"),
    ("OPENAI_API_KEY", "AI Counsellor", True, "OpenAI (GPT) counsellor"),
    ("OPENAI_MODEL", "AI Counsellor", False, "default gpt-4o"),
    ("XAI_API_KEY", "AI Counsellor", True, "Grok (xAI) counsellor"),
    ("XAI_MODEL", "AI Counsellor", False, "default grok-2-latest"),
    ("AI_BRAIN_ENABLED", "AI Brain", False, "true to enable LLM overlay"),
    ("VOICE_API_KEY", "Voice (Bland.ai)", True, "Bland.ai API key"),
    ("VOICE_FROM_NUMBER", "Voice (Bland.ai)", False, "outbound caller ID"),
    ("OWNER_PHONE", "Voice (Bland.ai)", False, "owner phone for alerts (+1…)"),
    ("VOICE_ALERTS", "Voice (Bland.ai)", False, "true to enable phone alerts"),
    ("MAX_ALLOCATION_PCT", "Risk", False, "per-position cap (≤0.15)"),
    ("MAX_TOTAL_DEPLOYED_PCT", "Risk", False, "total deployed cap (≤0.80)"),
    ("MIN_COUNCIL_CONVICTION", "Risk", False, "min conviction to trade"),
    ("CYCLE_MINUTES", "Ops", False, "run cadence"),
    ("LOG_LEVEL", "Ops", False, "INFO / DEBUG"),
]


def _env_catalog() -> list:
    out = []
    for name, cat, secret, desc in ENV_CATALOG:
        out.append({"name": name, "category": cat, "secret": secret,
                    "description": desc, "set": bool(os.getenv(name))})
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_status(firm, cfg: Config, state: Dict[str, Any], cycle_result: Dict[str, Any]) -> Dict[str, Any]:
    db = firm.db
    client = firm.client
    eq = cycle_result.get("equity", state.get("equity_last") or 0.0)
    eq0 = state.get("equity_start") or eq or 1.0
    realized = state.get("realized_pnl", 0.0)
    premium = state.get("premium_collected", 0.0)

    council = []
    for r in cycle_result.get("research", []):
        v = r["verdict"]
        council.append({
            "symbol": r["symbol"], "price": round(r["snap"].price, 2),
            "conviction": round(v.conviction, 3), "direction": v.direction,
            "composite": round(v.composite_score, 3),
            "risk_multiplier": round(v.risk_multiplier, 3),
            "agents": [{"name": a.name, "persona": a.persona, "score": round(a.score, 3),
                        "confidence": round(a.confidence, 3), "rationale": a.rationale}
                       for a in v.verdicts],
        })

    positions = []
    for sym, pos in state.get("positions", {}).items():
        shares = pos.get("shares", 0) or 0
        price = client.get_price(sym)
        positions.append({
            "symbol": sym, "strategy": pos.get("strategy", ""),
            "state": pos.get("stage") or "long", "shares": shares,
            "cost_basis": round(pos.get("cost_basis", 0.0), 2), "price": round(price, 2),
            "market_value": round(shares * price, 2),
            "unrealized": round((price - pos.get("cost_basis", price)) * shares, 2) if shares else 0.0,
        })

    brain = cycle_result.get("brain")
    brain_block = {"enabled": cfg.ai_brain_enabled, "used": getattr(brain, "used", False)}
    if brain is not None:
        brain_block.update({
            "posture": brain.posture, "global_risk_multiplier": round(brain.global_risk_multiplier, 3),
            "commentary": brain.commentary, "brain_model": brain.brain_model,
            "counsellors": brain.counsellors,
        })

    return {
        "firm": cfg.firm_name,
        "tagline": "Autonomous multi-agent quant trading — PAPER",
        "mode": cfg.mode,
        "ts": _now(),
        "cycle": state.get("cycle", 0),
        "account": {
            "equity": round(eq, 2), "equity_start": round(eq0, 2),
            "cash": round(cycle_result.get("cash", 0.0), 2),
            "deployed": round(cycle_result.get("deployed", 0.0), 2),
        },
        "pnl": {
            "realized": round(realized, 2), "premium_collected": round(premium, 2),
            "total_return_pct": round((eq / eq0 - 1.0) * 100, 3) if eq0 else 0.0,
        },
        "health": {
            "mode": cfg.mode,
            "broker_online": client.online,
            "market_open": client.is_market_open(),
            "risk_caps": {"per_position_pct": cfg.max_allocation_pct,
                          "total_deployed_pct": cfg.max_total_deployed_pct,
                          "min_conviction": cfg.min_council_conviction},
            "ai_brain": firm.brain.status,
            "voice": firm.notifier.status,
        },
        "council": council,
        "brain": brain_block,
        "positions": positions,
        "crm": db.fund_summary(),
        "recent_trades": db.recent_trades(15),
        "equity_curve": db.equity_history(150),
        "decisions": list(reversed(state.get("history", [])[-25:])),
        "agents_roster": [{"name": n, "role": role} for n, role in AGENT_ROSTER],
        "workforce": [{"role": n, "mandate": m} for n, m in WORKFORCE],
        "executed_this_cycle": cycle_result.get("executed", []),
        "env_catalog": _env_catalog(),
    }


def write_status(status: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2, default=str)
    os.replace(tmp, path)


def console_board(status: Dict[str, Any]) -> str:
    a = status["account"]
    p = status["pnl"]
    lines = [
        "═" * 64,
        f" {status['firm']}  ·  cycle {status['cycle']}  ·  mode={status['mode']}",
        "═" * 64,
        f" Equity ${a['equity']:,.2f}  (start ${a['equity_start']:,.2f}, "
        f"return {p['total_return_pct']:+.2f}%)",
        f" Cash ${a['cash']:,.2f}  ·  Deployed ${a['deployed']:,.2f}  ·  "
        f"Realized ${p['realized']:,.2f}  ·  Premium ${p['premium_collected']:,.2f}",
        f" Market open: {status['health']['market_open']}  ·  Broker online: "
        f"{status['health']['broker_online']}  ·  AI brain: {status['health']['ai_brain']['enabled']}",
        "─" * 64,
        " Council:",
    ]
    for c in status["council"]:
        lines.append(f"   {c['symbol']:<6} conv {c['conviction']:.0%} {c['direction']:<5} "
                     f"score {c['composite']:+.2f} risk×{c['risk_multiplier']:.2f}")
    if status["positions"]:
        lines.append(" Positions:")
        for pos in status["positions"]:
            lines.append(f"   {pos['symbol']:<6} {pos['strategy']:<7} {pos['state']:<14} "
                         f"{pos['shares']} sh @ {pos['cost_basis']} → {pos['price']} "
                         f"(uPnL ${pos['unrealized']:,.0f})")
    else:
        lines.append(" Positions: (flat)")
    crm = status["crm"]
    lines.append(f" CRM: {crm['investors']} investors / {crm['contacts']} contacts · "
                 f"AUM ${crm['aum']:,.0f}")
    lines.append("═" * 64)
    return "\n".join(lines)
