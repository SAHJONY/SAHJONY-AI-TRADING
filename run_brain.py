"""Read-only orchestration entry point for the SAHJONY analysis brain.

This module deliberately does not import strategies or the execution router.  The
broker passed to the analytical pipeline is narrowed to a read-only facade, so an
order API is not merely disabled: it is unreachable from this runner.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from config import Config, load_config
from intelligence.advisors import AdvisoryBoard
from intelligence.agents import Council, MarketSnapshot
from intelligence.ai_brain import AIBrain
from intelligence.historical_data import (
    HistoricalDataError, HistoricalDataProvider, configured_historical_provider,
    validate_historical_bars,
)
from observability.reconciliation import reconcile_positions, unavailable_reconciliation
from risk.risk_engine import RiskEngine
from utils.broker import get_broker
from utils.state_store import load_state
from workforce.reporter import write_status

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("brain")

STATUS_PATH = Path(__file__).resolve().parent / "public" / "brain_status.json"


class ReadOnlyBroker:
    """Capability-limited broker view; intentionally contains no order methods."""

    def __init__(self, broker: Any):
        self._broker = broker

    @property
    def online(self) -> bool:
        return bool(self._broker.online)

    @property
    def mode(self) -> str:
        return str(getattr(self._broker, "mode", "unknown"))

    @property
    def identity_verified(self) -> bool:
        return bool(getattr(self._broker, "identity_verified", False))

    @property
    def trading_armed(self) -> bool:
        return bool(getattr(self._broker, "trading_armed", False))

    @property
    def execution_authority(self) -> bool:
        return bool(getattr(self._broker, "execution_authority", False))

    def get_account(self):
        return self._broker.get_account()

    def get_broker_positions(self):
        return self._broker.get_broker_positions()

    def get_quote_snapshot(self, symbol: str) -> dict[str, Any]:
        getter = getattr(self._broker, "get_quote_snapshot", None)
        if callable(getter):
            return dict(getter(symbol) or {})
        return {"price": self._broker.get_price(symbol),
                "retrieved_at": datetime.now(timezone.utc).isoformat()}


def _timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float, np.integer, np.floating)):
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000.0
            return datetime.fromtimestamp(number, tz=timezone.utc)
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _freshness(quote: dict[str, Any], now: datetime, max_age: int) -> dict[str, Any]:
    source = (quote.get("exchange_timestamp") or quote.get("feed_timestamp")
              or quote.get("retrieved_at"))
    observed = _timestamp(source)
    age = max(0.0, (now - observed).total_seconds()) if observed else None
    fresh = observed is not None and age is not None and age <= max_age
    return {"fresh": fresh, "age_seconds": round(age, 3) if age is not None else None,
            "max_age_seconds": max_age, "source_timestamp": source}


def _safe_number(value: Any) -> float:
    number = float(value or 0.0)
    return number if math.isfinite(number) else 0.0


def _agent_output(verdict: Any) -> dict[str, Any]:
    return {"name": verdict.name, "persona": verdict.persona,
            "score": verdict.score, "confidence": verdict.confidence,
            "rationale": verdict.rationale, "metrics": verdict.metrics}


def run_analysis(cfg: Config, broker: Any, *, state: dict[str, Any] | None = None,
                 now: datetime | None = None, status_path: Path | str = STATUS_PATH,
                 historical_provider: HistoricalDataProvider | None = None) -> dict[str, Any]:
    """Run one analysis cycle and persist a secret-free status document."""
    client = ReadOnlyBroker(broker)
    now = now or datetime.now(timezone.utc)
    max_age = max(1, int(os.getenv("BRAIN_MAX_QUOTE_AGE_SECONDS", "300")))
    blockers: list[str] = []

    if client.trading_armed:
        blockers.append("trading_armed must be false")
    if client.execution_authority:
        blockers.append("execution_authority must be false")
    is_mcp = cfg.broker in {"robinhood_mcp", "robinhood_agentic", "rh_mcp"}
    if is_mcp and not client.online:
        blockers.append("robinhood_mcp requires authenticated live-data")
    if is_mcp and not client.identity_verified:
        blockers.append("robinhood_mcp identity mismatch")
    if is_mcp and client.mode != "live-data":
        blockers.append("robinhood_mcp is not in read-only live-data mode")

    account: dict[str, Any] = {}
    broker_positions: dict[str, Any] = {}
    try:
        account = dict(client.get_account() or {})
        broker_positions = dict(client.get_broker_positions() or {})
    except Exception as exc:
        blockers.append(f"broker account data unavailable: {type(exc).__name__}")

    try:
        reconciliation = reconcile_positions(
            (state if state is not None else load_state()).get("positions", {}), broker_positions
        )
    except Exception as exc:
        reconciliation = unavailable_reconciliation(type(exc).__name__)
    if not reconciliation.get("reconciled"):
        blockers.append("positions reconciliation unresolved")

    symbols = list(dict.fromkeys([*cfg.tickers, cfg.benchmark]))
    lookback_days = max(1, int(os.getenv("HISTORICAL_LOOKBACK_DAYS", "365")))
    min_bars = max(1, int(os.getenv("HISTORICAL_MIN_BARS", "200")))
    max_history_age = max(0.0, float(os.getenv("HISTORICAL_MAX_STALENESS_HOURS", "72")))
    market: dict[str, tuple[MarketSnapshot, Any, dict[str, Any]]] = {}
    histories: dict[str, dict[str, Any]] = {}
    quotes: dict[str, dict[str, Any]] = {}
    provider = historical_provider
    if provider is None:
        try:
            provider = configured_historical_provider()
        except HistoricalDataError as exc:
            blockers.append(f"historical data unavailable: {exc}")
    for symbol in symbols:
        try:
            if provider is None:
                raise HistoricalDataError("provider unavailable")
            bars = validate_historical_bars(
                provider.get_equity_bars(symbol, lookback_days), symbol,
                min_bars=min_bars, max_staleness_hours=max_history_age, now=now,
            )
            histories[symbol] = {
                "symbol": bars.symbol, "closes": bars.closes, "volumes": bars.volumes,
                "timestamps": bars.timestamps, "retrieved_at": bars.retrieved_at,
                "feed_timestamp": bars.feed_timestamp,
                "exchange_timestamp": bars.exchange_timestamp, "provider": bars.provider,
            }
        except Exception as exc:
            blockers.append(f"{symbol}: invalid history ({type(exc).__name__}: {exc})")
        try:
            quote = client.get_quote_snapshot(symbol)
            price = _safe_number(quote.get("price"))
            if price <= 0:
                raise ValueError("missing quote")
            quotes[symbol] = {**quote, "price": price}
        except Exception as exc:
            blockers.append(f"{symbol}: missing quote ({type(exc).__name__})")

    bench = np.asarray(histories.get(cfg.benchmark, {}).get("closes", []), dtype=float)
    quote_freshness = {
        symbol: (_freshness(quotes[symbol], now, max_age) if symbol in quotes else
                 {"fresh": False, "age_seconds": None, "max_age_seconds": max_age,
                  "source_timestamp": None})
        for symbol in symbols
    }
    for symbol, freshness in quote_freshness.items():
        if symbol in quotes and not freshness["fresh"]:
            blockers.append(f"{symbol}: stale quote")
    council, board = Council(), AdvisoryBoard(cfg)
    research: list[dict[str, Any]] = []
    for symbol in cfg.tickers:
        if symbol not in histories or symbol not in quotes:
            continue
        hist, quote = histories[symbol], quotes[symbol]
        freshness = quote_freshness[symbol]
        closes = np.asarray(hist.get("closes", []), dtype=float)
        volumes = np.asarray(hist.get("volumes", []), dtype=float)
        if closes.size == 0 or not np.all(np.isfinite(closes)):
            blockers.append(f"{symbol}: invalid market history")
            continue
        snap = MarketSnapshot(
            symbol, quote["price"], closes, volumes, bench,
            bar_timestamps=np.asarray(hist.get("timestamps", []), dtype=object),
            retrieved_at=hist.get("retrieved_at"), feed_timestamp=hist.get("feed_timestamp"),
            exchange_timestamp=hist.get("exchange_timestamp"),
        )
        verdict = council.deliberate(snap)
        research.append({"symbol": symbol, "snap": snap, "verdict": verdict})
        market[symbol] = (snap, verdict, freshness)

    board_outputs = board.evaluate(research)
    portfolio = [{"symbol": row["symbol"], "price": row["snap"].price,
                  "conviction": row["verdict"].conviction,
                  "direction": row["verdict"].direction,
                  "composite": row["verdict"].composite_score,
                  "alpha": row["verdict"].metrics.get("alpha", 0.0),
                  "beta": row["verdict"].metrics.get("beta", 1.0),
                  "vol": row["verdict"].metrics.get("vol", 0.0)} for row in research]
    brain = AIBrain(cfg).advise(portfolio)

    equity = _safe_number(account.get("equity"))
    buying_power = _safe_number(account.get("buying_power"))
    funding_ready = equity > 0 and buying_power > 0
    if not funding_ready:
        blockers.append("account funding unavailable")
    data_ready = bool(client.online and len(market) == len(cfg.tickers)
                      and all(symbol in histories and symbol in quotes for symbol in symbols)
                      and all(x["fresh"] for x in quote_freshness.values())
                      and (not is_mcp or client.identity_verified))
    if not data_ready:
        blockers.append("market data not ready")

    deployed = sum(abs(_safe_number(row.get("market_value"))) for row in broker_positions.values())
    risk = RiskEngine(cfg)
    global_blockers = list(dict.fromkeys(blockers))
    decisions = []
    for symbol in cfg.tickers:
        row = market.get(symbol)
        if row is None:
            decisions.append({"symbol": symbol, "action": "OBSERVE_ONLY", "eligible": False,
                              "blockers": ["analysis unavailable"]})
            continue
        _, verdict, freshness = row
        board_verdict = board_outputs.get(symbol)
        adjustment = brain.adjust_for(symbol) + (board_verdict.tilt if board_verdict else 0.0)
        conviction = max(0.0, min(1.0, verdict.conviction + adjustment))
        risk_multiplier = max(0.1, min(1.0, verdict.risk_multiplier * brain.global_risk_multiplier))
        budget = risk.position_budget(equity, conviction, risk_multiplier)
        gate = risk.approve(equity, deployed, budget, conviction, symbol)
        local_blockers = list(global_blockers)
        if not gate.approved:
            local_blockers.append(gate.reason)
        decisions.append({
            "symbol": symbol, "action": "OBSERVE_ONLY", "eligible": not local_blockers,
            "direction": verdict.direction, "conviction": conviction,
            "risk_multiplier": risk_multiplier, "analysis_budget": budget,
            "quote_freshness": freshness,
            "model_outputs": {"council": [_agent_output(v) for v in verdict.verdicts],
                              "council_composite": verdict.composite_score,
                              "advisory_board": asdict(board_verdict) if board_verdict else None,
                              "ai_adjustment": brain.adjust_for(symbol)},
            "blockers": list(dict.fromkeys(local_blockers)),
        })

    public_reconciliation = {
        "status": reconciliation.get("status", "unavailable"),
        "reconciled": bool(reconciliation.get("reconciled")),
        "execution_blocked": True,
        "observed_at": reconciliation.get("observed_at"),
        "internal_position_count": reconciliation.get("internal_position_count", 0),
        "broker_position_count": reconciliation.get("broker_position_count", 0),
        "difference_count": len(reconciliation.get("differences", [])),
        "error": reconciliation.get("error"),
    }
    status = {
        "generated_at": now.isoformat(), "mode": "ANALYSIS_ONLY", "broker": cfg.broker,
        "trading_armed": False, "execution_authority": False,
        "data_ready": data_ready, "funding_ready": funding_ready,
        "positions_reconciled": bool(reconciliation.get("reconciled")),
        "reconciliation": public_reconciliation, "blockers": global_blockers,
        "account": {"equity": equity, "cash": _safe_number(account.get("cash")),
                    "buying_power": buying_power},
        "ai_advisory": {"used": brain.used, "posture": brain.posture,
                        "global_risk_multiplier": brain.global_risk_multiplier,
                        "commentary": brain.commentary, "model": brain.brain_model},
        "quote_freshness": quote_freshness, "decisions": decisions, "orders": [],
    }
    write_status(status, str(status_path))
    return status


def main() -> int:
    cfg = load_config()
    status = run_analysis(cfg, get_broker(cfg))
    log.info("Brain analysis complete: data_ready=%s decisions=%d blockers=%d",
             status["data_ready"], len(status["decisions"]), len(status["blockers"]))
    return 0 if not status["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
