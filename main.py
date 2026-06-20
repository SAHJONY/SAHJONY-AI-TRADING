"""SAHJONY CAPITAL LLC — autonomous trading desk runtime.

Loads persistent state, runs the agentic workforce for one or more cycles,
persists state + the dashboard snapshot, and prints a health board. Designed to
be driven by cron/launchd at `--once` per tick during market hours; `--cycles N`
walks the offline simulator for a verifiable dry run; `--loop` runs an internal
loop.

Examples:
  python main.py --preflight          # read-only readiness check (no orders)
  python main.py --once               # one cycle (cron entry point)
  python main.py --cycles 12          # dry-run: 12 sim cycles, walks the market
  python main.py --loop               # internal loop every CYCLE_MINUTES
  python main.py --once --force       # trade even if the market clock says closed
"""
from __future__ import annotations

import argparse
import time

from config import HARD_MAX_ALLOCATION_PCT, HARD_MAX_TOTAL_DEPLOYED_PCT, load_config
from database import Database
from utils.broker import get_broker
from utils.logger import get_logger
from utils.state_store import load_state, save_state
from workforce import Firm
from paths import halt_path, status_path
from workforce.reporter import build_status, console_board, write_investor_views, write_status

log = get_logger("main")


def preflight(cfg, client) -> int:
    """Read-only readiness report — places NO orders. Returns 0 when ready.

    Run this before adding funds / arming live: it confirms the broker connects,
    the account is reachable (and funded, for live), market data flows, and shows
    exactly which mode and risk caps are active."""
    ok = True
    mode = getattr(client, "mode", cfg.mode)
    bar = "=" * 64
    print(bar)
    print(f"  SAHJONY PREFLIGHT — broker={cfg.broker} mode={mode}")
    print(bar)

    # connection
    if mode == "offline-sim":
        print(f"  • {cfg.broker}: OFFLINE-SIM (no real orders). Add credentials/connection "
              f"for paper/live.")
        if cfg.has_credentials or cfg.broker != "alpaca":
            print("  ✗ credentials/connection configured but broker did not connect (see logs).")
            ok = False
    else:
        print(f"  ✓ Connected to {cfg.broker} ({mode}).")

    # account
    acct = client.get_account()
    print(f"  Equity ${acct['equity']:,.2f} | Cash ${acct['cash']:,.2f} | "
          f"Buying power ${acct['buying_power']:,.2f}")
    if mode == "LIVE" and acct["equity"] <= 0:
        print("  ✗ LIVE account shows $0 equity — fund the account first.")
        ok = False

    # market clock + data feed
    try:
        print(f"  Market open: {client.is_market_open()}")
    except Exception:
        pass
    for sym in cfg.tickers:
        px = client.get_price(sym)
        if px and px > 0:
            print(f"  ✓ data {sym}: ${px:,.2f}")
        else:
            print(f"  ✗ data {sym}: no price")
            ok = False

    # risk envelope
    print(f"  Caps: per-position {cfg.max_allocation_pct:.0%} (hard {HARD_MAX_ALLOCATION_PCT:.0%}) | "
          f"total-deployed {cfg.max_total_deployed_pct:.0%} (hard {HARD_MAX_TOTAL_DEPLOYED_PCT:.0%}) | "
          f"min conviction {cfg.min_council_conviction:.0%}")
    print(f"  Daily circuit breaker: halt new risk if down {cfg.max_daily_drawdown_pct:.0%} in a day")
    import os as _os
    if cfg.trading_halt or _os.path.exists(halt_path()):
        print("  ⛔ KILL SWITCH ACTIVE — new risk is suspended (TRADING_HALT / HALT file).")

    # live arming status
    if mode == "LIVE":
        if cfg.live_trading_ack:
            print("  ⚠ LIVE ARMED (LIVE_TRADING_ACK set) — real orders WILL be placed when you run.")
        else:
            print("  • LIVE venue connected but NOT armed — set LIVE_TRADING_ACK to trade real money.")

    print(bar)
    print("  READY ✓ — safe to run." if ok else "  NOT READY ✗ — resolve the ✗ items above.")
    print(bar)
    return 0 if ok else 1


