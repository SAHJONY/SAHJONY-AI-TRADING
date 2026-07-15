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
from execution.idempotency import execution_intent_id
from intelligence.agents import Council, CouncilVerdict, MarketSnapshot
from intelligence.advisors import AdvisoryBoard
from intelligence.ai_brain import AIBrain, BrainVerdict
from intelligence.alt_data import AltData
from intelligence.autonomous_learning import AutonomousLearningPipeline
from intelligence.hermes import Hermes, HermesReport
from intelligence.institutional_research import (
    PROMOTION_KEY,
    InstitutionalResearchFabric,
    applied_multiplier,
    multiplier_enabled,
)
from risk.risk_engine import RiskEngine
from strategies.base import OrderIntent
from strategies.copy_trading import CopyTrader
from strategies.credit_spreads import CreditSpreads
from strategies.day_trading import DayTrading
from strategies.pairs_trading import PairsDesk
from strategies.trailing_ladder import TrailingLadder
from strategies.wheel_strategy import WheelStrategy
from utils.logger import get_logger
from utils.notify import Notifier
from utils.state_store import record_event

log = get_logger("workforce")


# ── roles ─────────────────────────────────────────────────────────────────────
class ResearchDesk:
    def __init__(self, client, council: Council):
        self.client = client
        self.council = council

    def research(self, symbol: str, bench_closes) -> (MarketSnapshot, CouncilVerdict):
        hist = self.client.get_history(symbol, 250)
        price = self.client.get_price(symbol)
        snap = MarketSnapshot(
            symbol, price, hist["closes"], hist["volumes"], bench_closes,
            bar_timestamps=hist.get("timestamps", []),
            retrieved_at=hist.get("retrieved_at"),
            feed_timestamp=hist.get("feed_timestamp"),
            exchange_timestamp=hist.get("exchange_timestamp"),
        )
        return snap, self.council.deliberate(snap)


