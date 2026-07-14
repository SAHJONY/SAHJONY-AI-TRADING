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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Per-investor snapshots are generated at report time and are NOT committed
# (they carry an investor's own name + stake). public/investors/ is gitignored.
INVESTORS_DIR = os.path.join(_ROOT, "public", "investors")

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
    ("Advisory Board", "Buffett/Munger/Macro/Growth/Quant + risk gate"),
    ("Hermes Guardian", "Data integrity, Sharpe scorecard, self-calibration"),
    ("Chief Strategist (AI Brain)", "Claude — synthesizes council + counsellors"),
    ("Counsellors", "OpenAI (GPT) + Grok (xAI) — advisory"),
    ("Portfolio Manager", "Strategy assignment + conviction sizing"),
    ("Wheel Options Desk", "Cash-secured puts → covered calls"),
    ("Credit Spread Desk", "Defined-risk bull put spreads (capped max loss)"),
    ("Pairs / StatArb Desk", "Market-neutral cointegrated spreads (long/short)"),
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
    ("TICKERS", "Universe", False, "Tickers (AAPL… or BTC/USD…)"),
    ("BENCHMARK", "Universe", False, "Benchmark for beta-neutrality"),
    ("MARKET_HOURS", "Universe", False, "us | 24_7 (crypto auto-24/7)"),
    ("SAHJONY_HOME", "Ops", False, "per-account data home (isolation)"),
    ("ANTHROPIC_API_KEY", "AI Brain", True, "Claude — PRIMARY brain"),
    ("ANTHROPIC_MODEL", "AI Brain", False, "default claude-fable-5"),
    ("OPENAI_API_KEY", "AI Counsellor", True, "OpenAI (GPT) counsellor"),
    ("OPENAI_MODEL", "AI Counsellor", False, "default gpt-4o"),
    ("XAI_API_KEY", "AI Counsellor", True, "Grok (xAI) counsellor"),
    ("XAI_MODEL", "AI Counsellor", False, "default grok-2-latest"),
    ("GEMINI_API_KEY", "AI Counsellor", True, "Gemini (Google) counsellor"),
    ("GEMINI_MODEL", "AI Counsellor", False, "default gemini-2.5-pro"),
    ("NVIDIA_API_KEY", "AI Counsellor", True, "NVIDIA NIM — free counsellor + fallback brain"),
    ("NVIDIA_MODEL", "AI Counsellor", False, "default openai/gpt-oss-120b"),
    ("AI_BRAIN_ENABLED", "AI Brain", False, "true to enable LLM overlay"),
    ("AUTO_UPDATE_MODELS", "AI Brain", False, "true = always latest model"),
    ("QUIVER_API_KEY", "Alt-Data", True, "QuiverQuant insider/congress alt-data"),
    ("QUIVER_ENABLED", "Alt-Data", False, "auto-on with a key; false to disable"),
    ("ADVISORS_ENABLED", "Advisory Board", False, "6-agent council overlay (default on)"),
    ("HERMES_ENABLED", "Hermes", False, "background guardian agent (default on)"),
    ("HERMES_GOAL", "Hermes", False, "the desk's well-defined objective"),
    ("CREDIT_SPREADS_ENABLED", "Options", False, "defined-risk put-spread desk (default on)"),
    ("PAIRS_ENABLED", "Pairs / StatArb", False, "market-neutral pairs desk (default on)"),
    ("PAIRS", "Pairs / StatArb", False, "pairs, e.g. SPY:QQQ,GLD:SLV"),
    ("PAIRS_ENTRY_Z", "Pairs / StatArb", False, "spread z-score to enter (default 2.0)"),
    ("SPREAD_SHORT_OTM_PCT", "Options", False, "short put distance below spot"),
    ("SPREAD_WIDTH_PCT", "Options", False, "hedge width (caps max loss)"),
    ("VOICE_API_KEY", "Voice (Bland.ai)", True, "Bland.ai API key"),
    ("VOICE_FROM_NUMBER", "Voice (Bland.ai)", False, "outbound caller ID"),
    ("OWNER_PHONE", "Voice (Bland.ai)", False, "owner phone for alerts (+1…)"),
    ("VOICE_ALERTS", "Voice (Bland.ai)", False, "true to enable phone alerts"),
    ("MAX_ALLOCATION_PCT", "Risk", False, "per-position cap (≤0.15)"),
    ("MAX_TOTAL_DEPLOYED_PCT", "Risk", False, "total deployed cap (≤0.80)"),
    ("MIN_COUNCIL_CONVICTION", "Risk", False, "min conviction to trade"),
    ("MAX_DAILY_DRAWDOWN_PCT", "Risk", False, "daily-loss halt (≤0.25)"),
    ("TRADING_HALT", "Risk", False, "true = kill switch (suspend new risk)"),
    ("VOL_TARGET_ANNUAL", "Risk", False, "vol targeting (0.20 = 20%; 0 disables)"),
    ("DAY_TRADING_ENABLED", "Day Trading / Forex", False, "intraday FX desk on/off"),
    ("FOREX_PAIRS", "Day Trading / Forex", False, "FX universe, e.g. EUR/USD,GBP/USD"),
    ("DAY_TRADE_SYMBOLS", "Day Trading / Forex", False, "extra intraday symbols"),
    ("DAY_TRADE_TARGET_PCT", "Day Trading / Forex", False, "intraday profit target"),
    ("DAY_TRADE_STOP_PCT", "Day Trading / Forex", False, "intraday stop loss"),
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


