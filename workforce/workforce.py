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

from dataclasses import asdict
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from config import Config
from database import Database
from execution.idempotency import execution_intent_id
from intelligence.agents import Council, CouncilVerdict, MarketSnapshot
from risk.portfolio_governor import (
    PortfolioRiskGovernor,
    PortfolioRiskInput,
    PortfolioRiskLimits,
)
from strategies.base import OrderIntent, StrategyContext, fee_cost, validate_order_intent
from intelligence.advisors import AdvisoryBoard
from intelligence.ai_brain import AIBrain, BrainVerdict
from intelligence.alt_data import AltData
from intelligence.autonomous_learning import AutonomousLearningPipeline
from intelligence.hermes import Hermes, HermesReport
from intelligence.intraday import IntradayOverlay
from intelligence.regime import classify_regime, gate as regime_gate
from intelligence.institutional_research import (
    PROMOTION_KEY,
    InstitutionalResearchFabric,
    applied_multiplier,
    multiplier_enabled,
)
from risk.risk_engine import RiskEngine
from strategies.copy_trading import CopyTrader
from strategies.credit_spreads import CreditSpreads
from strategies.day_trading import DayTrading
from strategies.pairs_trading import PairsDesk
from strategies.promoted import BacktestStrategyAdapter, enabled_strategy_ids
from strategies.trailing_ladder import TrailingLadder
from strategies.wheel_strategy import WheelStrategy
from utils.logger import get_logger
from utils.notify import Notifier
from utils.quote_cache import CachedBroker
from utils.bar_recorder import BarRecorder
from utils.realtime import RealtimeGuard
from utils.state_store import record_event

log = get_logger("workforce")