class PortfolioManager:
    """Assigns strategy and computes effective conviction + capital budget."""
    def __init__(self, cfg: Config, risk: RiskEngine):
        self.cfg = cfg
        self.risk = risk

    def assign_strategy(self, symbol: str, idx: int) -> str:
        # crypto has no options on Alpaca → always the equity-style ladder.
        # equities rotate deterministically across the three desks; with the
        # credit-spread desk disabled it falls back to the classic wheel/ladder split.
        if "/" in symbol:
            return "ladder"
        if getattr(self.cfg, "credit_spreads_enabled", True):
            return ("wheel", "ladder", "spread")[idx % 3]
        return "wheel" if idx % 2 == 0 else "ladder"

    def effective(self, council: CouncilVerdict, brain: BrainVerdict, equity: float,
                  alt_tilt: float = 0.0):
        # Council conviction, nudged by the AI brain and the alt-data overlay (both
        # clamped small upstream so they can only tilt, never hijack, the quant signal).
        conviction = max(0.0, min(1.0, council.conviction + brain.adjust_for(council.symbol) + alt_tilt))
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
        # Attribute every realized outcome to its strategy so Hermes can learn which
        # desks actually win and re-weight capital toward them (bounded, perpetual).
        if intent.realized_delta:
            events = state.setdefault("hermes_events", [])
            events.append({"strategy": intent.strategy or "?",
                           "realized": float(intent.realized_delta)})
            if len(events) > 400:
                del events[:len(events) - 400]

    def execute(self, intents: List[OrderIntent], state: Dict[str, Any], cycle: int,
                equity: float, deployed: float, conviction: float,
                allow_new_risk: bool = True) -> tuple[List[Dict], float]:
        """Returns (executed, deployed) — the running deployed value is threaded back
        so the total-deployed cap accounts for positions opened earlier this cycle.

        When allow_new_risk is False (circuit breaker / kill switch), risk-ADDING
        intents are blocked but exits and state updates still flow, so the desk can
        always reduce exposure."""
        done = []
        for intent in intents:
            intent_id = ""
            try:
                if intent.kind == "state":
                    self._apply(intent, state)
                    record_event(state, intent.purpose, {"symbol": intent.symbol, "reason": intent.reason})
                    continue
                if intent.risk_check and not allow_new_risk:
                    log.info("HALT BLOCK %s %s — new risk suspended", intent.symbol, intent.purpose)
                    record_event(state, "halt_block",
                                 {"symbol": intent.symbol, "purpose": intent.purpose})
                    self.db.append_audit("risk_block", {"cycle": cycle, "symbol": intent.symbol,
                                         "purpose": intent.purpose, "reason": "new risk suspended"})
                    continue
                if intent.risk_check:
                    dec = self.risk.approve(equity, deployed, intent.est_notional, conviction, intent.symbol)
                    if not dec.approved:
                        log.info("RISK BLOCK %s %s: %s", intent.symbol, intent.purpose, dec.reason)
                        record_event(state, "risk_block",
                                     {"symbol": intent.symbol, "purpose": intent.purpose, "reason": dec.reason})
                        self.db.append_audit("risk_block", {"cycle": cycle, "symbol": intent.symbol,
                                             "purpose": intent.purpose, "reason": dec.reason})
                        continue
                intent_id, payload = execution_intent_id(intent, cycle)
                if not self.db.reserve_execution_intent(intent_id, cycle, payload):
                    log.error("DUPLICATE INTENT BLOCKED %s %s id=%s",
                              intent.symbol, intent.purpose, intent_id[:12])
                    record_event(state, "duplicate_intent_block",
                                 {"symbol": intent.symbol, "purpose": intent.purpose,
                                  "intent_id": intent_id})
                    self.db.append_audit("duplicate_intent_block", {
                        "cycle": cycle, "symbol": intent.symbol,
                        "purpose": intent.purpose, "intent_id": intent_id,
                    })
                    continue
                self.db.append_audit("execution_reserved", {
                    "cycle": cycle, "intent_id": intent_id, "payload": payload,
                })
                if intent.kind == "equity":
                    res = self.client.submit_equity_order(intent.symbol, intent.qty, intent.side)
                    price = res.get("fill_price", self.client.get_price(intent.symbol))
                else:
                    res = self.client.submit_option_order(intent.contract, intent.qty, intent.side, intent.premium)
                    price = intent.premium
                if res.get("status") not in ("filled", "submitted"):
                    self.db.update_execution_intent(intent_id, "failed",
                                                    detail={"status": str(res.get("status", "rejected"))})
                    self.db.append_audit("execution_failed", {
                        "cycle": cycle, "intent_id": intent_id,
                        "status": str(res.get("status", "rejected")),
                    })
                    log.warning("order not filled %s: %s", intent.symbol, res)
                    continue
                self._apply(intent, state)
                transaction_cost = max(0.0, float(res.get("transaction_cost", 0.0) or 0.0))
                state["transaction_costs"] = state.get("transaction_costs", 0.0) + transaction_cost
                state["realized_pnl"] = state.get("realized_pnl", 0.0) - transaction_cost
                # Consume deployed budget for: equity buys, risk-gated equity shorts,
                # and cash-secured puts (sell_to_open carries collateral in
                # est_notional; covered calls are sell_to_open with est_notional 0,
                # so they correctly add nothing). Keeps stacked CSPs within the cap
                # within a single cycle, before _gross_exposure re-seeds next cycle.
                if (intent.side == "buy"
                        or (intent.risk_check and intent.side == "sell" and intent.kind == "equity")
                        or intent.side == "sell_to_open"):
                    deployed += intent.est_notional
                self.db.log_trade({
                    "cycle": cycle, "symbol": intent.symbol, "strategy": intent.strategy,
                    "kind": intent.kind, "side": intent.side, "qty": intent.qty,
                    "price": price, "premium": intent.premium, "notional": intent.est_notional,
                    "purpose": intent.purpose, "reason": intent.reason,
                    "mode": getattr(self.client, "mode", self.cfg.mode),
                    "simulated": res.get("simulated", True),
                })
                execution_status = "filled" if res.get("status") == "filled" else "submitted"
                broker_ref = str(res.get("order_id") or res.get("id") or "")
                self.db.update_execution_intent(
                    intent_id, execution_status, broker_ref=broker_ref,
                    detail={"transaction_cost": transaction_cost},
                )
                self.db.append_audit("execution_result", {
                    "cycle": cycle, "intent_id": intent_id, "status": execution_status,
                    "broker_ref": broker_ref, "transaction_cost": transaction_cost,
                })
                record_event(state, intent.purpose, {"symbol": intent.symbol, "reason": intent.reason})
                done.append({"symbol": intent.symbol, "purpose": intent.purpose, "reason": intent.reason})
                log.info("EXEC %s %s — %s", intent.symbol, intent.purpose, intent.reason)
            except Exception as exc:  # one bad intent never sinks the cycle
                if intent_id:
                    try:
                        self.db.update_execution_intent(
                            intent_id, "failed", detail={"error": type(exc).__name__}
                        )
                        self.db.append_audit("execution_exception", {
                            "cycle": cycle, "intent_id": intent_id,
                            "error": type(exc).__name__,
                        })
                    except Exception:
                        pass
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
        self.alt = AltData(cfg)   # QuiverQuant insider/congress alt-data overlay
        self.hermes = Hermes(cfg) # background guardian: data integrity + scores + self-calibration
        self.board = AdvisoryBoard(cfg)  # Buffett/Munger/Macro/Growth/Quant council + risk gate
        self.notifier = Notifier(cfg)
        self.risk = RiskEngine(cfg)
        self.research = ResearchDesk(client, self.council)
        self.pm = PortfolioManager(cfg, self.risk)
        self.execution = ExecutionTrader(client, self.risk, db, cfg)
        self.wheel = WheelStrategy(cfg)
        self.ladder = TrailingLadder(cfg)
        self.spread = CreditSpreads(cfg)
        self.copy = CopyTrader(cfg)
        self.dayts = DayTrading(cfg)
        self.pairs_desk = PairsDesk(cfg)

    def _position_value(self, state: Dict[str, Any]) -> float:
        """SIGNED market value (shorts negative) — correct for equity/P&L math."""
        total = 0.0
        for sym, pos in state.get("positions", {}).items():
            shares = pos.get("shares", 0) or 0
            if shares:
                total += shares * self.client.get_price(sym)
        return total

    def _gross_exposure(self, state: Dict[str, Any]) -> float:
        """GROSS exposure (|shares|·price) — what the deployed-capital cap gates on.
        A short is risk too; it must consume the same risk budget as a long.
        Includes cash-secured-put collateral (0-share short_put legs) — see below."""
        total = 0.0
        for sym, pos in state.get("positions", {}).items():
            shares = pos.get("shares", 0) or 0
            if shares:
                total += abs(shares) * self.client.get_price(sym)
        return total + self._csp_collateral(state)

    def _csp_collateral(self, state: Dict[str, Any]) -> float:
        """Capital committed by open cash-secured puts (stage 'short_put'). A CSP
        holds 0 shares, so _gross_exposure's share loop can't see it — but its
        strike×100×contracts collateral is real committed capital and must count
        against the total-deployed cap, or stacked CSPs quietly breach it."""
        total = 0.0
        for pos in state.get("positions", {}).values():
            if pos.get("stage") == "short_put":
                total += float(pos.get("strike", 0.0)) * 100 * int(pos.get("contracts", 1))
        return total

    def _position_cost(self, state: Dict[str, Any]) -> float:
        return sum((p.get("shares", 0) or 0) * p.get("cost_basis", 0.0)
                   for p in state.get("positions", {}).values())

    def _sleeve(self, state: Dict[str, Any]):
        """Virtual capital sleeve → (equity, cash) measured against cfg.trading_capital,
        so the desk behaves like a small account even on a large broker balance.
        equity = capital + realized + unrealized; cash = capital + realized − cost."""
        cap = self.cfg.trading_capital
        realized = state.get("realized_pnl", 0.0) + state.get("premium_collected", 0.0)
        cost = self._position_cost(state)
        return cap + realized + (self._position_value(state) - cost), cap + realized - cost

    def _kill_switch(self) -> bool:
        """Owner kill switch: TRADING_HALT env or a HALT file in the desk home."""
        from paths import halt_path
        return self.cfg.trading_halt or os.path.exists(halt_path())

    def _halt_check(self, state: Dict[str, Any], equity: float) -> Dict[str, Any]:
        """Decide whether NEW risk is suspended this cycle. Tracks the day's opening
        equity and latches a daily-drawdown halt for the rest of the calendar day so
        a small intraday bounce can't un-trip the breaker."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state.get("equity_day") != today:
            state["equity_day"] = today
            state["equity_day_start"] = equity
            state["breaker_latched"] = False
        day_start = float(state.get("equity_day_start") or 0.0)

        # Zero equity means the connected account is unfunded, not down 100%.
        # Block new risk through buying-power/account routing checks instead.
        if equity <= 0.0 or day_start <= 0.0:
            day_return = 0.0
            state["equity_day_start"] = equity
            state["breaker_latched"] = False
        else:
            day_return = equity / day_start - 1.0
            if day_return <= -abs(self.cfg.max_daily_drawdown_pct):
                state["breaker_latched"] = True

        if self._kill_switch():
            reason = "kill switch (TRADING_HALT / HALT file)"
        elif state.get("breaker_latched"):
            reason = (f"daily circuit breaker — down {day_return:.1%} "
                      f"(limit {self.cfg.max_daily_drawdown_pct:.0%})")
        else:
            reason = ""
        halted = bool(reason)
        if halted:
            log.warning("NEW RISK HALTED: %s", reason)
        return {"halted": halted, "reason": reason, "day_return": round(day_return, 4),
                "day_start": round(day_start, 2), "limit_pct": self.cfg.max_daily_drawdown_pct}

    def run_cycle(self, state: Dict[str, Any], trade: bool = True) -> Dict[str, Any]:
        state["cycle"] = state.get("cycle", 0) + 1
        cycle = state["cycle"]
        mode = getattr(self.client, "mode", self.cfg.mode)   # broker-accurate
        state["mode"] = mode
        acct = self.client.get_account()
        if self.cfg.trading_capital and self.cfg.trading_capital > 0:
            # Re-anchor the baseline the first time a cap is applied or changed
            # (e.g. switching a $100k desk to a $500 sleeve).
            if state.get("sleeve_capital") != self.cfg.trading_capital:
                state["sleeve_capital"] = self.cfg.trading_capital
                state["equity_start"] = self.cfg.trading_capital
                state["positions"] = {}               # start the sleeve FLAT (drop prior-size positions)
                state["realized_pnl"] = 0.0
                state["premium_collected"] = 0.0
                state["transaction_costs"] = 0.0
                state.pop("benchmark_start", None)    # re-anchor SPY alpha to the sleeve start
                state.pop("equity_day_start", None)
                log.info("Capital sleeve set to $%.0f — baseline + positions reset for a clean test.",
                         self.cfg.trading_capital)
            equity, _ = self._sleeve(state)
        else:
            equity = acct["equity"]
        if state.get("equity_start") is None:
            state["equity_start"] = equity
        state["equity_last"] = equity

        # A LIVE venue must reconcile broker positions before adding any risk.
        # Mismatches fail closed while exits remain available downstream.
        from observability.reconciliation import reconcile_positions, unavailable_reconciliation
        reconciliation = unavailable_reconciliation("not required outside LIVE mode")
        if mode == "LIVE":
            try:
                reconciliation = reconcile_positions(
                    state.get("positions", {}), self.client.get_broker_positions() or {}
                )
            except Exception as exc:
                reconciliation = unavailable_reconciliation(
                    f"broker snapshot failed: {type(exc).__name__}"
                )
            try:
                self.db.append_audit("position_reconciliation", {
                    "cycle": cycle, "status": reconciliation["status"],
                    "reconciled": reconciliation["reconciled"],
                    "differences": reconciliation.get("differences", []),
                })
            except Exception as exc:
                reconciliation = unavailable_reconciliation(
                    f"audit ledger unavailable: {type(exc).__name__}"
                )

        # Circuit breaker / kill switch — suspends NEW risk this cycle if tripped.
        halt = self._halt_check(state, equity)
        allow_new_risk = trade and not halt["halted"]
        if mode == "LIVE" and not reconciliation["reconciled"]:
            allow_new_risk = False
            reason = "broker position reconciliation failed"
            halt = {**halt, "halted": True,
                    "reason": f"{halt.get('reason')}; {reason}".strip("; ")}
            log.error("NEW RISK HALTED: %s", reason)

        # Volatility targeting — realized portfolio vol above target scales every
        # new-position budget down ([0.5, 1.0]); fault-isolated, neutral on failure.
        try:
            vol_scale = self.risk.vol_scalar(
                [row.get("equity") for row in self.db.equity_history_regime(60)])
        except Exception as exc:
            log.warning("vol targeting skipped: %s", exc)
            vol_scale = 1.0

        bench = self.client.get_history(self.cfg.benchmark, 250)["closes"]

        # 1) Research Desk — council per ticker
        research: List[Dict[str, Any]] = []
        for sym in self.cfg.tickers:
            try:
                snap, verdict = self.research.research(sym, bench)
                research.append({"symbol": sym, "snap": snap, "verdict": verdict})
            except Exception as exc:
                log.error("research failed %s: %s", sym, exc)

        # Cross-asset institutional research fabric. This is point-in-time and
        # advisory-only: it enriches AI/research context and can never invent an order.
        try:
            institutional_intelligence = InstitutionalResearchFabric().analyze(
                [row["snap"] for row in research],
                requested_symbols=self.cfg.tickers,
                max_age_seconds=self.cfg.institutional_max_data_age_seconds,
                require_timestamps=True,
            )
        except Exception as exc:
            log.error("institutional research fabric failed: %s", exc)
            institutional_intelligence = InstitutionalResearchFabric().analyze([])

        # 1b) Alt-data overlay — QuiverQuant insider/congress disclosures per symbol
        # (fault-isolated; empty when disabled). Feeds the brain's view and conviction.
        try:
            alt_signals = self.alt.signals([r["symbol"] for r in research])
        except Exception as exc:
            log.error("alt-data overlay failed: %s", exc)
            alt_signals = {}

        # 1b2) Advisory Board — the six-agent Intelligence Council (Buffett/Munger/
        # Macro/Growth/Quant + Risk gate). Advisory only: a bounded tilt per symbol.
        try:
            board = self.board.evaluate(research)
        except Exception as exc:
            log.error("advisory board failed: %s", exc)
            board = {}

        # 1c) Hermes guardian — background agent validating every feed (bad feeds are
        # quarantined: no NEW risk, exits still flow) and grading the council's realized
        # accuracy into a small self-improvement tilt. Fault-isolated like everything else.
        try:
            hermes = self.hermes.review(research, state)
            if hermes.quarantined:
                log.warning("HERMES quarantined %s — new risk blocked (bad data)",
                            ", ".join(hermes.quarantined))
        except Exception as exc:
            log.error("hermes review failed: %s", exc)
            hermes = HermesReport(used=False)

        # 2) Chief Strategist — AI brain advisory overlay
        institutional_factors = institutional_intelligence.get("factors", {})
        institutional_market = institutional_intelligence.get("market", {})
        institutional_promotion_stage = "research"
        try:
            candidate = self.db.upsert_promotion_candidate(
                PROMOTION_KEY, "Institutional Research Multiplier", "risk_overlay"
            )
            institutional_promotion_stage = str(candidate.get("stage") or "research")
        except Exception as exc:
            log.warning("institutional promotion state unavailable: %s", exc)
        institutional_multiplier_active = multiplier_enabled(
            institutional_promotion_stage,
            self.cfg.institutional_multiplier_enabled,
        )
        portfolio = [{
            "symbol": r["symbol"], "price": round(r["snap"].price, 2),
            "conviction": round(r["verdict"].conviction, 3), "direction": r["verdict"].direction,
            "composite": round(r["verdict"].composite_score, 3),
            "alpha": round(r["verdict"].metrics.get("alpha", 0.0), 4),
            "beta": round(r["verdict"].metrics.get("beta", 1.0), 3),
            "vol": round(r["verdict"].metrics.get("vol", 0.0), 3),
            "market_regime": ("stressed" if r["verdict"].metrics.get("stressed_prob", 0.0) >= 0.5
                              else "normal"),
            "asset_class": ("crypto" if "/" in r["symbol"] or r["symbol"].endswith("-USD")
                            else "options" if self.pm.assign_strategy(r["symbol"], idx) in {"wheel", "spread"}
                            else "equity"),
            "alt_tilt": round(alt_signals[r["symbol"]].tilt, 3) if r["symbol"] in alt_signals else 0.0,
            "alt_note": alt_signals[r["symbol"]].summary if r["symbol"] in alt_signals else "",
            "institutional_factor_score": (institutional_factors.get(r["symbol"]) or {}).get(
                "composite_factor_score", 0.0),
            "liquidity_rank": (institutional_factors.get(r["symbol"]) or {}).get(
                "liquidity_rank", 0.0),
            "expected_shortfall_95": (institutional_factors.get(r["symbol"]) or {}).get(
                "expected_shortfall_95", 0.0),
            "cross_asset_regime": institutional_market.get("regime", "unknown"),
            "institutional_advisory_risk": institutional_market.get(
                "advisory_risk_multiplier", 0.5),
        } for idx, r in enumerate(research)]
        brain = self.brain.advise(portfolio)
        if brain.used:
            log.info("AI BRAIN posture=%s risk_mult=%.2f — %s",
                     brain.posture, brain.global_risk_multiplier, brain.commentary[:120])
        learning = {}
        if self.cfg.ai_shadow_enabled and portfolio:
            try:
                overlays = self.brain.shadow_advise(portfolio, brain)
                learning = AutonomousLearningPipeline(
                    min_observations=self.cfg.ai_shadow_min_observations,
                    database=self.db,
                ).run_cycle(cycle, portfolio, overlays)
            except Exception as exc:
                log.error("autonomous learning pipeline failed: %s", exc)

        # 3-6) PM → Strategy → Risk → Execution → Treasurer, per ticker.
        # The deployed cap gates on GROSS exposure so shorts consume budget too.
        deployed = self._gross_exposure(state)
        executed: List[Dict] = []
        proposed_institutional_risk = max(.5, min(1.0, float(
            institutional_market.get("advisory_risk_multiplier", .5) or .5
        )))
        institutional_risk = applied_multiplier(
            proposed_institutional_risk,
            institutional_promotion_stage,
            self.cfg.institutional_multiplier_enabled,
        )
        institutional_intelligence["promotion"] = {
            "key": PROMOTION_KEY,
            "stage": institutional_promotion_stage,
            "feature_flag_enabled": self.cfg.institutional_multiplier_enabled,
            "multiplier_active": institutional_multiplier_active,
            "proposed_multiplier": proposed_institutional_risk,
            "applied_multiplier": institutional_risk,
        }
        for idx, r in enumerate(research):
            sym, snap, verdict = r["symbol"], r["snap"], r["verdict"]
            try:
                strat = self.pm.assign_strategy(sym, idx)
                pos = state.get("positions", {}).get(sym)
                # Position-first routing: an open trade always finishes under the desk
                # that opened it, even if the assignment rotation changes over time.
                if pos and pos.get("strategy") in ("wheel", "ladder", "spread"):
                    strat = pos["strategy"]
                # A pairs leg belongs to the Pairs Desk (6d) — core desks hands off.
                pairs_owned = bool(pos) and pos.get("strategy") == "pairs"
                if pairs_owned:
                    strat = "pairs"
                alt_tilt = alt_signals[sym].tilt if sym in alt_signals else 0.0
                board_tilt = board[sym].tilt if sym in board else 0.0
                hermes_tilt = hermes.tilt.get(sym, 0.0)
                if hermes_tilt <= -1.0:      # data quarantine always wins outright
                    tilt = hermes_tilt
                else:                        # advisory layers stack, but stay bounded
                    tilt = max(-0.20, min(0.20, alt_tilt + board_tilt + hermes_tilt))
                conviction, risk_mult, budget = self.pm.effective(verdict, brain, equity, tilt)
                # Hermes strategy calibration: budget leans toward desks with a proven
                # realized edge (bounded 0.70–1.15; hard risk ceilings still apply).
                budget *= hermes.strategy_weights.get(strat, 1.0) * vol_scale * institutional_risk
                if pairs_owned:
                    intents = []
                elif strat == "wheel":
                    chain = self.client.get_option_chain(sym, snap.price, self.cfg.wheel_dte_min,
                                                         self.cfg.wheel_dte_max, snap.vol)
                    intents = self.wheel.decide(sym, snap, pos, verdict, budget, chain)
                elif strat == "spread":
                    chain = self.client.get_option_chain(sym, snap.price, self.cfg.wheel_dte_min,
                                                         self.cfg.wheel_dte_max, snap.vol,
                                                         kinds=("put",))
                    intents = self.spread.decide(sym, snap, pos, verdict, budget, chain)
                else:
                    intents = self.ladder.decide(sym, snap, pos, verdict, budget)
                if trade:
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conviction, allow_new_risk)
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

        # 6b) Copy-trading desk — mirror external disclosure feed (risk-gated)
        if trade and self.cfg.copy_trading_enabled:
            try:
                signals = self.copy.fetch_signals()
                if signals:
                    c_intents = self.copy.decide(signals, state, equity, self.client.get_price)
                    conv = max(self.cfg.min_council_conviction, 0.6)
                    done, deployed = self.execution.execute(c_intents, state, cycle, equity,
                                                            deployed, conv, allow_new_risk)
                    executed += done
                    if done:
                        log.info("COPY desk mirrored %d trade(s)", len(done))
            except Exception as exc:
                log.error("copy-trading step failed: %s", exc)

        # 6c) Day-Trading / Forex desk — intraday momentum + mean-reversion on the
        # FX majors (and any extra DAY_TRADE_SYMBOLS), disjoint from the core tickers.
        if trade and self.cfg.day_trading_enabled:
            if self.cfg.broker == "robinhood":
                universe = list(self.cfg.day_trade_symbols)
            else:
                universe = [*self.cfg.forex_pairs, *self.cfg.day_trade_symbols]
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for sym in universe:
                try:
                    snap, verdict = self.research.research(sym, bench)
                    pos = state.get("positions", {}).get(sym)
                    conv = 0.70   # technical-signal desk; risk engine still gates size
                    budget = self.risk.position_budget(equity, conv, 1.0) \
                        * hermes.strategy_weights.get("daytrade", 1.0) * vol_scale * institutional_risk
                    intents = self.dayts.decide(sym, snap, pos, budget, today)
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conv, allow_new_risk)
                    executed += done
                    self.db.log_council(cycle, sym, verdict.conviction, verdict.direction,
                                        verdict.composite_score, verdict.risk_multiplier, verdict.metrics)
                    npos = state.get("positions", {}).get(sym, {})
                    shares = npos.get("shares", 0) or 0
                    self.db.log_snapshot(cycle, sym, "daytrade", npos.get("strategy") or "flat",
                                         shares, npos.get("cost_basis", 0.0), snap.price,
                                         shares * snap.price, 0.0)
                except Exception as exc:
                    log.error("day-desk %s failed: %s", sym, exc)
            if self.cfg.day_trading_enabled:
                log.info("DAY/FOREX desk ran %d symbol(s)", len(universe))

        # 6d) Pairs / StatArb desk — market-neutral spreads on cointegrated pairs
        # (long the cheap leg, short the rich leg). Both legs are risk-gated; an
        # orphan leg is closed immediately. Uses core research when available.
        if trade and self.cfg.pairs_enabled:
            from intelligence import engines
            snaps = {r["symbol"]: r["snap"] for r in research}
            for pair in self.cfg.pairs:
                try:
                    if ":" not in pair:
                        continue
                    sym_a, sym_b = (p.strip() for p in pair.split(":", 1))
                    snap_a = snaps.get(sym_a) or self.research.research(sym_a, bench)[0]
                    snap_b = snaps.get(sym_b) or self.research.research(sym_b, bench)[0]
                    coint = engines.cointegration(snap_a.closes, snap_b.closes)
                    pos_a = state.get("positions", {}).get(sym_a)
                    pos_b = state.get("positions", {}).get(sym_b)
                    conv = 0.70   # signal desk; the Risk Officer still gates size
                    budget = self.risk.position_budget(equity, conv, 1.0) \
                        * hermes.strategy_weights.get("pairs", 1.0) * vol_scale * institutional_risk
                    intents = self.pairs_desk.decide(sym_a, sym_b, snap_a.price, snap_b.price,
                                                     pos_a, pos_b, budget, coint)
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conv, allow_new_risk)
                    executed += done
                    if done:
                        log.info("PAIRS desk %s/%s: %d order(s), z=%+.2f",
                                 sym_a, sym_b, len(done), coint.get("spread_z", 0.0))
                except Exception as exc:
                    log.error("pairs desk %s failed: %s", pair, exc)

        # 7) Treasurer — equity curve
        acct = self.client.get_account()
        if self.cfg.trading_capital and self.cfg.trading_capital > 0:
            eq_now, cash_now = self._sleeve(state)
        else:
            eq_now, cash_now = acct["equity"], acct["cash"]
        self.db.log_equity(cycle, eq_now, cash_now, self._position_value(state),
                           state.get("realized_pnl", 0.0), state.get("premium_collected", 0.0), mode)

        return {"cycle": cycle, "equity": eq_now, "cash": cash_now,
                "research": research, "brain": brain, "executed": executed,
                "ai_shadow": learning,
                "deployed": self._position_value(state), "halt": halt,
                "reconciliation": reconciliation,
                "institutional_intelligence": institutional_intelligence,
                "hermes": hermes, "board": board, "vol_scale": round(vol_scale, 3)}