def _capital_block(db, equity: float, equity_start: float) -> Dict[str, Any]:
    """Separate capital you ADDED from money the strategy MADE. With deposits/
    withdrawals recorded (see treasury), trading P&L = equity − net capital;
    otherwise it falls back to the equity_start baseline."""
    s = db.capital_summary()
    net = s["net_capital"]
    if net > 0:
        trading_pnl = equity - net
        ret = (equity / net - 1.0) * 100
    else:  # no flows recorded → baseline accounting
        trading_pnl = equity - equity_start
        ret = (equity / equity_start - 1.0) * 100 if equity_start else 0.0
    return {
        "deposits": round(s["deposits"], 2),
        "withdrawals": round(s["withdrawals"], 2),
        "net_capital": round(net, 2),
        "flows": s["flows"],
        "trading_pnl": round(trading_pnl, 2),
        "trading_return_pct": round(ret, 3),
    }


def _hermes_block(firm, db, cycle_result: Dict[str, Any]) -> Dict[str, Any]:
    """Hermes guardian status: goal, this cycle's data quality + calibration, and the
    honest Sharpe/Sortino scorecard off the equity curve. Secret-free, fault-isolated."""
    hermes = getattr(firm, "hermes", None)
    if hermes is None:
        return {"enabled": False}
    out: Dict[str, Any] = dict(hermes.status)
    rep = cycle_result.get("hermes")
    if rep is not None:
        out.update({
            "used": getattr(rep, "used", False),
            "data_ok_pct": getattr(rep, "data_ok_pct", 1.0),
            "quarantined": list(getattr(rep, "quarantined", [])),
            "issues": dict(getattr(rep, "issues", {})),
            "hit_rates": dict(getattr(rep, "hit_rates", {})),
            "strategy_weights": dict(getattr(rep, "strategy_weights", {})),
        })
    try:
        out["scorecard"] = hermes.scorecard(db.equity_history_regime(150))
    except Exception:
        out["scorecard"] = {}
    return out


