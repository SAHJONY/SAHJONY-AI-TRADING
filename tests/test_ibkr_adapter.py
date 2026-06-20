"""IBKR adapter verification (offline) — no pytest, no ib_insync, no TWS needed.

    python -m tests.test_ibkr_adapter

ib_insync isn't installed in CI and there's no TWS, so the adapter must degrade
to the shared SimBroker (zero real orders) and still satisfy the full broker
contract and run a cycle. Live behavior must be validated against a paper
TWS/Gateway separately — see MULTI_ACCOUNT.md.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["BROKER"] = "ibkr"
os.environ["TICKERS"] = "AAPL,FX:EUR/USD,FUT:ES@CME"
os.environ["MARKET_HOURS"] = "24_7"

from config import load_config
from database import Database
from utils.broker import REQUIRED, get_broker
from utils.brokers.ibkr import IBKRBroker
from utils.state_store import default_state
from workforce import Firm


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    cfg = load_config()
    _check(cfg.broker == "ibkr", "BROKER=ibkr selected")

    client = get_broker(cfg)            # factory must route + verify the contract
    _check(isinstance(client, IBKRBroker), "factory returns the IBKR adapter")
    _check(all(hasattr(client, m) for m in REQUIRED), "IBKR adapter implements full contract")

    # no ib_insync / no TWS here → must be offline-sim, never claiming a live link
    _check(client.online is False, "no TWS → not online")
    _check(client.mode == "offline-sim", "degrades to offline-sim (zero real orders)")

    # data + orders work via the sim fallback across asset classes
    for sym in cfg.tickers:
        _check(client.get_price(sym) > 0, f"price available for {sym}")
    res = client.submit_equity_order("FX:EUR/USD", 1000, "buy")
    _check(res.get("simulated") is True and res["status"] == "filled",
           "order routed to sim (simulated fill, no real order)")
    _check(client.is_market_open() is True, "24/7 desk is always open")

    # a full cycle runs end-to-end on an IBKR (sim-fallback) desk
    db = Database(":memory:")
    firm = Firm(cfg, client, db)
    out = firm.run_cycle(default_state(), trade=True)
    _check(out["cycle"] == 1 and out["equity"] > 0, "IBKR desk completes a cycle")
    db.close()

    for k in ("BROKER", "TICKERS", "MARKET_HOURS"):
        del os.environ[k]
    print("\nIBKR ADAPTER CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
