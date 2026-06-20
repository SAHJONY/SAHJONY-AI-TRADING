"""Cross-adapter conformance — every registered broker must behave consistently.

    python -m tests.test_broker_conformance

With no credentials/SDK/connection, EVERY venue must degrade to offline-sim and
honor the whole BrokerAdapter contract identically: safe account shape, positive
sim prices, history arrays, a list option chain, a bool clock, and orders that
are SIMULATED (never real). This guards the seam as adapters multiply.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")
# ensure no adapter sees credentials and tries a real connection
for _k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "CCXT_API_KEY", "CCXT_SECRET"):
    os.environ.pop(_k, None)

import numpy as np

from config import load_config
from utils.broker import REQUIRED, get_broker

VENUES = ["alpaca", "ibkr", "ccxt"]


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    for venue in VENUES:
        os.environ["BROKER"] = venue
        os.environ["TICKERS"] = "BTC/USD" if venue == "ccxt" else "AAPL"
        cfg = load_config()
        b = get_broker(cfg)
        sym = cfg.tickers[0]

        _check(all(hasattr(b, m) for m in REQUIRED), f"[{venue}] implements full contract")
        _check(b.online is False, f"[{venue}] offline with no credentials/connection")
        _check(b.mode == "offline-sim", f"[{venue}] degrades to offline-sim")

        acct = b.get_account()
        _check(all(k in acct for k in ("equity", "cash", "buying_power")),
               f"[{venue}] account has equity/cash/buying_power")

        _check(b.get_price(sym) > 0, f"[{venue}] sim price positive")
        hist = b.get_history(sym, 30)
        _check(isinstance(hist["closes"], np.ndarray) and hist["closes"].size > 0,
               f"[{venue}] history returns a non-empty array")
        _check(isinstance(b.is_market_open(), bool), f"[{venue}] market clock is bool")
        _check(isinstance(b.get_option_chain(sym, 100.0, 14, 28, 0.3), list),
               f"[{venue}] option chain is a list")

        res = b.submit_equity_order(sym, 1, "buy")
        _check(res.get("simulated") is True, f"[{venue}] offline order is SIMULATED (no real order)")

    for k in ("BROKER", "TICKERS"):
        os.environ.pop(k, None)
    print("\nBROKER CONFORMANCE CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