def build_status(firm, cfg: Config, state: Dict[str, Any], cycle_result: Dict[str, Any]) -> Dict[str, Any]:
    db = firm.db
    client = firm.client
    mode = getattr(client, "mode", cfg.mode)   # broker-accurate (Alpaca/IBKR/sim)
    # Real-money armed = a LIVE venue that the operator has deliberately acked.
    live_armed = bool(mode == "LIVE" and cfg.live_trading_ack)
    _tag_mode = {"LIVE": "LIVE — REAL MONEY", "paper": "PAPER",
                 "offline-sim": "OFFLINE SIM"}.get(mode, str(mode).upper())
    eq = float(cycle_result.get("equity", state.get("equity_last") or 0.0) or 0.0)
    raw_eq0 = float(state.get("equity_start") or 0.0)

    # An unfunded account has no valid performance baseline.
    # Do not invent a $1 starting value or report a false -100% return.
    eq0 = raw_eq0 if raw_eq0 > 0.0 else eq
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

    # Broker-reported account + holdings straight from the adapter (e.g. Robinhood's
    # own numbers), shown next to the desk's internal book so the two reconcile.
    # Every call is fault-isolated in the adapter; guard again here so the snapshot
    # never fails to build.
    try:
        b_acct = client.get_account() or {}
    except Exception:
        b_acct = {}
    broker_holdings = []
    try:
        for sym, h in (client.get_broker_positions() or {}).items():
            broker_holdings.append({
                "symbol": sym,
                "qty": round(float(h.get("qty", 0.0) or 0.0), 8),
                "avg_price": round(float(h.get("avg_price", 0.0) or 0.0), 2),
                "market_value": round(float(h.get("market_value", 0.0) or 0.0), 2),
            })
    except Exception:
        pass
    broker_account = {
        "venue": cfg.broker,
        "mode": mode,
        "online": client.online,
        "live_armed": live_armed,
        "equity": round(float(b_acct.get("equity", 0.0) or 0.0), 2),
        "cash": round(float(b_acct.get("cash", 0.0) or 0.0), 2),
        "buying_power": round(float(b_acct.get("buying_power", 0.0) or 0.0), 2),
        "holdings": broker_holdings,
    }

    # Robinhood/venue account roster from accounts.yaml (AccountOrchestrator) —
    # masked identifiers only (***last4), so the snapshot stays secret-free.
    # Fault-isolated: a missing/broken accounts.yaml never sinks the snapshot.
    try:
        from accounts.orchestrator import AccountOrchestrator
        accounts_block = AccountOrchestrator(os.path.join(_ROOT, "accounts.yaml")).summary()
    except Exception:
        accounts_block = {"count": 0, "enabled": 0, "accounts": []}

    brain = cycle_result.get("brain")
    brain_block = {"enabled": cfg.ai_brain_enabled, "used": getattr(brain, "used", False)}
    if brain is not None:
        brain_block.update({
            "posture": brain.posture, "global_risk_multiplier": round(brain.global_risk_multiplier, 3),
            "commentary": brain.commentary, "brain_model": brain.brain_model,
            "counsellors": brain.counsellors,
            "telemetry": brain.telemetry,
        })
    brain_block["shadow_evaluation"] = cycle_result.get("ai_shadow") or {}

    # Benchmark (buy-and-hold SPY) anchored at the desk's first cycle, persisted in
    # state — gives an HONEST alpha-vs-market number instead of a bare return.
    bench = {}
    try:
        bsym = (cfg.benchmark or "SPY").upper()
        bpx = float(client.get_price(bsym))
        if bpx > 0:
            b0 = state.get("benchmark_start") or bpx
            state["benchmark_start"] = b0           # anchor once; main.py persists state
            bret = (bpx / b0 - 1.0) * 100 if b0 else 0.0
            total_ret = (eq / eq0 - 1.0) * 100 if eq0 else 0.0
            bench = {"symbol": bsym, "start_price": round(b0, 2), "last_price": round(bpx, 2),
                     "return_pct": round(bret, 3), "alpha_pct": round(total_ret - bret, 3)}
    except Exception:  # benchmark is informational — never break the cycle
        bench = {}

    from intelligence.strategy_ranking import rank_strategies
    from intelligence.global_performance import global_performance
    from intelligence.self_improvement import self_improvement_score
    strategy_ranking = rank_strategies(state, cycle_result.get("ai_shadow") or {})
    performance = global_performance(db.equity_history_regime(500))
    improvement = self_improvement_score(
        state, cycle_result.get("ai_shadow") or {}, cfg.ai_shadow_min_observations
    )
    return {
        "firm": cfg.firm_name,
        "tagline": f"Autonomous multi-agent quant trading — {_tag_mode}",
        "mode": mode,
        "broker": cfg.broker,
        "benchmark": bench,
        "ts": _now(),
        "cycle": state.get("cycle", 0),
        "strategy_ranking": strategy_ranking,
        "global_performance": performance,
        "self_improvement": improvement,
        "account": {
            "equity": round(eq, 2), "equity_start": round(eq0, 2),
            "cash": round(cycle_result.get("cash", 0.0), 2),
            "deployed": round(cycle_result.get("deployed", 0.0), 2),
        },
        "pnl": {
            "realized": round(realized, 2), "premium_collected": round(premium, 2),
            "total_return_pct": round((eq / eq0 - 1.0) * 100, 3) if eq0 > 0.0 else 0.0,
        },
        "capital": _capital_block(db, eq, eq0),
        "capital_flows": db.capital_ledger(20),
        "health": {
            "mode": mode,
            "broker": cfg.broker,
            "live_armed": live_armed,
            "broker_online": client.online,
            "market_open": client.is_market_open(),
            "risk_caps": {"per_position_pct": cfg.max_allocation_pct,
                          "total_deployed_pct": cfg.max_total_deployed_pct,
                          "min_conviction": cfg.min_council_conviction,
                          "daily_drawdown_pct": cfg.max_daily_drawdown_pct},
            "vol_targeting": {"target_annual": getattr(cfg, "vol_target_annual", 0.0),
                              "scale": cycle_result.get("vol_scale", 1.0)},
            "circuit_breaker": cycle_result.get("halt", {"halted": False, "reason": ""}),
            "ai_brain": firm.brain.status,
            "alt_data": getattr(firm, "alt", None).status if getattr(firm, "alt", None) else {"enabled": False},
            "hermes": _hermes_block(firm, db, cycle_result),
            "advisory_board": getattr(firm, "board", None).status if getattr(firm, "board", None) else {"enabled": False},
            "voice": firm.notifier.status,
        },
        "advisors": [
            {"symbol": v.symbol, "scores": v.scores, "gate": v.gate,
             "composite": v.composite, "tilt": v.tilt, "rationale": v.rationale}
            for v in (cycle_result.get("board") or {}).values()
        ],
        "council": council,
        "brain": brain_block,
        "positions": positions,
        "broker_account": broker_account,
        "accounts": accounts_block,
        "crm": db.fund_summary(),
        "recent_trades": db.recent_trades(15),
        "equity_curve": db.equity_history_regime(150),
        "decisions": list(reversed(state.get("history", [])[-25:])),
        "agents_roster": [{"name": n, "role": role} for n, role in AGENT_ROSTER],
        "workforce": [{"role": n, "mandate": m} for n, m in WORKFORCE],
        "executed_this_cycle": cycle_result.get("executed", []),
        "env_catalog": _env_catalog(),
    }


