"""SAHJONY CAPITAL LLC — autonomous trading desk runtime.

Loads persistent state, runs the agentic workforce for one or more cycles,
persists state + the dashboard snapshot, and prints a health board. Designed to
be driven by cron/launchd at `--once` per tick during market hours; `--cycles N`
walks the offline simulator for a verifiable dry run; `--loop` runs an internal
loop.

Examples:
  python main.py --once               # one cycle (cron entry point)
  python main.py --cycles 12          # dry-run: 12 sim cycles, walks the market
  python main.py --loop               # internal loop every CYCLE_MINUTES
  python main.py --once --force       # trade even if the market clock says closed
"""
from __future__ import annotations

import argparse
import time

from config import load_config
from database import Database
from utils.alpaca_client import AlpacaClient
from utils.logger import get_logger
from utils.state_store import load_state, save_state
from workforce import Firm
from workforce.reporter import build_status, console_board, write_status
from workforce.workforce import STATUS_PATH

log = get_logger("main")


def run_once(firm: Firm, state, force: bool) -> dict:
    market_open = (not firm.client.online) or firm.client.is_market_open()
    trade = market_open or force
    if not trade:
        log.info("Market closed — research/report only (use --force to override).")
    result = firm.run_cycle(state, trade=trade)
    status = build_status(firm, firm.cfg, state, result)
    write_status(status, STATUS_PATH)
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
    args = ap.parse_args(argv)

    cfg = load_config()
    log.info("Booting %s — mode=%s, tickers=%s", cfg.firm_name, cfg.mode, ",".join(cfg.tickers))
    db = Database()
    client = AlpacaClient(cfg)
    firm = Firm(cfg, client, db)
    state = load_state()

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
