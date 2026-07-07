"""Robinhood adapter verification (offline) — no pytest, no PyNaCl, no keys needed.

    python -m tests.test_robinhood_adapter

Robinhood has NO paper venue, so this adapter is the most safety-critical one in
the repo. These checks pin the guarantees that keep it from ever placing a real
order by accident:

  • no credentials              → offline-sim (zero real orders)
  • credentials but NOT armed   → still offline-sim (needs ROBINHOOD_LIVE *and*
                                  LIVE_TRADING_ACK together)
  • orders route to the sim, marked simulated, and a full cycle runs end-to-end

Live behavior must be validated against your real account with `--preflight`
before arming — see GO_LIVE.md.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["BROKER"] = "robinhood"
os.environ["TICKERS"] = "BTC/USD,ETH/USD"
os.environ["MARKET_HOURS"] = "24_7"

from config import load_config
from database import Database
from utils.broker import REQUIRED, get_broker
from utils.brokers.robinhood import RobinhoodBroker
from utils.state_store import default_state
from workforce import Firm


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    cfg = load_config()
    _check(cfg.broker == "robinhood", "BROKER=robinhood selected")

    client = get_broker(cfg)            # factory must route + verify the contract
    _check(isinstance(client, RobinhoodBroker), "factory returns the Robinhood adapter")
    _check(all(hasattr(client, m) for m in REQUIRED), "Robinhood adapter implements full contract")

    # no credentials here → must be offline-sim, never claiming a live link
    _check(client.online is False, "no credentials → not online")
    _check(client.mode == "offline-sim", "degrades to offline-sim (zero real orders)")

    # data + orders work via the sim fallback
    for sym in cfg.tickers:
        _check(client.get_price(sym) > 0, f"price available for {sym}")
    res = client.submit_equity_order("BTC/USD", 0.01, "buy")
    _check(res.get("simulated") is True and res["status"] == "filled",
           "order routed to sim (simulated fill, no real order)")
    _check(client.is_market_open() is True, "24/7 crypto desk is always open")

    # the double-lock: credentials present but NOT armed must stay offline-sim
    os.environ["ROBINHOOD_API_KEY"] = "test-key"
    os.environ["ROBINHOOD_PRIVATE_KEY"] = "dGVzdA=="   # base64("test"), never used
    armed_off = get_broker(load_config())
    _check(armed_off.online is False and armed_off.mode == "offline-sim",
           "creds without ROBINHOOD_LIVE+LIVE_TRADING_ACK stays offline-sim")
    os.environ["ROBINHOOD_LIVE"] = "true"   # only one of the two locks → still safe
    one_lock = get_broker(load_config())
    _check(one_lock.online is False and one_lock.mode == "offline-sim",
           "ROBINHOOD_LIVE alone (no LIVE_TRADING_ACK) stays offline-sim")
    for k in ("ROBINHOOD_API_KEY", "ROBINHOOD_PRIVATE_KEY", "ROBINHOOD_LIVE"):
        del os.environ[k]

    # a full cycle runs end-to-end on a Robinhood (sim-fallback) desk
    db = Database(":memory:")
    firm = Firm(cfg, client, db)
    out = firm.run_cycle(default_state(), trade=True)
    _check(out["cycle"] == 1 and out["equity"] > 0, "Robinhood desk completes a cycle")
    db.close()

    for k in ("BROKER", "TICKERS", "MARKET_HOURS"):
        del os.environ[k]
    print("\nROBINHOOD ADAPTER CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