def build_investor_view(status: Dict[str, Any], investor: Dict[str, Any],
                        total_units: float) -> Dict[str, Any]:
    """A read-only statement for ONE investor: their stake + fund-level aggregates.

    Contains no other investor's data and no secrets. The fund's current NAV per
    unit is marked from trading equity, so an investor's value tracks the fund
    proportionally to their units (standard pooled-fund accounting)."""
    equity = float(status.get("account", {}).get("equity", 0.0) or 0.0)
    units = float(investor.get("units", 0.0) or 0.0)
    contributed = float(investor.get("contributed", 0.0) or 0.0)
    nav_per_unit = (equity / total_units) if total_units > 0 else 1.0
    current_value = units * nav_per_unit
    ownership = (units / total_units) if total_units > 0 else 0.0
    return {
        "firm": status.get("firm"),
        "mode": status.get("mode"),
        "ts": status.get("ts"),
        "cycle": status.get("cycle"),
        "disclaimer": "Paper-trading simulation — illustrative only, not investment "
                      "advice, and not an offer or solicitation. No real money is at risk.",
        "investor": {
            "name": investor.get("name"),
            "kind": investor.get("kind"),
            "units": round(units, 4),
            "ownership_pct": round(ownership * 100, 3),
            "contributed": round(contributed, 2),
            "nav_per_unit": round(nav_per_unit, 4),
            "current_value": round(current_value, 2),
            "unrealized_pnl": round(current_value - contributed, 2),
            "return_pct": round((current_value / contributed - 1.0) * 100, 3) if contributed > 0 else 0.0,
        },
        "fund": {
            "equity": round(equity, 2),
            "total_return_pct": status.get("pnl", {}).get("total_return_pct", 0.0),
            "aum": status.get("crm", {}).get("aum", 0.0),
            "investors": status.get("crm", {}).get("investors", 0),
        },
        "equity_curve": status.get("equity_curve", []),
    }


def write_investor_views(db, status: Dict[str, Any], out_dir: str = None) -> int:
    """Write a token-keyed snapshot for every investor with a share link. Returns
    the count written. Each file is the capability target of /investor?t=<token>."""
    if out_dir is None:
        from paths import investors_dir
        out_dir = investors_dir()
    shared = db.shared_investors()
    if not shared:
        return 0
    total_units = float(db.fund_summary().get("units", 0.0) or 0.0)
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for inv in shared:
        token = (inv.get("share_token") or "").strip()
        if not token:
            continue
        view = build_investor_view(status, inv, total_units)
        write_status(view, os.path.join(out_dir, token + ".json"))  # reuse atomic writer
        written += 1
    return written


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
    ]
    cb = status["health"].get("circuit_breaker", {})
    if cb.get("halted"):
        lines.append(f" ⛔ NEW RISK HALTED — {cb.get('reason', '')}")
    lines += ["─" * 64, " Council:"]
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
