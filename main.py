"""Main execution entry point for SAHJONY CAPITAL LLC autonomous trading bot.
Runs configured strategies, updates persistent state, and prints a concise console dashboard.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import MAX_CAPITAL_ALLOCATION
from utils.alpaca_client import get_client
from strategies.wheel_strategy import execute_wheel
from strategies.trailing_ladder import execute_ladder

# Configure logger (also writes to logs/bot.log via utils logger)
logger = logging.getLogger("main")
handler = logging.FileHandler("logs/bot.log")
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"

def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    else:
        return {"last_run": None, "positions": {}, "cash": 0, "equity": 0, "metrics": {"pnl": 0, "trades_executed": 0}}

def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def dashboard(state):
    print("=== SAHJONY CAPITAL LLC Trading Bot Dashboard ===")
    print(f"Last run   : {state.get('last_run')}")
    print(f"Cash       : ${state.get('cash',0):,.2f}")
    print(f"Equity     : ${state.get('equity',0):,.2f}")
    print(f"PnL        : ${state.get('metrics',{}).get('pnl',0):,.2f}")
    print(f"Trades exec: {state.get('metrics',{}).get('trades_executed',0)}")
    print("Positions  :")
    for sym, pos in state.get('positions', {}).items():
        print(f"  {sym}: {pos}")

def main():
    logger.info("Bot start")
    state = load_state()
    client = get_client()
    account = client.get_account()
    cash = float(account.get("cash", 0))
    buying_power = float(account.get("buying_power", 0))
    alloc = buying_power * MAX_CAPITAL_ALLOCATION
    logger.info("Account cash $%s, buying power $%s, alloc $%s", cash, buying_power, alloc)

    # Example watchlist – could be external config
    symbols = ["AAPL", "MSFT", "TSLA"]
    for sym in symbols:
        wheel_res = execute_wheel(sym, cash, max_allocation=0.05)
        logger.info("Wheel result for %s: %s", sym, wheel_res)
        ladder_res = execute_ladder(sym, cash, entry_price=100)  # placeholder price
        logger.info("Ladder result for %s: %s", sym, ladder_res)
        # Simplified counters
        state.setdefault('metrics', {})['trades_executed'] = state['metrics'].get('trades_executed',0) + len(wheel_res.get('actions',[])) + len(ladder_res.get('actions',[]))

    state['last_run'] = datetime.utcnow().isoformat() + "Z"
    save_state(state)
    dashboard(state)
    logger.info("Bot complete")

if __name__ == "__main__":
    main()