def gross_symbol_value(client, state: Dict[str, Any], symbol: str) -> float:
    """Gross value held in ONE symbol, as the risk gates must see it.

    Gross (|shares|) because a short is exposure too. Falls back to the recorded
    cost basis when the venue cannot quote the symbol: a 0.0 price would make the
    position weigh nothing against the caps, which is precisely how an
    unpriceable row can quietly widen the risk envelope. Never raises, never
    returns a negative or non-finite number — a bad price must make the gate
    stricter, not silently disable it.

    Module-level on purpose: the per-position cap and the total-deployed cap both
    call it, and they must never disagree about what one symbol is worth.
    """
    try:
        pos = (state.get("positions") or {}).get(symbol) or {}
        shares = abs(float(pos.get("shares", 0) or 0))
        if not shares:
            return 0.0
        try:
            price = float(client.get_price(symbol) or 0.0)
        except Exception:
            price = 0.0
        if price <= 0:
            price = float(pos.get("cost_basis", 0.0) or 0.0)
        value = shares * max(0.0, price)
        return value if math.isfinite(value) else 0.0
    except Exception as exc:
        log.warning("gross value lookup failed for %s: %s", symbol, exc)
        return 0.0


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
    def __init__(self, client, risk: RiskEngine, db: Database, cfg: Config,
                 governor: PortfolioRiskGovernor | None = None):
        self.client = client
        self.risk = risk
        self.db = db
        self.cfg = cfg
        # Portfolio-level second gate (risk/portfolio_governor.py). Optional so
        # unit tests can construct ExecutionTrader without one; Firm always
        # injects a live governor unless PORTFOLIO_GOVERNOR=false.
        self.governor = governor

    def _governor_decision(self, equity: float, intent: OrderIntent,
                           dec, state: Dict[str, Any],
                           cycle_gross: list) -> bool:
        """Veto-only portfolio backstop. Returns True when the intent may flow.

        Runs AFTER RiskEngine.approve() as defense-in-depth: the smooth
        portfolio throttle is applied earlier at the budget stage
        (Firm._governor_cycle_gate), so by the time an intent reaches this
        gate the only governor outcomes that matter are the hard ones —
        max-drawdown stop and gross-exposure cap breach. This gate never
        mutates the intent (no qty/set_position fixup risk); it only blocks.
        Exits (risk_check=False) never reach this gate. Fail-closed: any
        exception → intent blocked.
        """
        gov = self.governor
        if gov is None:
            return True
        try:
            peak = float(state.get("equity_peak") or equity or 0.0)
            drawdown = (peak - equity) / peak if peak > 0 else 0.0
            gross = cycle_gross[0] + dec.max_notional
            verdict = gov.size(PortfolioRiskInput(
                equity=equity,
                proposed_notional=dec.max_notional,
                raw_kelly_fraction=1.0,          # Kelly neutral — budget stage owns sizing
                gross_exposure=gross,
                existing_position_value=gross_symbol_value(self.client, state, intent.symbol),
                realized_vol_annual=0.0,        # RiskEngine.vol_scalar already targets vol
                max_abs_correlation=0.0,        # no correlation matrix yet — neutral
                drawdown=drawdown,
                liquidity_cap_notional=None,
            ))
            audit = {
                "cycle": None, "symbol": intent.symbol, "purpose": intent.purpose,
                "approved": verdict.approved, "reason": verdict.reason,
                "final_notional": round(verdict.final_notional, 2),
                "risk_scalar": round(verdict.risk_scalar, 4),
                "drawdown": round(drawdown, 6),
                "gross_exposure": round(gross, 2),
            }
            self.db.append_audit("portfolio_governor", audit)
            record_event(state, "portfolio_governor", audit)
            if not verdict.approved:
                log.info("GOVERNOR BLOCK %s %s: %s", intent.symbol, intent.purpose,
                         verdict.reason)
                return False
            # Approved intents consume gross-exposure room for later intents
            # this cycle (single mutable cell — execute() is single-threaded).
            cycle_gross[0] = gross
            return True
        except Exception as exc:  # fail-closed
            log.error("GOVERNOR ERROR %s %s: %s — blocking", intent.symbol, intent.purpose, exc)
            record_event(state, "governor_error",
                         {"symbol": intent.symbol, "purpose": intent.purpose, "error": str(exc)})
            self.db.append_audit("governor_error", {"symbol": intent.symbol, "error": str(exc)})
            return False

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

    @staticmethod
    def _adds_exposure(intent: OrderIntent) -> bool:
        return bool(
            intent.side == "buy"
            or (intent.risk_check and intent.side == "sell" and intent.kind == "equity")
            or intent.side == "sell_to_open"
        )

    def reconcile_pending_orders(
        self, state: Dict[str, Any], cycle: int, deployed: float
    ) -> float:
        """Resolve persisted submissions without ever assuming an acknowledgement filled.

        Status lookup is an optional broker capability. When it is unavailable,
        errors, or returns an unknown state, the lock remains in place.
        """
        if state.get("_pending_reconciled_cycle") == cycle:
            return deployed
        state["_pending_reconciled_cycle"] = cycle
        pending_orders = state.get("pending_orders", {})
        getter = getattr(self.client, "get_order_status", None)
        if not pending_orders or not callable(getter):
            return deployed

        terminal_failure = {"cancelled", "canceled", "rejected", "expired", "failed"}
        for symbol, pending in list(pending_orders.items()):
            intent_id = str(pending.get("intent_id") or "")
            broker_ref = str(pending.get("broker_ref") or "")
            if not intent_id or not broker_ref:
                continue
            try:
                try:
                    result = getter(broker_ref, symbol)
                except TypeError:
                    result = getter(broker_ref)
                status = str((result or {}).get("status", "")).lower()
            except Exception as exc:
                self.db.append_audit("pending_reconciliation_error", {
                    "cycle": cycle, "symbol": symbol, "intent_id": intent_id,
                    "error": type(exc).__name__,
                })
                continue

            if status in terminal_failure:
                self.db.update_execution_intent(
                    intent_id, "failed", broker_ref=broker_ref,
                    detail={"broker_status": status},
                )
                pending_orders.pop(symbol, None)
                self.db.append_audit("pending_order_released", {
                    "cycle": cycle, "symbol": symbol, "intent_id": intent_id,
                    "broker_ref": broker_ref, "status": status,
                })
                record_event(state, "pending_order_released",
                             {"symbol": symbol, "status": status})
                continue
            if status != "filled":
                continue

            raw_intent = pending.get("intent")
            try:
                recovered = OrderIntent(**raw_intent)
                blocker = validate_order_intent(recovered)
                if blocker:
                    raise ValueError(blocker)
            except Exception as exc:
                self.db.append_audit("pending_reconciliation_error", {
                    "cycle": cycle, "symbol": symbol, "intent_id": intent_id,
                    "error": f"invalid persisted intent: {type(exc).__name__}",
                })
                continue

            # Establish a defensible fill price BEFORE mutating anything. Booking a
            # fill at 0 writes a zero cost basis, which makes every later
            # realized-P&L calculation on that row read as pure profit — the exact
            # corruption position_audit reports as "cost basis is missing or
            # invalid". On a bad price, keep the order pending and look again next
            # cycle rather than record a fiction. Ordering matters: this must come
            # before _apply, or a rejected price would leave state already mutated
            # with the order still pending, and the next cycle would apply it twice.
            fill_price = (result or {}).get("fill_price")
            if fill_price is None:
                fill_price = (self.client.get_price(symbol)
                              if recovered.kind == "equity" else recovered.premium)
            try:
                fill_price = float(fill_price or 0.0)
            except (TypeError, ValueError):
                fill_price = 0.0
            if not math.isfinite(fill_price) or fill_price <= 0:
                log.warning("FILLED order %s (%s) has no defensible fill price; keeping pending",
                            broker_ref, symbol)
                self.db.append_audit("pending_reconciliation_error", {
                    "cycle": cycle, "symbol": symbol, "intent_id": intent_id,
                    "error": "filled order has no defensible fill price",
                })
                continue

            self._apply(recovered, state)
            transaction_cost = max(
                0.0, float((result or {}).get("transaction_cost", 0.0) or 0.0)
            )
            state["transaction_costs"] = state.get("transaction_costs", 0.0) + transaction_cost
            state["realized_pnl"] = state.get("realized_pnl", 0.0) - transaction_cost
            if self._adds_exposure(recovered):
                deployed += recovered.est_notional
            filled_qty = (result or {}).get("filled_qty")
            self.db.log_trade({
                "cycle": cycle, "symbol": recovered.symbol,
                "strategy": recovered.strategy, "kind": recovered.kind,
                "side": recovered.side,
                "qty": filled_qty if filled_qty is not None else recovered.qty,
                "price": fill_price, "premium": recovered.premium,
                "notional": recovered.est_notional, "purpose": recovered.purpose,
                "reason": recovered.reason,
                "mode": getattr(self.client, "mode", self.cfg.mode),
                "simulated": (result or {}).get("simulated", False),
                # Broker attribution: a reconciled fill is the one trade the desk
                # did NOT witness happen, so the ledger has to carry enough to tie
                # the row back to the venue's own record of it.
                "order_id": broker_ref,
                "client_order_id": ((result or {}).get("client_order_id")
                                    or pending.get("client_order_id")),
                "order_status": "filled",
                "submitted_at": pending.get("submitted_at"),
                "filled_at": (result or {}).get("filled_at"),
            })
            self.db.update_execution_intent(
                intent_id, "filled", broker_ref=broker_ref,
                detail={"transaction_cost": transaction_cost, "reconciled_cycle": cycle},
            )
            pending_orders.pop(symbol, None)
            self.db.append_audit("pending_order_filled", {
                "cycle": cycle, "symbol": symbol, "intent_id": intent_id,
                "broker_ref": broker_ref, "state_applied": True,
            })
            record_event(state, "pending_order_filled",
                         {"symbol": symbol, "intent_id": intent_id})
        return deployed

    def execute(self, intents: List[OrderIntent], state: Dict[str, Any], cycle: int,
                equity: float, deployed: float, conviction: float,
                allow_new_risk: bool = True) -> tuple[List[Dict], float]:
        """Returns (executed, deployed) — the running deployed value is threaded back
        so the total-deployed cap accounts for positions opened earlier this cycle.

        When allow_new_risk is False (circuit breaker / kill switch), risk-ADDING
        intents are blocked but exits and state updates still flow, so the desk can
        always reduce exposure."""
        done = []
        deployed = self.reconcile_pending_orders(state, cycle, deployed)
        # Running gross-exposure accumulator for the portfolio-governor backstop:
        # starts from priced positions, grows as intents clear the gates, so the
        # gross-exposure cap is enforced across intents within one cycle.
        # Single-element list as a mutable cell (execute() is single-threaded).
        cycle_gross = [sum(gross_symbol_value(self.client, state, s)
                           for s in (state.get("positions") or {}))]
        for intent in intents:
            intent_id = ""
            try:
                state.setdefault("pending_orders", {})
                if intent.kind == "state":
                    self._apply(intent, state)
                    record_event(state, intent.purpose, {"symbol": intent.symbol, "reason": intent.reason})
                    continue
                malformed = validate_order_intent(intent)
                if malformed:
                    log.error("INVALID INTENT BLOCK %s %s: %s",
                              intent.symbol, intent.purpose, malformed)
                    record_event(state, "invalid_intent_block",
                                 {"symbol": intent.symbol, "purpose": intent.purpose,
                                  "reason": malformed})
                    self.db.append_audit("invalid_intent_block", {
                        "cycle": cycle, "symbol": intent.symbol,
                        "purpose": intent.purpose, "reason": malformed,
                    })
                    continue
                pending = state.get("pending_orders", {}).get(intent.symbol)
                if pending:
                    reason = "unconfirmed broker order already pending"
                    log.warning("PENDING ORDER BLOCK %s %s", intent.symbol, intent.purpose)
                    record_event(state, "pending_order_block",
                                 {"symbol": intent.symbol, "purpose": intent.purpose,
                                  "reason": reason})
                    self.db.append_audit("pending_order_block", {
                        "cycle": cycle, "symbol": intent.symbol,
                        "purpose": intent.purpose, "pending": pending,
                    })
                    continue
                if intent.risk_check and not allow_new_risk:
                    log.info("HALT BLOCK %s %s — new risk suspended", intent.symbol, intent.purpose)
                    record_event(state, "halt_block",
                                 {"symbol": intent.symbol, "purpose": intent.purpose})
                    self.db.append_audit("risk_block", {"cycle": cycle, "symbol": intent.symbol,
                                         "purpose": intent.purpose, "reason": "new risk suspended"})
                    continue
                if intent.risk_check:
                    dec = self.risk.approve(equity, deployed, intent.est_notional,
                                            conviction, intent.symbol,
                                            gross_symbol_value(self.client, state, intent.symbol))
                    if not dec.approved:
                        log.info("RISK BLOCK %s %s: %s", intent.symbol, intent.purpose, dec.reason)
                        record_event(state, "risk_block",
                                     {"symbol": intent.symbol, "purpose": intent.purpose, "reason": dec.reason})
                        self.db.append_audit("risk_block", {"cycle": cycle, "symbol": intent.symbol,
                                             "purpose": intent.purpose, "reason": dec.reason})
                        continue
                    # Portfolio-governor backstop (veto-only): hard max-drawdown
                    # stop + gross-exposure cap, evaluated on the live book.
                    if not self._governor_decision(equity, intent, dec, state, cycle_gross):
                        record_event(state, "governor_block",
                                     {"symbol": intent.symbol, "purpose": intent.purpose})
                        self.db.append_audit("governor_block", {"cycle": cycle,
                                             "symbol": intent.symbol, "purpose": intent.purpose})
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
                else:
                    res = self.client.submit_option_order(intent.contract, intent.qty, intent.side, intent.premium)
                status = str(res.get("status", "")).lower()
                if status not in ("filled", "submitted"):
                    self.db.update_execution_intent(intent_id, "failed",
                                                    detail={"status": str(res.get("status", "rejected"))})
                    self.db.append_audit("execution_failed", {
                        "cycle": cycle, "intent_id": intent_id,
                        "status": str(res.get("status", "rejected")),
                    })
                    log.warning("order not filled %s: %s", intent.symbol, res)
                    continue
                broker_ref = str(res.get("order_id") or res.get("id") or "")
                if status == "submitted":
                    pending = {
                        "intent_id": intent_id,
                        "broker_ref": broker_ref,
                        "cycle": cycle,
                        "side": intent.side,
                        "qty": intent.qty,
                        "purpose": intent.purpose,
                        # Carried so the reconciled fill can be tied back to the
                        # venue's record — the status lookup does not always
                        # return them, and by then the submit result is gone.
                        "client_order_id": str(res.get("client_order_id") or ""),
                        "submitted_at": str(res.get("submitted_at") or ""),
                        "intent": asdict(intent),
                    }
                    state.setdefault("pending_orders", {})[intent.symbol] = pending
                    self.db.update_execution_intent(
                        intent_id, "submitted", broker_ref=broker_ref,
                        detail={"confirmation": "pending"},
                    )
                    self.db.append_audit("execution_result", {
                        "cycle": cycle, "intent_id": intent_id, "status": "submitted",
                        "broker_ref": broker_ref, "state_applied": False,
                    })
                    record_event(state, "order_submitted", {
                        "symbol": intent.symbol, "purpose": intent.purpose,
                        "intent_id": intent_id, "broker_ref": broker_ref,
                    })
                    done.append({
                        "symbol": intent.symbol, "purpose": intent.purpose,
                        "reason": intent.reason, "status": "submitted",
                    })
                    log.warning("SUBMITTED %s %s — awaiting broker fill confirmation",
                                intent.symbol, intent.purpose)
                    continue
                price = (res.get("fill_price") if res.get("fill_price") is not None
                         else self.client.get_price(intent.symbol)
                         if intent.kind == "equity" else intent.premium)
                # Transaction costs: charge the estimated round trip when a position
                # is CLOSED, so realized P&L — and therefore the equity curve and
                # Hermes' scorecard — are NET of spread rather than gross.
                if intent.realized_delta:
                    gross = float(intent.realized_delta)
                    cost = fee_cost(intent.symbol, abs(float(intent.qty or 0) * float(price or 0)),
                                    self.cfg)
                    if cost > 0:
                        intent.realized_delta = gross - cost
                        log.info("%s %s realized $%.4f gross → $%.4f net (est. cost $%.4f)",
                                 intent.symbol, intent.purpose, gross, intent.realized_delta, cost)
                self._apply(intent, state)
                transaction_cost = max(0.0, float(res.get("transaction_cost", 0.0) or 0.0))
                state["transaction_costs"] = state.get("transaction_costs", 0.0) + transaction_cost
                state["realized_pnl"] = state.get("realized_pnl", 0.0) - transaction_cost
                # Consume deployed budget for: equity buys, risk-gated equity shorts,
                # and cash-secured puts (sell_to_open carries collateral in
                # est_notional; covered calls are sell_to_open with est_notional 0,
                # so they correctly add nothing). Keeps stacked CSPs within the cap
                # within a single cycle, before _gross_exposure re-seeds next cycle.
                if self._adds_exposure(intent):
                    deployed += intent.est_notional
                self.db.log_trade({
                    "cycle": cycle, "symbol": intent.symbol, "strategy": intent.strategy,
                    "kind": intent.kind, "side": intent.side, "qty": intent.qty,
                    "price": price, "premium": intent.premium, "notional": intent.est_notional,
                    "purpose": intent.purpose, "reason": intent.reason,
                    "mode": getattr(self.client, "mode", self.cfg.mode),
                    "simulated": res.get("simulated", True),
                })
                self.db.update_execution_intent(
                    intent_id, "filled", broker_ref=broker_ref,
                    detail={"transaction_cost": transaction_cost},
                )
                self.db.append_audit("execution_result", {
                    "cycle": cycle, "intent_id": intent_id, "status": "filled",
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
        # Real-time quote guard + per-cycle price cache.
        #
        # OFF BY DEFAULT, deliberately. Both change desk behaviour — the guard
        # can reject a tick (so the desk stands down where it previously traded)
        # and the cache pins one price per symbol per cycle — and
        # public/evaluation.json freezes behaviour for the 90-day out-of-sample
        # window ending 2026-10-24. Merging this must not silently invalidate
        # that measurement, so the code ships wired but dormant: flip QUOTE_GUARD
        # to true once the window closes and no code change or merge is needed.
        #
        # Wrapped here rather than in utils.broker.get_broker() so the factory
        # keeps returning the bare adapter its contract promises; every role
        # below shares this instance. Order matters: validate the fresh read,
        # then cache the validated value.
        self.feed = None
        if getattr(cfg, "quote_guard_enabled", False):
            self.feed = RealtimeGuard(client, max_jump_pct=cfg.quote_max_jump_pct,
                                      stale_after_s=cfg.quote_stale_after_s,
                                      max_venue_age_s=cfg.quote_max_venue_age_s)
            client = CachedBroker(self.feed)
            log.info("real-time quote guard ENABLED (jump>%.0f%% rejected, "
                     "venue prints >%.0fs flagged)",
                     cfg.quote_max_jump_pct * 100, cfg.quote_max_venue_age_s)
        self.client = client
        self.db = db
        # Passive history accumulation. Robinhood's API has no candles, so the
        # only way to get real bars out of it is to record the quotes the desk
        # already fetches. Pure logging: it observes, writes rows, and influences
        # no decision — which is why it is allowed to run during the evaluation
        # window while the quote guard is not.
        self.bars = None
        if getattr(cfg, "bar_recorder_enabled", True):
            self.bars = BarRecorder(db, getattr(cfg, "bar_intervals",
                                                getattr(cfg, "bar_interval_minutes", 5)),
                                    source=getattr(client, "mode", "live"))
        self.council = Council()
        self.brain = AIBrain(cfg)
        self.alt = AltData(cfg)   # QuiverQuant insider/congress alt-data overlay
        # Intraday confirmation from the desk's own recorded bars. The council is a
        # DAILY estimator (sma200, 12-1 momentum, 52-week high) re-run every few
        # minutes, so it has no intraday view at all; this supplies one without
        # touching the daily series those agents depend on. Default off.
        self.intraday = IntradayOverlay(cfg, db)
        self.hermes = Hermes(cfg) # background guardian: data integrity + scores + self-calibration
        self.board = AdvisoryBoard(cfg)  # Buffett/Munger/Macro/Growth/Quant council + risk gate
        self.notifier = Notifier(cfg)
        self.risk = RiskEngine(cfg)
        self.research = ResearchDesk(client, self.council)
        self.pm = PortfolioManager(cfg, self.risk)
        # Portfolio governor (risk/portfolio_governor.py): second risk gate.
        # Kelly is neutralized in the live wiring (fractional_kelly=1.0 and the
        # call sites pass raw_kelly=1.0 → pass-through), so the governor acts
        # purely as a portfolio overlay — hard drawdown stop, drawdown
        # throttle, gross-exposure cap, single-position room, correlation
        # penalty. RiskEngine remains the position sizer. Reduction-only: it
        # can only shrink or block the RiskEngine-approved budget, never grow
        # it. PORTFOLIO_GOVERNOR=false restores the pre-governor behaviour.
        self.governor = None
        if getattr(cfg, "portfolio_governor_enabled", True):
            self.governor = PortfolioRiskGovernor(PortfolioRiskLimits(
                fractional_kelly=1.0,  # Kelly neutral — see above
                target_vol_annual=0.0,  # RiskEngine.vol_scalar already targets vol
                max_gross_exposure_pct=cfg.portfolio_max_gross_exposure_pct,
                max_single_position_pct=cfg.max_allocation_pct,
                max_pair_correlation=cfg.portfolio_max_pair_correlation,
                max_drawdown_soft=cfg.portfolio_max_drawdown_soft,
                max_drawdown_hard=cfg.portfolio_max_drawdown_hard,
            ))
            log.info("portfolio governor ENABLED (gross<=%.0f%%, dd soft/hard %.0f%%/%.0f%%)",
                     cfg.portfolio_max_gross_exposure_pct * 100,
                     cfg.portfolio_max_drawdown_soft * 100,
                     cfg.portfolio_max_drawdown_hard * 100)
        self.execution = ExecutionTrader(client, self.risk, db, cfg,
                                         governor=self.governor)
        self.wheel = WheelStrategy(cfg)
        self.ladder = TrailingLadder(cfg)
        self.spread = CreditSpreads(cfg)
        self.copy = CopyTrader(cfg)
        self.dayts = DayTrading(cfg)
        self.pairs_desk = PairsDesk(cfg)
        # Promoted research desks (strategies/promoted.py): validated backtest
        # strategies running as live desks. Double-gated
        # (PROMOTED_DESKS_ENABLED + PROMOTED_STRATEGIES); empty by default so
        # nothing validated in research reaches a broker by accident.
        self.promoted_adapters = []
        for sid in enabled_strategy_ids(cfg):
            try:
                self.promoted_adapters.append(BacktestStrategyAdapter(sid, db))
            except Exception as exc:
                log.error("promoted strategy %s init failed: %s", sid, exc)
        if self.promoted_adapters:
            log.info("promoted desks ENABLED: %s on symbols %s",
                     [a.strategy_id for a in self.promoted_adapters],
                     list(cfg.promoted_symbols or []))
        # Intel workforce (intel/workforce/) — 8-agent advisory-only analyst
        # team. Runs AFTER the research block; never emits orders, never
        # touches risk caps or the arming chain. Import-guarded so the desk
        # boots even if the module is absent.
        self.intel_desk = None
        try:
            from intel.workforce.desk import IntelDesk
            self.intel_desk = IntelDesk(cfg)
        except Exception as exc:
            log.warning("intel workforce unavailable: %s", exc)
        # Per-cycle stash for risk events that must page the owner (e.g. halt
        # flatten). Reset at the top of every run_cycle; drained by _maybe_notify.
        self._cycle_risk_events = []

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
        Includes cash-secured-put collateral (0-share short_put legs) — see below.

        Prices through `gross_symbol_value`, which falls back to cost basis when the
        venue cannot quote a symbol. Multiplying by a 0.0 price instead would let
        an unpriceable position contribute NOTHING to deployed capital and quietly
        raise the total-deployed cap by its full size — the same bypass the
        per-position cap had. desks/stocks is carrying three such rows right now
        (BTCUSD/ETHUSD/SOLUSD at price 0.0 inside an equity desk). Note
        `_position_value` deliberately does NOT do this: marking to cost in the
        equity calculation would hide losses, whereas a risk gate should
        over-count capital it cannot price, never under-count it."""
        total = 0.0
        for sym, pos in state.get("positions", {}).items():
            if pos.get("shares", 0) or 0:
                total += gross_symbol_value(self.client, state, sym)
        return total + self._csp_collateral(state)

    @staticmethod
    def position_integrity(state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Positions whose recorded fields contradict each other.

        Reverse-engineering how one bad row was written is archaeology; the
        durable fix is to assert the invariant every cycle. desks/stocks carries
        DIA at -9.935112 shares with state "long" — a short recorded as a long,
        which makes every downstream reader (P&L sign, exposure direction, the
        exit path that assumes a long) quietly wrong. Nothing in the desk checked
        that a position's share sign agrees with the direction it claims.

        Read-only and never raises: this reports, the owner decides.
        """
        out: List[Dict[str, Any]] = []
        for sym, pos in ((state or {}).get("positions") or {}).items():
            if not isinstance(pos, dict):
                out.append({"symbol": sym, "issue": "position is not a record"})
                continue
            try:
                shares = float(pos.get("shares", 0) or 0)
            except (TypeError, ValueError):
                out.append({"symbol": sym, "issue": "shares is not a number",
                            "shares": repr(pos.get("shares"))[:40]})
                continue
            if not math.isfinite(shares):
                out.append({"symbol": sym, "issue": "shares is not finite",
                            "shares": str(shares)})
                continue
            state_label = str(pos.get("state") or pos.get("stage") or "").lower()
            if shares < 0 and state_label in ("long", "ladder_long"):
                out.append({"symbol": sym, "issue": "short position recorded as long",
                            "shares": shares, "state": state_label,
                            "strategy": pos.get("strategy", "")})
            elif shares > 0 and state_label in ("short", "ladder_short"):
                out.append({"symbol": sym, "issue": "long position recorded as short",
                            "shares": shares, "state": state_label,
                            "strategy": pos.get("strategy", "")})
            try:
                basis = float(pos.get("cost_basis", 0.0) or 0.0)
            except (TypeError, ValueError):
                basis = float("nan")
            # An open position must have a POSITIVE basis. Zero is not a
            # cheap position, it is a missing one — and it silently makes every
            # realized-P&L calculation on that row read as pure profit.
            if shares and (not math.isfinite(basis) or basis <= 0):
                out.append({"symbol": sym, "issue": "cost basis is missing or invalid",
                            "cost_basis": str(pos.get("cost_basis")),
                            "strategy": pos.get("strategy", "")})
        return out

    def cap_breaches(self, state: Dict[str, Any], equity: float) -> List[Dict[str, Any]]:
        """Positions already larger than the per-position cap allows.

        Reported, never auto-traded. A position can end up over the cap through a
        path no gate can prevent — an inherited position, a deposit-driven change
        in equity, or (until it was fixed) a cap that only measured the increment.
        Blocking further adds is automatic; unwinding is an owner decision, so the
        desk's job is to make the breach impossible to miss rather than to trade
        its way out of one on its own initiative."""
        out: List[Dict[str, Any]] = []
        if not math.isfinite(equity) or equity <= 0:
            return out
        cap = equity * self.cfg.max_allocation_pct
        for sym, pos in (state.get("positions") or {}).items():
            if not (pos.get("shares", 0) or 0):
                continue
            value = gross_symbol_value(self.client, state, sym)
            if value > cap:
                out.append({"symbol": sym, "value": round(value, 2),
                            "cap": round(cap, 2),
                            "over_pct": round(100.0 * (value / cap - 1.0), 1)
                            if cap > 0 else 0.0,
                            "pct_of_equity": round(100.0 * value / equity, 1)})
        return sorted(out, key=lambda r: r["value"], reverse=True)

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
            state["realized_day_start"] = float(state.get("realized_pnl", 0.0) or 0.0)
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

            # Capital-flow guard. A flat desk with no realized P&L did not suffer
            # a trading drawdown, so re-anchor deposits, withdrawals, and sleeve changes.
            realized_today = (float(state.get("realized_pnl", 0.0) or 0.0)
                              - float(state.get("realized_day_start", 0.0) or 0.0))
            no_activity = (not (state.get("positions") or {})) and abs(realized_today) < 1e-9
            if no_activity:
                if abs(day_return) > 1e-9:
                    log.info("circuit breaker baseline re-anchored $%.2f → $%.2f "
                             "(capital change, no trading activity today)", day_start, equity)
                    state["equity_day_start"] = equity
                    state["realized_day_start"] = float(
                        state.get("realized_pnl", 0.0) or 0.0
                    )
                    day_start, day_return = equity, 0.0
                if state.get("breaker_latched"):
                    state["breaker_latched"] = False

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

    def _reconcile_broker(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Make the broker the source of truth for WHAT WE OWN.

        The desk's positions live in state.json, which is runtime-only (gitignored,
        cached by the runner). If that state is ever lost — killed job, evicted
        cache, fresh machine — the desk would believe it is flat while the broker
        still holds the asset: it would re-buy (double exposure) and never manage
        or exit the orphan, since no strategy tracks it.

        So every cycle we compare the two:
          • broker holds something state doesn't know → ADOPT it under the ladder
            desk so stops and floors start protecting it immediately (basis from
            the broker when available, else the live price — conservative: it
            protects from here on rather than inventing a P&L history),
          • state holds something the broker doesn't → drop the ghost so it can't
            block new entries or emit sells for shares that do not exist.
        Fault-isolated: any broker hiccup leaves state untouched.
        """
        out = {"adopted": [], "dropped": [], "mismatched": [], "ok": True}
        try:
            broker = self.client.get_broker_positions() or {}
        except Exception as exc:
            log.warning("broker reconciliation skipped: %s", exc)
            out["ok"] = False
            return out
        if not isinstance(broker, dict):
            out["ok"] = False
            return out
        positions = state.setdefault("positions", {})

        def _norm(sym: str) -> str:
            return str(sym or "").upper().replace("-", "/").replace("/USD", "")

        held = {_norm(k): (k, v) for k, v in broker.items()
                if abs(float((v or {}).get("qty", 0) or 0)) > 0}
        known = {_norm(k) for k, v in positions.items()
                 if abs(float((v or {}).get("shares", 0) or 0)) > 0}

        # A shared symbol with different quantities is neither an orphan nor a
        # ghost. Never rewrite it automatically: expose the drift and block new
        # risk until a confirmed fill or an operator-reviewed repair resolves it.
        local_by_base = {_norm(k): (k, v) for k, v in positions.items()
                         if abs(float((v or {}).get("shares", 0) or 0)) > 0}
        for base in sorted(set(held) & set(local_by_base)):
            raw_sym, info = held[base]
            local_sym, local = local_by_base[base]
            broker_qty = float(info.get("qty", 0) or 0)
            local_qty = float(local.get("shares", 0) or 0)
            tolerance = 1e-8 if "/" in str(raw_sym) or "-" in str(raw_sym) else 1e-6
            if abs(broker_qty - local_qty) > tolerance:
                out["ok"] = False
                out["mismatched"].append({"symbol": local_sym,
                                           "local_qty": local_qty,
                                           "broker_qty": broker_qty,
                                           "delta_qty": broker_qty - local_qty,
                                           "quantity_tolerance": tolerance})
        if out["mismatched"]:
            log.error("broker quantity mismatch — state preserved: %s", out["mismatched"])
            return out

        for base, (raw_sym, info) in held.items():
            if base in known:
                continue
            qty = float(info.get("qty", 0) or 0)
            basis = float(info.get("avg_price", 0) or 0)
            if basis <= 0:
                try:
                    basis = float(self.client.get_price(raw_sym) or 0.0)
                except Exception:
                    basis = 0.0
            if basis <= 0:
                continue                      # no defensible basis → leave it alone
            sym = next((s for s in self.cfg.tickers if _norm(s) == base), raw_sym)
            positions[sym] = {"strategy": "ladder", "shares": qty, "cost_basis": basis,
                              "entry_price": basis, "peak": basis, "adopted": True,
                              "hard_floor": basis * (1 - self.cfg.ladder_catastrophic_pct
                                                     if self.cfg.ladder_enable_averaging
                                                     else 1 - self.cfg.ladder_hard_floor_pct)}
            out["adopted"].append(sym)
            log.warning("ADOPTED untracked broker position %s: %s @ %.6f — now under "
                        "ladder risk management", sym, qty, basis)

        for sym in [s for s in list(positions) if _norm(s) not in held
                    and abs(float((positions[s] or {}).get("shares", 0) or 0)) > 0]:
            # options/spreads are not equity holdings — never treat them as ghosts
            if (positions[sym] or {}).get("stage") or (positions[sym] or {}).get("contract"):
                continue
            out["dropped"].append(sym)
            log.warning("DROPPED ghost position %s — the broker reports no such holding", sym)
            positions.pop(sym, None)
        return out

    def _cadence_check(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Measure the real gap between cycles and flag a degraded schedule.

        The configured CYCLE_MINUTES is an intention, not a guarantee: shared
        schedulers throttle high-frequency crons, so the observed cadence is what
        actually bounds our risk management. Tolerate 3x the configured interval
        (or 90 minutes, whichever is larger) before declaring the schedule
        unreliable for opening new positions.
        """
        now = datetime.now(timezone.utc)
        expected = max(1, int(getattr(self.cfg, "cycle_minutes", 15)))
        prev = state.get("last_cycle_ts")
        gap = None
        if prev:
            try:
                gap = (now - datetime.fromisoformat(str(prev))).total_seconds() / 60.0
            except Exception:
                gap = None
        state["last_cycle_ts"] = now.isoformat()
        tolerance = max(expected * 3.0, 90.0)
        degraded = gap is not None and gap > tolerance
        reason = ("" if not degraded else
                  f"execution cadence degraded: {gap:.0f} min since the last cycle "
                  f"(expected ~{expected} min) — a new position could not be managed")
        return {"degraded": bool(degraded), "reason": reason,
                "gap_min": (round(gap, 1) if gap is not None else None),
                "expected_min": expected, "tolerance_min": round(tolerance, 1)}

    def _catastrophic_stop_sweep(self, state: Dict[str, Any], cycle: int,
                                 equity: float) -> List[Dict]:
        """Central per-position hard-stop backstop (upgrade/world-class).

        Wires up RiskEngine.hard_stop_breached(), which had zero callers.
        Each cycle, any equity position that has fallen further than
        cfg.catastrophic_stop_pct below its cost basis is liquidated —
        regardless of which desk opened it. This is the backstop for desks
        without their own downside stop (wheel-assigned shares sit unprotected
        otherwise). Wide by design: strategy-level stops fire first.

        Emits risk_check=False exit intents so the sweep works even during a
        kill-switch halt or governor hard stop — the desk must always be able
        to reduce risk. Never raises; fault-isolated per symbol.
        """
        floor = float(getattr(self.cfg, "catastrophic_stop_pct", 0.25) or 0.25)
        intents: List[OrderIntent] = []
        for sym, pos in list((state.get("positions") or {}).items()):
            try:
                if not isinstance(pos, dict):
                    continue
                # Equity shares only — options legs have their own lifecycle.
                if str(pos.get("strategy") or "") in ("wheel_option", "spread"):
                    continue
                shares = float(pos.get("shares", 0) or 0)
                if not shares or not math.isfinite(shares):
                    continue
                basis = float(pos.get("cost_basis", 0) or 0)
                if not math.isfinite(basis) or basis <= 0:
                    continue
                try:
                    price = float(self.client.get_price(sym) or 0.0)
                except Exception:
                    continue
                if not math.isfinite(price) or price <= 0:
                    continue
                breached = self.risk.hard_stop_breached(basis, price, floor)
                # hard_stop_breached is long-oriented; for shorts the loss is
                # a price RISE past the floor.
                if shares < 0:
                    breached = (price / basis - 1.0) >= abs(floor)
                if not breached:
                    continue
                side = "sell" if shares > 0 else "buy"
                intents.append(OrderIntent(
                    symbol=sym, strategy="risk", kind="equity",
                    purpose="catastrophic_stop",
                    reason=(f"catastrophic stop: {shares:+.4g} sh @ basis "
                            f"{basis:.2f} vs {price:.2f} "
                            f"({(price / basis - 1.0) * 100:+.1f}%)"),
                    side=side, qty=abs(shares), est_notional=0.0,
                    risk_check=False, clear_position=True,
                ))
                log.warning("CATASTROPHIC STOP %s: %+.4g sh, basis %.2f → %.2f",
                            sym, shares, basis, price)
            except Exception as exc:
                log.error("catastrophic sweep failed for %s: %s", sym, exc)
        if not intents:
            return []
        done, _ = self.execution.execute(intents, state, cycle, equity,
                                        0.0, 0.0, allow_new_risk=True)
        for d in done:
            record_event(state, "catastrophic_stop",
                         {"symbol": d.get("symbol"), "reason": "hard stop breached"})
        return done

    def _regime_gate(self, verdict, strategy_id: str) -> tuple:
        """Apply the regime gate (intelligence/regime.py) to one desk/symbol.

        Returns (budget_scale, entries_allowed). Reduction-only: stressed blocks
        new entries, bear/chop halve budgets and restrict desks. Exits always
        flow — the caller ANDs entries_allowed into allow_new_risk, and
        ExecutionTrader lets risk_check=False exits through during any halt.
        Fail-closed: any classification problem denies new entries.
        `verdict` may be a CouncilVerdict or a plain metrics dict.
        """
        if not getattr(self.cfg, "regime_gate_enabled", True):
            return 1.0, True
        try:
            if hasattr(verdict, "metrics"):
                regime = classify_regime(verdict.metrics,
                                         getattr(verdict, "direction", ""),
                                         getattr(verdict, "composite_score", 0.0))
            elif isinstance(verdict, dict):
                regime = classify_regime(verdict, "", 0.0)
            else:
                regime = classify_regime({}, "", 0.0)
            scale, allowed = regime_gate(regime, strategy_id)
            if not allowed or scale < 1.0:
                log.info("REGIME gate: %s desk in %s regime — scale %.2f, entries %s",
                         strategy_id, regime, scale, "allowed" if allowed else "BLOCKED")
            return scale, allowed
        except Exception as exc:      # fail-closed
            log.error("regime gate failed for %s: %s — denying new entries",
                      strategy_id, exc)
            return 0.0, False

    def _flatten_all_positions(self, state: Dict[str, Any], cycle: int,
                               equity: float, reason: str) -> tuple:
        """Emergency flatten: liquidate every equity/crypto position on halt.

        A halt that only blocks new risk while a bleeding book stays open
        protects nothing, so the kill switch and the daily circuit breaker now
        FLATTEN instead of merely freezing. Edge-triggered by the caller (once
        per halt episode via state["halt_flattened"]).

        Equity/crypto shares only — option legs are NOT auto-closed: the desk
        has never exercised an option close, and inventing one inside a
        protective sweep is how accidents happen. Unflattened option legs are
        returned separately so they can be paged for manual handling.

        Exits emit risk_check=False so they flow during the halt. Never raises;
        fault-isolated per symbol. Returns (flattened, open_option_legs).
        """
        intents: List[OrderIntent] = []
        open_options: List[Dict] = []
        for sym, pos in list((state.get("positions") or {}).items()):
            try:
                if not isinstance(pos, dict):
                    continue
                strat = str(pos.get("strategy") or "")
                if strat in ("wheel_option", "spread") or pos.get("contract"):
                    open_options.append({
                        "symbol": sym, "strategy": strat,
                        "contracts": pos.get("contracts"),
                        "strike": pos.get("strike"),
                        "note": "option leg NOT auto-closed — manual handling required",
                    })
                    log.warning("HALT FLATTEN skipped option leg %s (%s) — paging for manual close",
                                sym, strat)
                    continue
                shares = float(pos.get("shares", 0) or 0)
                if not shares or not math.isfinite(shares):
                    continue
                side = "sell" if shares > 0 else "buy"
                intents.append(OrderIntent(
                    symbol=sym, strategy="risk", kind="equity",
                    purpose="halt_flatten",
                    reason=f"halt flatten ({reason}): closing {shares:+.4g} {sym}",
                    side=side, qty=abs(shares), est_notional=0.0,
                    risk_check=False, clear_position=True,
                ))
                log.warning("HALT FLATTEN %s: closing %+.4g sh — %s", sym, shares, reason)
            except Exception as exc:
                log.error("halt flatten failed for %s: %s", sym, exc)
        flattened: List[Dict] = []
        if intents:
            done, _ = self.execution.execute(intents, state, cycle, equity,
                                            0.0, 0.0, allow_new_risk=True)
            flattened = done
            for d in done:
                record_event(state, "halt_flatten",
                             {"symbol": d.get("symbol"), "reason": reason})
        return flattened, open_options

    def _maybe_notify(self, state: Dict[str, Any], cycle: int, halt: Dict[str, Any],
                      recon: Dict[str, Any], hermes, brain, executed: List[Dict],
                      equity: float) -> None:
        """Page the owner on risk events. Fault-isolated; silent without creds.

        Wires up Notifier.maybe_risk_alert (circuit-breaker/kill-switch trips,
        broker disconnects, data quarantine — de-duplicated per reason per day)
        and Notifier.maybe_alert (cycle summary when something traded or the
        brain turned risk-off). With no channel configured this is a no-op.
        """
        n = getattr(self, "notifier", None)
        if n is None:
            return
        try:
            if not (n.telegram_configured or n.whatsapp_configured or n.configured):
                return
        except Exception:
            return
        try:
            base = float(state.get("equity_start") or 0.0)
            total_ret = (equity / base - 1.0) * 100.0 if base > 0 else 0.0
            health = {
                "circuit_breaker": {
                    "halted": bool(halt.get("halted")),
                    "reason": str(halt.get("reason") or ""),
                    "day_return": float(halt.get("day_return") or 0.0),
                    "limit_pct": float(halt.get("limit_pct") or 0.10),
                },
                "broker_online": bool((recon or {}).get("ok", True)),
                "hermes": {"quarantined":
                           list(getattr(hermes, "quarantined", None) or [])},
            }
            status = {
                "health": health,
                "account": {"equity": equity},
                "pnl": {"total_return_pct": total_ret},
                "cycle": cycle,
                "firm": self.cfg.firm_name,
                "mode": state.get("mode", ""),
                "executed_this_cycle": executed,
                "brain": {"posture": getattr(brain, "posture", "neutral") or "neutral"},
                "extra_risk_events": list(self._cycle_risk_events or []),
            }
            n.maybe_risk_alert(status, state)
            n.maybe_alert(status)
        except Exception as exc:
            log.error("owner notify failed: %s", exc)

    def _halt_flatten_step(self, state: Dict[str, Any], cycle: int,
                            equity: float, halt: Dict[str, Any]) -> List[Dict]:
        """Edge-triggered halt flatten (called once per run_cycle).

        When the kill switch or daily circuit breaker trips, liquidate every
        equity/crypto position instead of merely blocking new risk. Fires once
        per halt episode (state["halt_flattened"]); re-arms when the halt
        clears. Queues a page-worthy risk event for _maybe_notify.
        """
        if not (halt.get("halted") and self.cfg.flatten_on_halt
                and not state.get("halt_flattened")):
            if not halt.get("halted") and state.get("halt_flattened"):
                state.pop("halt_flattened", None)   # halt cleared — re-arm
            return []
        flattened, open_options = self._flatten_all_positions(
            state, cycle, equity, halt["reason"])
        state["halt_flattened"] = {
            "reason": halt["reason"], "cycle": cycle,
            "flattened": [d.get("symbol") for d in flattened],
            "open_options": open_options,
        }
        msg = (f"🔻 HALT FLATTEN — {halt['reason']}: liquidated "
               f"{len(flattened)} position(s)")
        if open_options:
            msg += (f"; {len(open_options)} option leg(s) NOT auto-closed "
                    f"({', '.join(o['symbol'] for o in open_options[:5])}) — "
                    f"manual close required")
        log.warning("%s", msg)
        self._cycle_risk_events.append(("flatten", msg))
        return flattened

    def _governor_cycle_gate(self, equity: float, state: Dict[str, Any]
                             ) -> tuple[float, bool, list]:
        """Once-per-cycle portfolio throttle for new-position budgets.

        Returns (scale, hard_blocked, reasons) where scale ∈ [0, 1] multiplies
        every strategy budget this cycle. Uses a representative full-size
        proposal (the per-position cap) so the factor reflects the room a new
        position actually has. Tracks the equity peak in state for drawdown.
        Fail-closed on bad inputs (scale 0, blocked True); neutral (1.0) when
        the governor is disabled.
        """
        if self.governor is None:
            return 1.0, False, []
        try:
            if not (math.isfinite(equity) and equity > 0):
                return 0.0, True, ["non-finite or non-positive equity"]
            peak = float(state.get("equity_peak") or equity)
            if equity > peak:
                peak = equity
                state["equity_peak"] = peak
            drawdown = (peak - equity) / peak if peak > 0 else 0.0
            gross = sum(gross_symbol_value(self.client, state, s)
                        for s in (state.get("positions") or {}))
            rep = equity * self.cfg.max_allocation_pct  # representative full-size new position
            verdict = self.governor.size(PortfolioRiskInput(
                equity=equity,
                proposed_notional=rep,
                raw_kelly_fraction=1.0,   # Kelly neutral — RiskEngine sizes
                gross_exposure=gross + rep,
                existing_position_value=0.0,
                realized_vol_annual=0.0,  # RiskEngine.vol_scalar already targets vol
                max_abs_correlation=0.0,  # no correlation matrix yet — neutral
                drawdown=drawdown,
                liquidity_cap_notional=None,
            ))
            scale = (verdict.final_notional / rep) if rep > 0 else 0.0
            scale = max(0.0, min(1.0, scale))
            reasons = [] if verdict.approved else [verdict.reason]
            if not verdict.approved:
                log.warning("GOVERNOR cycle gate: %s (dd=%.2f%%, gross=$%.0f)",
                            verdict.reason, drawdown * 100, gross)
            elif scale < 1.0:
                log.info("GOVERNOR throttle: budgets ×%.2f (%s, dd=%.2f%%)",
                         scale, verdict.reason, drawdown * 100)
            record_event(state, "governor_cycle_gate",
                         {"scale": round(scale, 4), "blocked": not verdict.approved,
                          "reason": verdict.reason, "drawdown": round(drawdown, 6),
                          "gross": round(gross, 2)})
            return scale, not verdict.approved, reasons
        except Exception as exc:  # fail-closed
            log.error("governor cycle gate failed: %s — blocking new risk", exc)
            return 0.0, True, [f"governor error: {exc}"]

    def run_cycle(self, state: Dict[str, Any], trade: bool = True) -> Dict[str, Any]:
        state["cycle"] = state.get("cycle", 0) + 1
        cycle = state["cycle"]
        self._cycle_risk_events = []   # drained by _maybe_notify at cycle end
        if hasattr(self.client, "begin_cycle"):
            self.client.begin_cycle()  # fresh quotes; pinned for this cycle
        # Record this cycle's prices as bars (passive; see utils/bar_recorder.py).
        if self.bars is not None:
            try:
                self.bars.record_many({sym: self.client.get_price(sym)
                                       for sym in self.cfg.tickers})
            except Exception as exc:      # history keeping never disturbs trading
                log.warning("bar recording skipped: %s", exc)
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
        # Capital-flow guard on the RETURN baseline (same principle as the daily
        # breaker): deposits, withdrawals and sleeve changes move equity without
        # any trading. If the desk is FLAT and has booked no realized P&L, a moved
        # equity cannot be performance — re-anchor, or the dashboard reports a
        # capital change as profit (a $10 → $50 sleeve read as "+400% return").
        try:
            flat = not (state.get("positions") or {})
            no_pnl = (abs(float(state.get("realized_pnl", 0.0) or 0.0)) < 1e-9
                      and abs(float(state.get("premium_collected", 0.0) or 0.0)) < 1e-9)
            base = float(state.get("equity_start") or 0.0)
            if flat and no_pnl and base > 0 and abs(equity - base) > 1e-9:
                log.info("return baseline re-anchored $%.2f → $%.2f (capital change, "
                         "no trading activity)", base, equity)
                state["equity_start"] = equity
        except Exception:
            pass
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

        # Broker reconciliation FIRST: never plan a cycle against a stale view of
        # what we own (see _reconcile_broker for why state alone is not enough).
        recon = self._reconcile_broker(state)
        recon["orders_resolved"] = []

        # Circuit breaker / kill switch — suspends NEW risk this cycle if tripped.
        halt = self._halt_check(state, equity)
        allow_new_risk = trade and not halt["halted"]
        if mode == "LIVE" and not reconciliation["reconciled"]:
            allow_new_risk = False
            reason = "broker position reconciliation failed"
            halt = {**halt, "halted": True,
                    "reason": f"{halt.get('reason')}; {reason}".strip("; ")}
            log.error("NEW RISK HALTED: %s", reason)

        if mode == "LIVE" and not recon["ok"]:
            allow_new_risk = False
            reason = "broker state synchronization degraded"
            halt = {**halt, "halted": True,
                    "reason": f"{halt.get('reason')}; {reason}".strip("; ")}
            log.error("NEW RISK HALTED: %s", reason)

        # Execution-cadence guard. Every protective rail (trailing stops, hard
        # floors, the daily breaker) only evaluates WHEN A CYCLE RUNS. Scheduled
        # runners throttle and skip, so cycles can be hours apart — and a position
        # opened into a multi-hour blind spot cannot be managed. When the gap runs
        # far beyond the configured cadence we keep EXITS flowing but refuse to
        # open NEW risk: better to miss a trade than to hold what we cannot watch.
        cadence = self._cadence_check(state)
        if cadence["degraded"] and allow_new_risk:
            log.warning("NEW RISK PAUSED — %s", cadence["reason"])
            allow_new_risk = False

        # Volatility targeting — realized portfolio vol above target scales every
        # new-position budget down ([0.5, 1.0]); fault-isolated, neutral on failure.
        try:
            vol_scale = self.risk.vol_scalar(
                [row.get("equity") for row in self.db.equity_history_regime(60)])
        except Exception as exc:
            log.warning("vol targeting skipped: %s", exc)
            vol_scale = 1.0

        # Portfolio-governor budget throttle — computed once per cycle from the
        # live book. Smoothly scales every new-position budget down as the
        # portfolio approaches its rails (drawdown throttle, gross-exposure
        # room, single-position room); the hard stops are enforced again per
        # intent in ExecutionTrader._governor_decision. Reduction-only:
        # gov_scale ∈ [0, 1]. Fault-isolated, neutral (1.0) on failure.
        gov_scale, gov_hard_block, gov_reasons = self._governor_cycle_gate(equity, state)
        if gov_hard_block:
            log.warning("GOVERNOR hard stop: %s — all new-risk budgets zeroed",
                        "; ".join(gov_reasons))

        bench = self.client.get_history(self.cfg.benchmark, 250)["closes"]

        # 1) Research Desk — council per ticker
        research: List[Dict[str, Any]] = []
        for sym in self.cfg.tickers:
            try:
                snap, verdict = self.research.research(sym, bench)
                research.append({"symbol": sym, "snap": snap, "verdict": verdict})
            except Exception as exc:
                log.error("research failed %s: %s", sym, exc)

        # 1d) Intel workforce — the 8-agent advisory-only analyst team
        # (intel/workforce/). Runs after the research block and reports
        # plain-language findings to the dashboard. Fault-isolated: a dead
        # data source makes that agent abstain; a dead module leaves an empty
        # list. Never emits orders, never touches risk caps or the arming chain.
        intel_findings: List[Dict[str, Any]] = []
        try:
            if getattr(self.cfg, "intel_workforce_enabled", True) \
                    and self.intel_desk is not None:
                intel_ctx = {
                    "client": self.client,
                    "db": self.db,
                    "state": state,
                    "cfg": self.cfg,
                    "tickers": list(self.cfg.tickers or []),
                    "research": research,
                    "reconciliation": recon,
                }
                intel_findings = [f.as_dict() for f in self.intel_desk.run(intel_ctx)]
        except Exception as exc:
            log.error("intel workforce failed: %s", exc)
            intel_findings = []

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
            hermes = self.hermes.review(research, state, feed=self.feed)
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
                # Score the intraday overlay against forward returns BEFORE it is
                # ever allowed to move a real order. shadow_read computes the tilt
                # whether or not the overlay is armed, so the evidence needed to
                # decide on arming accumulates without anything being risked to
                # produce it. Excluded from the LLM consensus (see
                # AutonomousLearningPipeline.consensus) — it is a quant estimator,
                # not an opinion, and that metric is mid-measurement.
                overlays["intraday"] = {
                    "per_symbol_adjust": {
                        row["symbol"]: self.intraday.shadow_read(
                            row["symbol"], row.get("direction", "")).tilt
                        for row in portfolio
                    },
                    "risk_multiplier": 1.0,
                    "telemetry": {"schema_valid": True, "fallback_used": False},
                }
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
                # Intraday confirmation: does the recent tape agree with the
                # direction this daily verdict already chose? Neutral (0.0) unless
                # the overlay is armed AND the desk has enough bars with a
                # measured range, so it contributes nothing until it has grounds to.
                intraday_read = self.intraday.read(sym, verdict.direction)
                intraday_tilt = intraday_read.tilt
                if hermes_tilt <= -1.0:      # data quarantine always wins outright
                    tilt = hermes_tilt
                else:                        # advisory layers stack, but stay bounded
                    tilt = max(-0.20, min(0.20, alt_tilt + board_tilt + hermes_tilt
                                          + intraday_tilt))
                conviction, risk_mult, budget = self.pm.effective(verdict, brain, equity, tilt)
                # Hermes strategy calibration: budget leans toward desks with a proven
                # realized edge (bounded 0.70–1.15; hard risk ceilings still apply).
                budget *= hermes.strategy_weights.get(strat, 1.0) * vol_scale * institutional_risk
                # Portfolio-governor throttle: smooth reduction-only scaling from
                # the once-per-cycle portfolio gate (0 on hard stop).
                budget *= gov_scale
                # Regime gate: the council's regime read is a real gate now —
                # stressed blocks new entries, bear/chop halve budgets and
                # restrict which desks may open risk. Exits always flow.
                regime_scale, regime_entries = self._regime_gate(verdict, strat)
                budget *= regime_scale
                ticker_allow_new_risk = allow_new_risk and regime_entries
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
                    # LiveStrategy protocol: single context value in, pure intents out.
                    intents = self.ladder.decide(StrategyContext(
                        symbol=sym, snap=snap, position=pos, council=verdict,
                        budget=budget, state=state,
                        get_price=self.client.get_price))
                if trade:
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conviction, ticker_allow_new_risk)
                    executed += done
                # log council + snapshot
                self.db.log_council(cycle, sym, verdict.conviction, verdict.direction,
                                    verdict.composite_score, verdict.risk_multiplier, verdict.metrics,
                                    snap.price)
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
                # Protective exits run FIRST and unconditionally: the feed can go
                # empty or 404, but held positions must still be risk-managed.
                m_intents = self.copy.manage(state, self.client.get_price)
                if m_intents:
                    done, deployed = self.execution.execute(
                        m_intents, state, cycle, equity, deployed,
                        max(self.cfg.min_council_conviction, 0.6), allow_new_risk)
                    executed += done
                    if done:
                        log.info("COPY desk protective exit: %d order(s)", len(done))
            except Exception as exc:
                log.error("copy-trading risk management failed: %s", exc)
            try:
                signals = self.copy.fetch_signals()
                if signals:
                    # Regime gate on copy ENTRIES: research each unique feed
                    # symbol once (reusing core research when it coincides) and
                    # mirror only symbols whose regime allows new entries.
                    # Protective exits (above) and feed-driven exits stay
                    # unconditional — the gate is entries-only.
                    syms = []
                    for s in signals:
                        sm = str(s.get("symbol") or "")
                        if sm and sm not in syms:
                            syms.append(sm)
                    sig_verdicts = {}
                    for sm in syms:
                        try:
                            hit = next((r for r in research if r["symbol"] == sm), None)
                            if hit is not None:
                                sig_verdicts[sm] = hit["verdict"]
                            else:
                                snap, verdict = self.research.research(sm, bench)
                                sig_verdicts[sm] = verdict
                                self.db.log_council(
                                    cycle, sm, verdict.conviction, verdict.direction,
                                    verdict.composite_score, verdict.risk_multiplier,
                                    verdict.metrics, snap.price)
                        except Exception as exc:
                            log.warning("copy desk research failed for %s: %s", sm, exc)
                    allowed_syms, scales = set(), []
                    for sm, ver in sig_verdicts.items():
                        scale, entries = self._regime_gate(ver, "copy")
                        if entries:
                            allowed_syms.add(sm)
                            scales.append(scale)
                    # Entries (buys) are regime-gated; feed-driven sells are
                    # exits and flow unconditionally.
                    gated = [s for s in signals
                             if s.get("side") != "buy"
                             or s.get("symbol") in allowed_syms]
                    blocked = sum(1 for s in signals
                                  if s.get("side") == "buy"
                                  and s.get("symbol") not in allowed_syms)
                    if blocked:
                        log.info("COPY desk: regime gate blocked %d signal(s)", blocked)
                    if gated:
                        # Conservative: the weakest allowed regime scales the
                        # whole mirror budget (reduction-only).
                        gate_scale = min(scales) if scales else 0.0
                        c_intents = self.copy.decide(gated, state,
                                                     equity * gate_scale,
                                                     self.client.get_price)
                        conv = max(self.cfg.min_council_conviction, 0.6)
                        done, deployed = self.execution.execute(
                            c_intents, state, cycle, equity, deployed, conv,
                            allow_new_risk)
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
                    # Council conviction instead of a hardcoded 0.70 — the desk
                    # already pays for the research; use it. Floored at the
                    # council minimum so the RiskEngine gate still sees a valid
                    # conviction, capped so a hot read cannot over-size.
                    conv = max(self.cfg.min_council_conviction,
                               min(0.95, float(getattr(verdict, "conviction", 0.0) or 0.0)))
                    rscale, rentries = self._regime_gate(verdict, "day")
                    budget = self.risk.position_budget(equity, conv, 1.0) \
                        * hermes.strategy_weights.get("daytrade", 1.0) * vol_scale * institutional_risk \
                        * gov_scale * rscale  # governor throttle (0 on hard stop) × regime
                    intents = self.dayts.decide(sym, snap, pos, budget, today)
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conv,
                                                            allow_new_risk and rentries)
                    executed += done
                    self.db.log_council(cycle, sym, verdict.conviction, verdict.direction,
                                        verdict.composite_score, verdict.risk_multiplier, verdict.metrics,
                                    snap.price)
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
            verdicts = {r["symbol"]: r["verdict"] for r in research}
            for pair in self.cfg.pairs:
                try:
                    if ":" not in pair:
                        continue
                    sym_a, sym_b = (p.strip() for p in pair.split(":", 1))
                    if sym_a in snaps:
                        snap_a, ver_a = snaps[sym_a], verdicts.get(sym_a)
                    else:
                        snap_a, ver_a = self.research.research(sym_a, bench)
                    if sym_b in snaps:
                        snap_b, ver_b = snaps[sym_b], verdicts.get(sym_b)
                    else:
                        snap_b, ver_b = self.research.research(sym_b, bench)
                    coint = engines.cointegration(snap_a.closes, snap_b.closes)
                    pos_a = state.get("positions", {}).get(sym_a)
                    pos_b = state.get("positions", {}).get(sym_b)
                    # Council conviction from the stronger leg instead of a
                    # hardcoded 0.70 (floored/capped like the day desk).
                    leg_conv = max(float(getattr(ver_a, "conviction", 0.0) or 0.0),
                                   float(getattr(ver_b, "conviction", 0.0) or 0.0))
                    conv = max(self.cfg.min_council_conviction, min(0.95, leg_conv))
                    # Regime gate per leg, conservative: the weaker regime wins
                    # and both legs must allow entries.
                    sa, ea = self._regime_gate(ver_a, "pairs")
                    sb, eb = self._regime_gate(ver_b, "pairs")
                    rscale, rentries = min(sa, sb), (ea and eb)
                    budget = self.risk.position_budget(equity, conv, 1.0) \
                        * hermes.strategy_weights.get("pairs", 1.0) * vol_scale * institutional_risk \
                        * gov_scale * rscale  # governor throttle (0 on hard stop) × regime
                    intents = self.pairs_desk.decide(sym_a, sym_b, snap_a.price, snap_b.price,
                                                     pos_a, pos_b, budget, coint)
                    done, deployed = self.execution.execute(intents, state, cycle, equity,
                                                            deployed, conv,
                                                            allow_new_risk and rentries)
                    executed += done
                    if done:
                        log.info("PAIRS desk %s/%s: %d order(s), z=%+.2f",
                                 sym_a, sym_b, len(done), coint.get("spread_z", 0.0))
                except Exception as exc:
                    log.error("pairs desk %s failed: %s", pair, exc)

        # 6e2) Promoted research desks — validated backtest strategies (S1–S18)
        # running as live desks via strategies/promoted.py. Double-gated
        # (PROMOTED_DESKS_ENABLED + PROMOTED_STRATEGIES); empty by default.
        # Promoted symbols are researched like core tickers so the council,
        # the regime gate, and every risk rail apply to them identically.
        # Symbols colliding with core tickers are skipped (no double-trading).
        if trade and self.promoted_adapters:
            core_syms = set(self.cfg.tickers or [])
            promoted_syms = [s for s in (self.cfg.promoted_symbols or [])
                             if s and s not in core_syms]
            if promoted_syms:
                for adapter in self.promoted_adapters:
                    for sym in promoted_syms:
                        try:
                            hit = next((r for r in research if r["symbol"] == sym), None)
                            if hit is not None:
                                snap, verdict = hit["snap"], hit["verdict"]
                            else:
                                snap, verdict = self.research.research(sym, bench)
                                self.db.log_council(
                                    cycle, sym, verdict.conviction, verdict.direction,
                                    verdict.composite_score, verdict.risk_multiplier,
                                    verdict.metrics, snap.price)
                            # Council conviction (floored/capped like day/pairs).
                            pconv = max(self.cfg.min_council_conviction,
                                        min(0.95, float(getattr(
                                            verdict, "conviction", 0.0) or 0.0)))
                            rscale, rentries = self._regime_gate(verdict, "promoted")
                            budget = self.risk.position_budget(
                                equity, pconv, 1.0) \
                                * hermes.strategy_weights.get("promoted", 1.0) \
                                * vol_scale * institutional_risk * gov_scale * rscale
                            intents = adapter.decide(StrategyContext(
                                symbol=sym, snap=snap,
                                position=state.get("positions", {}).get(sym),
                                council=verdict, budget=budget, state=state,
                                get_price=self.client.get_price,
                                extras={"allow_fractional": self.cfg.allow_fractional}))
                            done, deployed = self.execution.execute(
                                intents, state, cycle, equity, deployed,
                                pconv, allow_new_risk and rentries)
                            executed += done
                            if done:
                                log.info("PROMOTED %s %s: %d order(s)",
                                         adapter.strategy_id, sym, len(done))
                        except Exception as exc:
                            log.error("promoted desk %s %s failed: %s",
                                      adapter.strategy_id, sym, exc)

        # 6e) Catastrophic per-position hard stop — central backstop wiring up
        # RiskEngine.hard_stop_breached(). Exits only; flows even during halts.
        try:
            stopped = self._catastrophic_stop_sweep(state, cycle, equity)
            if stopped:
                executed += stopped
                log.warning("catastrophic stop sweep liquidated %d position(s)",
                            len(stopped))
        except Exception as exc:
            log.error("catastrophic stop sweep failed: %s", exc)

        # 6g) Halt flatten — a halt that leaves the book open protects nothing.
        # Edge-triggered via _halt_flatten_step (once per halt episode).
        try:
            flattened = self._halt_flatten_step(state, cycle, equity, halt)
            if flattened:
                executed += flattened
        except Exception as exc:
            log.error("halt flatten failed: %s", exc)

        # 7) Treasurer — equity curve
        acct = self.client.get_account()
        if self.cfg.trading_capital and self.cfg.trading_capital > 0:
            eq_now, cash_now = self._sleeve(state)
        else:
            eq_now, cash_now = acct["equity"], acct["cash"]
        self.db.log_equity(cycle, eq_now, cash_now, self._position_value(state),
                           state.get("realized_pnl", 0.0), state.get("premium_collected", 0.0), mode)

        # 8) Owner alerting — risk pages go out even when nothing traded.
        # Wires up Notifier.maybe_risk_alert (breaker/kill-switch trips, broker
        # disconnects, quarantine — de-duplicated per reason per day) and
        # Notifier.maybe_alert. Silent without configured channels.
        try:
            self._maybe_notify(state, cycle, halt, recon, hermes, brain,
                               executed, eq_now)
        except Exception as exc:
            log.error("owner notify step failed: %s", exc)

        return {"cycle": cycle, "equity": eq_now, "cash": cash_now,
                "research": research, "brain": brain, "executed": executed,
                "ai_shadow": learning, "intel_findings": intel_findings,
                "deployed": self._position_value(state), "halt": halt,
                "reconciliation": recon,
                "execution_reconciliation": reconciliation,
                "institutional_intelligence": institutional_intelligence,
                "hermes": hermes, "board": board, "vol_scale": round(vol_scale, 3),
                "cadence": cadence}
