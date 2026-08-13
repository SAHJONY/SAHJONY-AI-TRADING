#!/usr/bin/env python3
"""Project the authoritative Python engine snapshot into Parquet's public contract.

This adapter never submits orders. Execution remains owned by run_brain.py and its
existing broker, reconciliation, and risk gates.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[2]
SHORT = {
    "Citadel Systematic": "CTS", "Two Sigma Backtest": "2SIG", "Bridgewater Risk": "BWR",
    "Renaissance Patterns": "REN", "Goldman Technical": "GS", "JPMorgan Fundamental": "JPM",
    "D.E. Shaw Options": "DES", "AQR Factor": "AQR", "Citadel Securities MM": "CMM",
    "Millennium Pod": "MLN", "Renaissance Medallion": "MED", "Sovereign Wealth": "SWF",
}


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def source_for(desk: str) -> Path:
    if desk in {"live", "crypto"}:
        candidates = [ROOT / "public/status.json", ROOT / "desks/robinhood/public/status.json"]
        readable = [path for path in candidates if path.exists()]
        if readable:
            # Runtime publishers may update either location. Prefer the highest
            # completed engine cycle so the UI never regresses to a stale snapshot.
            return max(readable, key=lambda path: int(json.loads(path.read_text()).get("cycle", 0)))
    return ROOT / "public/status.json"


def sharpe(values: list[float]) -> float:
    returns = [(b / a) - 1 for a, b in zip(values, values[1:]) if a > 0]
    if len(returns) < 2 or pstdev(returns) == 0:
        return 0.0
    return mean(returns) / pstdev(returns) * math.sqrt(252)


def log_signals(raw: dict, db_path: Path) -> dict[str, dict]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("""CREATE TABLE IF NOT EXISTS agent_attribution (
      cycle INTEGER NOT NULL, ts TEXT NOT NULL, symbol TEXT NOT NULL, agent TEXT NOT NULL,
      score REAL NOT NULL, confidence REAL NOT NULL, rationale TEXT NOT NULL,
      realized_alpha REAL, outcome TEXT, PRIMARY KEY(cycle, symbol, agent))""")
    db.execute("""CREATE TABLE IF NOT EXISTS agent_trade_links (
      trade_id TEXT NOT NULL, cycle INTEGER NOT NULL, symbol TEXT NOT NULL, agent TEXT NOT NULL,
      signal_score REAL NOT NULL, confidence REAL NOT NULL, contribution_weight REAL NOT NULL,
      realized_alpha REAL, outcome TEXT, PRIMARY KEY(trade_id, agent))""")
    for asset in raw.get("council", []):
        for agent in asset.get("agents", []):
            db.execute("""INSERT OR IGNORE INTO agent_attribution
              (cycle,ts,symbol,agent,score,confidence,rationale) VALUES(?,?,?,?,?,?,?)""",
              (raw.get("cycle", 0), raw.get("ts", ""), asset.get("symbol", ""),
               agent.get("name", "unknown"), number(agent.get("score")),
               number(agent.get("confidence")), agent.get("rationale", "")))
    current_assets = {asset.get("symbol"): asset for asset in raw.get("council", [])}
    for trade in raw.get("recent_trades", []):
        if int(trade.get("cycle", -1)) != int(raw.get("cycle", 0)):
            continue
        aligned = [a for a in current_assets.get(trade.get("symbol"), {}).get("agents", [])
                   if abs(number(a.get("score"))) >= .12 and number(a.get("confidence")) >= .5
                   and ((trade.get("side") == "buy" and number(a.get("score")) > 0)
                        or (trade.get("side") == "sell" and number(a.get("score")) < 0))]
        total = sum(abs(number(a.get("score"))) * number(a.get("confidence")) for a in aligned) or 1
        for agent in aligned:
            weight = abs(number(agent.get("score"))) * number(agent.get("confidence")) / total
            db.execute("""INSERT OR IGNORE INTO agent_trade_links
              (trade_id,cycle,symbol,agent,signal_score,confidence,contribution_weight)
              VALUES(?,?,?,?,?,?,?)""", (str(trade.get("id")), raw.get("cycle", 0), trade.get("symbol", ""),
              agent.get("name", "unknown"), number(agent.get("score")), number(agent.get("confidence")), weight))
    db.commit()
    rows = db.execute("""SELECT agent, COALESCE(SUM(realized_alpha),0),
      SUM(CASE WHEN outcome='profit' THEN 1 ELSE 0 END),
      SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END)
      FROM agent_trade_links GROUP BY agent""").fetchall()
    driver_rows = db.execute("SELECT trade_id,agent FROM agent_trade_links ORDER BY contribution_weight DESC").fetchall()
    db.close()
    result = {r[0]: {"alpha": r[1], "wins": r[2], "losses": r[3]} for r in rows}
    result["__drivers__"] = {}
    for trade_id, agent in driver_rows:
        result["__drivers__"].setdefault(str(trade_id), []).append(agent)
    return result


def project(raw: dict, desk: str, attribution: dict[str, dict]) -> dict:
    account = raw.get("account", {})
    health = raw.get("health", {})
    brain = raw.get("brain", {})
    hermes = health.get("hermes", {})
    scorecard = hermes.get("scorecard", {})
    reconciliation = raw.get("reconciliation", {})
    benchmark = raw.get("benchmark", {})
    perf = raw.get("global_performance", {})
    equity = number(account.get("equity"))
    start = number(account.get("equity_start"), equity or 1)
    return_pct = number(raw.get("pnl", {}).get("total_return_pct"))
    benchmark_pct = number(benchmark.get("return_pct"))
    curves = raw.get("equity_curve", [])[-120:]
    equity_values = [number(p.get("equity")) for p in curves if number(p.get("equity")) > 0]
    actual_sharpe = number(perf.get("sharpe"), sharpe(equity_values))
    expected_sharpe = 1.0
    integrity_raw = number(hermes.get("data_ok_pct"), 1.0)
    integrity = round(max(0, min(100, integrity_raw * 100 if integrity_raw <= 1 else integrity_raw)))
    halted = bool(health.get("circuit_breaker", {}).get("halted")) or integrity < 80
    halt_reason = health.get("circuit_breaker", {}).get("reason", "")
    if integrity < 80:
        halt_reason = f"Hermes data integrity {integrity}% is below the 80% execution floor"

    names = []
    for asset in raw.get("council", []):
        for agent in asset.get("agents", []):
            if agent.get("name") not in names:
                names.append(agent.get("name"))
    agents_summary = []
    for name in names[:12]:
        observed = [a for asset in raw.get("council", []) for a in asset.get("agents", []) if a.get("name") == name]
        stats = attribution.get(name, {})
        agents_summary.append({
            "name": name, "shortName": SHORT.get(name, name[:3].upper()),
            "focus": observed[0].get("persona", "quantitative") if observed else "quantitative",
            "score": mean([number(a.get("score")) for a in observed]) if observed else 0,
            "confidence": mean([number(a.get("confidence")) for a in observed]) if observed else 0,
            "rationale": observed[0].get("rationale", "") if observed else "",
            "alphaContribution": number(stats.get("alpha")), "profitable": int(stats.get("wins", 0)),
            "losing": int(stats.get("losses", 0)),
        })
    by_name = {a["name"]: a for a in agents_summary}
    council = []
    for asset in raw.get("council", []):
        scores = []
        for a in asset.get("agents", [])[:12]:
            base = by_name.get(a.get("name"), {})
            scores.append({**base, "score": number(a.get("score")), "confidence": number(a.get("confidence")),
                           "rationale": a.get("rationale", "")})
        council.append({"symbol": asset.get("symbol", ""), "price": number(asset.get("price")),
                        "conviction": number(asset.get("conviction")), "direction": asset.get("direction", "flat"),
                        "agents": scores})
    nav_start = next((number(p.get("equity")) for p in curves if number(p.get("equity")) > 0), start or 1)
    equity_curve = [{"cycle": int(p.get("cycle", 0)), "nav": number(p.get("equity")) / nav_start * 100,
                     "benchmark": 100 + benchmark_pct, "expected": 100 + max(0, i - 1) * 0.01}
                    for i, p in enumerate(curves) if number(p.get("equity")) > 0]
    deployed = number(account.get("deployed"))
    allocation = [{"name": "Cash", "value": number(account.get("cash")), "color": "#59616a"}]
    for p in raw.get("positions", []):
        allocation.append({"name": p.get("symbol", "").replace("/USD", ""),
                           "value": number(p.get("market_value")), "color": "#00ff88"})
    positive_cycles = int(scorecard.get("cycles", 0)) if number(scorecard.get("sharpe")) > 0 else 0
    return {
        "schemaVersion": 1, "desk": desk, "cycle": int(raw.get("cycle", 0)),
        "ts": raw.get("ts") or datetime.now(timezone.utc).isoformat(), "mode": raw.get("mode", "UNKNOWN"),
        "broker": raw.get("broker", "unknown"),
        "account": {"equity": equity, "equityStart": start, "cash": number(account.get("cash")),
                    "deployed": deployed, "nav": (equity / start * 100) if start else 100},
        "pnl": {"returnPct": return_pct, "realized": number(raw.get("pnl", {}).get("realized")),
                "benchmarkPct": benchmark_pct, "alphaPct": number(benchmark.get("alpha_pct"), return_pct - benchmark_pct)},
        "health": {"marketOpen": bool(health.get("market_open")), "brokerOnline": bool(health.get("broker_online")),
                   "liveArmed": bool(health.get("live_armed")), "halted": halted, "haltReason": halt_reason,
                   "dataIntegrity": integrity, "reconciliation": "RECONCILED" if reconciliation.get("ok") else "MISMATCH"},
        "brain": {"posture": brain.get("posture", "neutral"),
                  "globalRiskMultiplier": number(brain.get("global_risk_multiplier")),
                  "commentary": brain.get("commentary", "No strategist commentary available."),
                  "model": brain.get("brain_model", "deterministic fallback"), "used": bool(brain.get("used"))},
        "council": council, "positions": [{"symbol": p.get("symbol", ""), "strategy": p.get("strategy", ""),
          "shares": number(p.get("shares")), "price": number(p.get("price")), "marketValue": number(p.get("market_value")),
          "unrealized": number(p.get("unrealized"))} for p in raw.get("positions", [])],
        "blotter": [{"ts": t.get("ts", ""), "symbol": t.get("symbol", ""), "side": t.get("side", ""),
          "purpose": t.get("purpose", ""), "status": t.get("order_status") or ("recorded" if t.get("simulated") == 0 else "simulated"),
          "notional": number(t.get("notional")), "agentDrivers": attribution.get("__drivers__", {}).get(str(t.get("id")), [])}
          for t in raw.get("recent_trades", [])],
        "equityCurve": equity_curve, "allocation": allocation, "attribution": agents_summary,
        "drift": {"actualSharpe": actual_sharpe, "expectedSharpe": expected_sharpe,
                  "deviation": actual_sharpe - expected_sharpe, "alert": abs(actual_sharpe - expected_sharpe) > .75,
                  "observations": int(perf.get("return_observations", len(equity_values)))},
        "incubation": {"active": positive_cycles < 100, "deployedCapital": deployed,
                       "capitalCeiling": 100, "positiveSharpeCycles": positive_cycles,
                       "requiredCycles": 100, "scaleEligible": positive_cycles >= 100},
        "traces": {"dataIntegrity": {"value": integrity, "source": "health.hermes.data_ok_pct",
          "rationale": "Percentage of symbols passing Hermes freshness and integrity checks.", "asOf": raw.get("ts", "")}},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--desk", choices=("live", "crypto", "trainer", "stocks"), default="live")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()
    raw = json.loads(source_for(args.desk).read_text())
    stats = {} if args.no_log else log_signals(raw, ROOT / "data/parquet_attribution.db")
    print(json.dumps(project(raw, args.desk, stats), separators=(",", ":")))


if __name__ == "__main__":
    main()
