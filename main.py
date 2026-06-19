#!/usr/bin/env python
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from config import settings
from utils.alpaca_client import AlpacaClient
from strategies import WheelStrategy, TrailingLadderStrategy

# ----------------------------------------------------------------------
# Logging configuration
# ----------------------------------------------------------------------
log_level = getattr(logging, settings.log_level, logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s %(levelname)s %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger('ai-trading-bot')

# ----------------------------------------------------------------------
# Helper: load / persist state
# ----------------------------------------------------------------------
STATE_PATH = Path(__file__).parent / 'state.json'

def load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            with open(STATE_PATH, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            log.error('Corrupt state.json – resetting: %s', exc)
    return {}

def save_state(state: dict) -> None:
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

# ----------------------------------------------------------------------
# Core execution loop
# ----------------------------------------------------------------------
def run_bot(dry_run: bool = False) -> None:
    log.info('=== Bot start (%s) ===', datetime.utcnow().isoformat())
    state = load_state()

    client = AlpacaClient()

    # Instantiate strategies (configurable later)
    wheel = WheelStrategy(client, ticker='AAPL', allocation=0.10)
    ladder = TrailingLadderStrategy(client, ticker='AAPL', allocation=0.20)

    # Run strategies sequentially (could be parallelised later)
    state = wheel.run(state)
    state = ladder.run(state)

    if dry_run:
        log.info('Dry‑run mode – state not persisted')
    else:
        save_state(state)
        log.info('State persisted to %s', STATE_PATH)

    # Simple console dashboard
    recent_wheel = state.get('wheel', [])[-1:] if state.get('wheel') else []
    recent_ladder = state.get('ladder', [])[-1:] if state.get('ladder') else []
    print('\n=== Bot Dashboard ===')
    print(f'Timestamp: {datetime.utcnow().isoformat()} UTC')
    account = client.get_account()
    print(f"Equity (from Alpaca): ${account.get('equity') if account else 'N/A'}")
    print(f"Wheel cycles executed: {len(state.get('wheel', []))}")
    print(f"Ladder cycles executed: {len(state.get('ladder', []))}")
    if recent_wheel:
        print(' Last wheel action:', recent_wheel[0])
    if recent_ladder:
        print(' Last ladder action:', recent_ladder[0])
    print('=====================\n')

# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Autonomous Alpaca trading bot')
    parser.add_argument('--dry-run', action='store_true', help='Execute strategies but do not write state.json')
    args = parser.parse_args()
    try:
        run_bot(dry_run=args.dry_run)
    except Exception as exc:
        log.exception('Unhandled exception in bot: %s', exc)
        sys.exit(1)