def confirm_live(cfg, client) -> bool:
    """Gatekeeper for REAL-MONEY trading. Live orders are refused unless the
    operator has deliberately armed them (keys + ALPACA_PAPER=false + an explicit
    LIVE_TRADING_ACK). Returns False to abort, True to proceed (armed)."""
    if not cfg.live_trading_ack:
        log.error("LIVE venue connected but LIVE_TRADING_ACK is not set.")
        log.error("Refusing to place REAL-MONEY orders.")
        log.error('To deliberately enable live trading, set '
                  'LIVE_TRADING_ACK="I_UNDERSTAND_REAL_MONEY" in your .env —')
        log.error("or connect a paper venue instead.")
        return False
    acct = client.get_account()
    bar = "=" * 64
    print("\n".join([
        bar,
        " ⚠  LIVE REAL-MONEY TRADING ARMED — orders will use real funds",
        bar,
        f"  Broker equity          : ${acct.get('equity', 0):,.2f}",
        f"  Per-position cap        : {cfg.max_allocation_pct:.0%} "
        f"(hard ceiling {HARD_MAX_ALLOCATION_PCT:.0%})",
        f"  Total-deployed cap      : {cfg.max_total_deployed_pct:.0%} "
        f"(hard ceiling {HARD_MAX_TOTAL_DEPLOYED_PCT:.0%})",
        f"  Min conviction to trade : {cfg.min_council_conviction:.0%}",
        "  Ctrl-C within 5s to abort.",
        bar,
    ]))
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        log.info("Live trading aborted by operator.")
        return False
    return True


def run_once(firm: Firm, state, force: bool) -> dict:
    market_open = (not firm.client.online) or firm.client.is_market_open()
    trade = market_open or force
    if not trade:
        log.info("Market closed — research/report only (use --force to override).")
    result = firm.run_cycle(state, trade=trade)
    status = build_status(firm, firm.cfg, state, result)
    write_status(status, status_path())
    shared = write_investor_views(firm.db, status)  # token-keyed read-only investor snapshots
    if shared:
        log.info("Refreshed %d investor share view(s).", shared)
    save_state(state)
    alert = firm.notifier.maybe_alert(status)
    if alert:
        log.info("Voice alert: %s", alert)
    print(console_board(status))
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SAHJONY CAPITAL LLC trading desk")
    ap.add_argument("--once", action="store_true", help="run a single cycle (default)")
    ap.add_argument("--cycles", type=int, default=0, help="run N cycles (advances the sim each cycle)")
    ap.add_argument("--loop", action="store_true", help="loop every CYCLE_MINUTES")
    ap.add_argument("--force", action="store_true", help="trade even if market clock says closed")
    ap.add_argument("--preflight", action="store_true",
                    help="read-only readiness check (connection/funding/data); places NO orders")
    args = ap.parse_args(argv)

    cfg = load_config()
    log.info("Booting %s — mode=%s, tickers=%s", cfg.firm_name, cfg.mode, ",".join(cfg.tickers))
    db = Database()
    client = get_broker(cfg)
    firm = Firm(cfg, client, db)
    state = load_state()

    if args.preflight:
        rc = preflight(cfg, client)
        db.close()
        return rc

    if getattr(client, "mode", cfg.mode) == "LIVE" and not confirm_live(cfg, client):
        db.close()
        return 2

    try:
        if args.cycles and args.cycles > 0:
            for i in range(args.cycles):
                run_once(firm, state, force=True)
                client.advance_sim(1)  # walk the offline simulator
            return 0
        if args.loop:
            log.info("Entering loop (every %d min). Ctrl-C to stop.", cfg.cycle_minutes)
            while True:
                run_once(firm, state, force=args.force)
                client.advance_sim(1)
                time.sleep(cfg.cycle_minutes * 60)
        run_once(firm, state, force=args.force)  # default: one cycle
        return 0
    except KeyboardInterrupt:
        log.info("Stopped by user.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
