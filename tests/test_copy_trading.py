"""Copy-trading engine verification — no pytest, offline, no network.

    python -m tests.test_copy_trading

Asserts the engine normalizes mixed signal formats, turns a BUY into a
risk-checked equity intent and a SELL into a close of a held position, and
respects the max-symbols cap.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["COPY_TRADING_ENABLED"] = "true"
os.environ["COPY_TRADING_MAX_SYMBOLS"] = "2"

from config import load_config
from strategies.copy_trading import CopyTrader
from utils.state_store import default_state


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    cfg = load_config()
    ct = CopyTrader(cfg)

    # normalization across messy shapes
    norm = ct._normalize([
        {"ticker": "aapl", "transaction": "Purchase"},
        {"symbol": "MSFT", "side": "SALE"},
        {"symbol": "", "side": "buy"},          # dropped (no symbol)
        {"symbol": "NVDA", "type": "hold"},     # dropped (no actionable side)
    ])
    syms = {s["symbol"]: s["side"] for s in norm}
    _check(syms == {"AAPL": "buy", "MSFT": "sell"}, "normalizes tickers/sides, drops junk")

    # decide(): BUY → risk-checked buy intent; SELL of held → close
    prices = {"AAPL": 200.0, "MSFT": 400.0, "TSLA": 250.0}
    state = default_state()
    state["positions"] = {"MSFT": {"strategy": "copy", "shares": 5, "cost_basis": 380.0}}
    signals = [{"symbol": "AAPL", "side": "buy", "weight": 1.0, "source": "Sen. X"},
               {"symbol": "MSFT", "side": "sell", "source": "Rep. Y"},
               {"symbol": "TSLA", "side": "buy", "weight": 1.0, "source": "Sen. Z"}]
    intents = ct.decide(signals, state, equity=100_000.0, get_price=lambda s: prices.get(s, 0.0))

    buys = [i for i in intents if i.purpose == "copy_buy"]
    exits = [i for i in intents if i.purpose == "copy_exit"]
    _check(any(i.symbol == "AAPL" and i.side == "buy" and i.risk_check for i in buys),
           "BUY signal → risk-checked equity buy")
    _check(all(i.qty > 0 and i.est_notional > 0 for i in buys), "buys are sized with notional")
    _check(any(i.symbol == "MSFT" and i.side == "sell" and i.clear_position for i in exits),
           "SELL of a held name → position close")
    _check(len(buys) <= 2, "respects COPY_TRADING_MAX_SYMBOLS cap")

    # disabled / no source → no signals
    os.environ["COPY_TRADING_ENABLED"] = "false"
    _check(CopyTrader(load_config()).fetch_signals() == [], "disabled → no signals (no network)")

    print("\nCOPY-TRADING CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
