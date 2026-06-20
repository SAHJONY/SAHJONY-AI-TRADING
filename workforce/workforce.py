"""The SAHJONY CAPITAL LLC agentic workforce.

The firm's org chart, as code. Each role is a focused agent; the Firm wires them
into one trading cycle:

  Research Desk   → builds a market snapshot per ticker and convenes the 12-agent
                    Intelligence Council (intelligence/agents.py).
  Chief Strategist→ the AI Brain (Claude) with OpenAI + Grok counsellors — an
                    advisory overlay that nudges conviction and risk posture.
  Portfolio Mgr   → assigns each ticker a strategy and computes effective
                    conviction + a risk-scaled capital budget.
  Strategy Desks  → Wheel Options Desk + Equity Ladder Desk emit order intents.
  Risk Officer    → the gatekeeper; approves/denies every risk-adding intent.
  Execution Trader→ routes intents to the broker (paper) or the sim, applies fills
                    to persistent state.
  Treasurer       → writes trades, snapshots, equity curve, and council log to the
                    native SQLite database; keeps investor accounting (CRM).
  Reporter        → emits the owner dashboard snapshot (public/status.json) and a
                    console health board.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from config import Config
from database import Database
from intelligence.agents import Council, CouncilVerdict, MarketSnapshot
from intelligence.ai_brain import AIBrain, BrainVerdict
from risk.risk_engine import RiskEngine
from strategies.base import OrderIntent
from strategies.trailing_ladder import TrailingLadder
from strategies.wheel_strategy import WheelStrategy
from utils.logger import get_logger
from utils.notify import Notifier
from utils.state_store import record_event

log = get_logger("workforce")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_PATH = os.path.join(_ROOT, "public", "status.json")


# ── roles ─────────────────────────────────────────────────────────────────────
class ResearchDesk:
    def __init__(self, client, council: Council):
        self.client = client
        self.council = council

    def research(self, symbol: str, bench_closes) -> (MarketSnapshot, CouncilVerdict):
        hist = self.client.get_history(symbol, 250)
        price = self.client.get_price(symbol)
        snap = MarketSnapshot(symbol, price, hist["closes"], hist["volumes"], bench_closes)
        return snap, self.council.deliberate(snap)


class PortfolioManager:
    """Assigns strategy and computes effective conviction + capital budget."""
    def __init__(self, cfg: Config, risk: RiskEngine):
        self.cfg = cfg
        self.risk = risk

    def assign_strategy(self, symbol: str, idx: int) -> str:
        # deterministic split: even index → wheel, odd → ladder
        return "wheel" if idx % 2 == 0 else "ladder"

    def effective(self, council: CouncilVerdict, brain: BrainVerdict, equity: float):
        conviction = max(0.0, min(1.0, council.conviction + brain.adjust_for(council.symbol)))
        risk_mult = max(0.1, min(1.2, council.risk_multiplier * brain.global_risk_multiplier))
        budget = self.risk.position_budget(equity, conviction, risk_mult)
        return conviction, risk_mult, budget


class ExecutionTrader:
    """Risk-gates and executes order intents, applying fills to persistent state."""
    def __init__(self, client, risk: RiskEngine, db: Database, cfg: Config):
        self.client = client
        self.risk = risk
        self.db = db
        self.cfg = cfg

    def _apply(self, intent: OrderIntent, state: Dict[str, Any]) -> None:
        positions = state.setdefault("positions", {})
        if intent.clear_position:
            positions.pop(intent.symbol, None)
        elif intent.set_position is not None:
            positions[intent.symbol] = intent.set_position
        elif intent.merge_position is not None:
            pos = positions.get(intent.symbol, {})
            pos.update(intent.merge_position)
            positions[intent.symbol] = pos
        state["premium_collected"] = state.get("premium_collected", 0.0) + intent.premium_delta
        state["realized_pnl"] = state.get("realized_pnl", 0.0) + intent.realized_delta

    def execute(self, intents: List[OrderIntent], state: Dict[str, Any], cycle: int,
                equity: float, deployed: float, conviction: float) -> tuple[List[Dict], float]:
        """Returns (executed, deployed) — the running deployed value is threaded back
        so the total-deployed cap accounts for positions opened earlier this cycle."""
        done = []
        for intent in intents:
            try:
                if intent.kind == "state":
                    self._apply(intent, state)
                    record_event(state, intent.purpose, {"symbol": intent.symbol, "reason": intent.reason})
                    continue
                if intent.risk_check:
                    dec = self.risk.approve(equity, deployed, intent.est_notional, conviction, intent.symbol)
                    if not dec.approved:
                        log.info("RISK BLOCK %s %s: %s", intent.symbol, intent.purpose, dec.reason)
                        record_event(state, "risk_block",
                                     {"symbol": intent.symbol, "purpose": intent.purpose, "reason": dec.reason})
                        continue
                if intent.kind == "equity":
                    res = self.client.submit_equity_order(intent.symbol, intent.qty, intent.side)
                    price = res.get("fill_price", self.client.get_price(intent.symbol))
                else:
                    res = self.client.submit_option_order(intent.contract, intent.qty, intent.side, intent.premium)
                    price = intent.premium
                if res.get("status") not in ("filled", "submitted"):
                    log.warning("order not filled %s: %s", intent.symbol, res)
                    continue
                self._apply(intent, state)
                if intent.side in ("buy",):
                    deployed += intent.est_notional
                self.db.log_trade({
                    "cycle": cycle, "symbol": intent.symbol, "strategy": intent.strategy,
                    "kind": intent.kind, "side": intent.side, "qty": intent.qty,
                    "price": price, "premium": intent.premium, "notional": intent.est_notional,
                    "purpose": intent.purpose, "reason": intent.reason, "mode": self.cfg.mode,
                    "simulated": res.get("simulated", True),
                })
                record_event(state, intent.purpose, {"symbol": intent.symbol, "reason": intent.reason})
                done.append({"symbol": intent.symbol, "purpose": intent.purpose, "reason": intent.reason})
                log.info("EXEC %s %s — %s", intent.symbol, intent.purpose, intent.reason)
            except Exception as exc:  # one bad intent never sinks the cycle
                log.error("execute intent failed (%s %s): %s", intent.symbol, intent.purpose, exc)
        return done, deployed


# ── the firm ────────────────────────────────────────────────────────────────
class Firm:
    def __init__(self, cfg: Config, client, db: Database):
        self.cfg = cfg
        self.client = client
        self.db = db
        self.council = Council()
        self.brain = AIBrain(cfg)
        self.notifier = Notifier(cfg)
        self.risk = RiskEngine(cfg)
        self.research = ResearchDesk(client, self.council)
        self.pm = PortfolioManager(cfg, self.risk)
        self.execution = ExecutionTrader(client, self.risk, db, cfg)
        self.wheel = WheelStrategy(cfg)
        self.ladder = TrailingLadder(cfg)

    def _position_value(self, state: Dict[str, Any]) -> float:
        total = 0.0
        for sym, pos in state.get("positions", {}).items():
            shares = pos.get("shares", 0) or 0
            if shares:
                total += shares * self.client.get_price(sym)
        return total

    def run_cycle(self, state: Dict[str, Any], trade: bool = True) -> Dict[str, Any]:
        state["cycle"] = state.get("cycle", 0) + 1
        cycle = state["cycle"]
        state["mode"] = self.cfg.mode
        acct = self.client.get_account()
        equity = acct["equity"]
        if state.get("equity_start") is None:
            state["equity_start"] = equity
        state["equity_last"] = equity

        bench = self.client.get_history(self.cfg.benchmark, 250)["closes"]

        # 1) Research Desk — council per ticker
        research: List[Dict[str, Any]] = []
        for sym in self.cfg.tickers:
            try:
                snap, verdict = self.research.research(sym, bench)
                research.append({"symbol": sym, "snap": snap, "verdict": verdict})
            except Exception as exc:
                log.error("research failed %s: %s", sym, exc)

        # 2) Chief Strategist — AI brain advisory overlay
        portfolio = [{
            "symbol": r["symbol"], "price": round(r["snap"].price, 2),
            "conviction": round(r["verdict"].conviction, 3), "direction": r["verdict"].direction,
            "composite": round(r["verdict"].composite_score, 3),
            "alpha": round(r["verdict"].metrics.get("alpha", 0.0), 4),
            "beta": round(r["verdict"].metrics.get("beta", 1.0), 3),
            "vol": round(r["verdict"].metrics.get("vol", 0.0), 3),
        } for r in research]
        brain = self.brain.advise(portfolio)
        if brain.used:
            log.info("AI BRAIN posture=%s risk_mult=%.2f — %s",
                     brain.posture, brain.global_risk_multiplier, brain.commentary[:120])

        # 3-6) PM → Strategy → Risk → Execution → Treasurer, per ticker
        deployed = self._position_value(state)
        executed: List[Dict] = []
        for idx, r in enumerate(research):
            sym, snap, verdict = r["symbol"], r["snap"], r["verdict"]
            try:
                strat = self.pm.assign_strategy(sym, idx)
                conviction, risk_mult, budget = self.pm.effective(verdict, brain, equity)
                pos = state.get("positions", {}).get(sym)
                if strat == "wheel":
                    chain = self.client.get_option_chain(sym, snap.price, self.cfg.wheel_dte_min,
                                                         self.cfg.wheel_dte_max, snap.vol)
                    intents = self.wheel.decide(sym, snap, pos, verdict, budget, chain)
                else:
                    intents = self.ladder.decide(sym, snap, pos, verdict, budget)
                if trade:
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conviction)
                    executed += done
                # log council + snapshot
                self.db.log_council(cycle, sym, verdict.conviction, verdict.direction,
                                    verdict.composite_score, verdict.risk_multiplier, verdict.metrics)
                npos = state.get("positions", {}).get(sym, {})
                shares = npos.get("shares", 0) or 0
                self.db.log_snapshot(cycle, sym, strat, npos.get("stage") or npos.get("strategy") or "flat",
                                     shares, npos.get("cost_basis", 0.0), snap.price,
                                     shares * snap.price, 0.0)
            except Exception as exc:
                log.error("cycle step failed %s: %s", sym, exc)

        # 7) Treasurer — equity curve
        acct = self.client.get_account()
        self.db.log_equity(cycle, acct["equity"], acct["cash"], self._position_value(state),
                           state.get("realized_pnl", 0.0), state.get("premium_collected", 0.0), self.cfg.mode)

        return {"cycle": cycle, "equity": acct["equity"], "cash": acct["cash"],
                "research": research, "brain": brain, "executed": executed,
                "deployed": self._position_value(state)}
