"""Multi-tenant cron entry point.

For every active desk: decrypt its keys, build a per-desk Config, run ONE engine
cycle (reusing the exact single-tenant domain code), and persist state + a
dashboard snapshot + the equity point + trades back to Supabase Postgres.

Run on a worker host (Railway/Render/Fly) on a schedule:
    python -m worker.run            # one pass over all active desks
    python -m worker.run --desk <uuid>   # a single desk (debug)

Safety: mode defaults to 'sim'. 'paper' needs Alpaca keys. 'live' additionally
requires the desk's explicit live_ack=true AND keys — otherwise it is refused
and the desk falls back to 'sim' for that run (logged, never silently traded).
"""
from __future__ import annotations

import argparse
import os
from typing import Any, Dict

from config import load_config
from database import Database
from utils.broker import get_broker
from utils.logger import get_logger
from utils.state_store import default_state
from workforce import Firm
from workforce.reporter import build_status

from worker import db_pg
from worker.crypto import decrypt

log = get_logger("worker")

# env keys we own per desk — cleared between desks so one tenant never leaks into another
_MANAGED_ENV = [
    "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_PAPER", "TICKERS", "BENCHMARK",
    "MAX_ALLOCATION_PCT", "MAX_TOTAL_DEPLOYED_PCT", "MIN_COUNCIL_CONVICTION",
    "AI_BRAIN_ENABLED", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
    "VOICE_API_KEY", "VOICE_ALERTS", "OWNER_PHONE", "FIRM_NAME",
]


def _clear_env() -> None:
    for k in _MANAGED_ENV:
        os.environ.pop(k, None)


def _resolve_mode(desk: Dict[str, Any], creds: Dict[str, str]) -> str:
    """Decide the effective mode for this run, enforcing the live opt-in gate."""
    want = (desk.get("mode") or "sim").lower()
    has_alpaca = bool(creds.get("ALPACA_API_KEY") and creds.get("ALPACA_SECRET_KEY"))
    if want == "live":
        if not desk.get("live_ack"):
            log.warning("desk %s requested live without live_ack → falling back to sim", desk["id"])
            return "sim"
        if not has_alpaca:
            log.warning("desk %s live but no Alpaca keys → sim", desk["id"])
            return "sim"
        return "live"
    if want == "paper":
        return "paper" if has_alpaca else "sim"
    return "sim"


def _apply_env(desk: Dict[str, Any], creds: Dict[str, str], mode: str) -> None:
    _clear_env()
    os.environ["TICKERS"] = ",".join(desk.get("tickers") or ["AAPL", "MSFT", "SPY"])
    os.environ["BENCHMARK"] = desk.get("benchmark") or "SPY"
    os.environ["MAX_ALLOCATION_PCT"] = str(desk.get("max_allocation_pct", 0.10))
    os.environ["MAX_TOTAL_DEPLOYED_PCT"] = str(desk.get("max_total_deployed_pct", 0.60))
    os.environ["MIN_COUNCIL_CONVICTION"] = str(desk.get("min_conviction", 0.55))
    os.environ["FIRM_NAME"] = desk.get("name") or "SAHJONY CAPITAL LLC"
    # LLM brain
    if desk.get("ai_brain_enabled") and creds.get("ANTHROPIC_API_KEY"):
        os.environ["AI_BRAIN_ENABLED"] = "true"
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "VOICE_API_KEY", "OWNER_PHONE"):
        if creds.get(k):
            os.environ[k] = creds[k]
    # broker
    if mode in ("paper", "live"):
        os.environ["ALPACA_API_KEY"] = creds.get("ALPACA_API_KEY", "")
        os.environ["ALPACA_SECRET_KEY"] = creds.get("ALPACA_SECRET_KEY", "")
        os.environ["ALPACA_PAPER"] = "false" if mode == "live" else "true"


def run_desk(conn, desk: Dict[str, Any]) -> None:
    desk_id = desk["id"]
    enc = db_pg.get_credentials(conn, desk_id)
    creds: Dict[str, str] = {}
    for name, token in enc.items():
        try:
            creds[name] = decrypt(token)
        except Exception as exc:  # a bad/rotated key never sinks the desk
            log.error("desk %s: failed to decrypt %s: %s", desk_id, name, exc)

    mode = _resolve_mode(desk, creds)
    _apply_env(desk, creds, mode)
    cfg = load_config()

    state = desk.get("state") or default_state()
    if not isinstance(state, dict) or not state:
        state = default_state()

    db = Database(":memory:")
    try:
        client = get_broker(cfg)
        firm = Firm(cfg, client, db)
        trade = (not client.online) or client.is_market_open()
        result = firm.run_cycle(state, trade=trade)
        status = build_status(firm, cfg, state, result)

        db_pg.append_equity(conn, desk_id, {
            "cycle": result["cycle"], "equity": result["equity"], "cash": result["cash"],
            "deployed": result["deployed"], "realized_pnl": state.get("realized_pnl", 0.0),
            "premium": state.get("premium_collected", 0.0), "mode": cfg.mode,
        })
        db_pg.insert_trades(conn, desk_id, [dict(t, cycle=result["cycle"]) for t in db.recent_trades(50)])
        # replace single-cycle history with the tenant's full Postgres history
        status["equity_curve"] = db_pg.equity_curve(conn, desk_id)
        status["recent_trades"] = db_pg.recent_trades(conn, desk_id)
        db_pg.save_desk_result(conn, desk_id, state, status, cfg.mode)
        conn.commit()
        log.info("desk %s ok — cycle %s mode=%s equity=%.2f",
                 desk_id, result["cycle"], cfg.mode, result["equity"])
    except Exception as exc:
        conn.rollback()
        log.error("desk %s failed: %s", desk_id, exc)
    finally:
        db.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SAHJONY multi-tenant worker")
    ap.add_argument("--desk", help="run a single desk by id (debug)")
    args = ap.parse_args(argv)

    conn = db_pg.connect()
    try:
        desks = db_pg.list_active_desks(conn)
        if args.desk:
            desks = [d for d in desks if str(d["id"]) == args.desk]
        log.info("worker pass: %d desk(s)", len(desks))
        for desk in desks:
            run_desk(conn, desk)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
