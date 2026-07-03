"""Robinhood Crypto — READ-ONLY connectivity & auth check. MOVES NO MONEY.

    python -m scripts.robinhood_check

Run this FIRST, before trusting any order path. Robinhood Crypto has no sandbox,
so this read-only check (GET account + a live BTC-USD quote) is how you verify
your API key + Ed25519 private key are correct without placing an order. It only
issues GET requests — it cannot buy or sell anything.

Setup (in .env, single-line values — the private key is a base64 SEED, not a PEM):
    ROBINHOOD_API_KEY=<your api key>
    ROBINHOOD_PRIVATE_KEY=<base64 ed25519 private-key seed>

Exit 0 = auth works (signing verified against your real account); 1 = it doesn't.
"""
from __future__ import annotations

import sys

from config import load_config
from utils.brokers.robinhood_crypto import RobinhoodCryptoBroker


def main() -> int:
    cfg = load_config()
    rh = RobinhoodCryptoBroker(cfg)
    bar = "=" * 64
    print(bar)
    print("  ROBINHOOD CRYPTO — READ-ONLY CHECK (no orders, no money moved)")
    print(bar)
    print(f"  API key present     : {'yes' if rh.api_key else 'NO — set ROBINHOOD_API_KEY'}")
    print(f"  Signer initialized  : {'yes' if rh.online else 'NO — set ROBINHOOD_PRIVATE_KEY (base64 seed)'}")
    print(f"  Armed for real orders: {rh.armed}   (needs LIVE_TRADING_ACK + ROBINHOOD_LIVE=true)")
    print(f"  Per-order cap        : ${rh.max_order_usd:,.2f}  (ROBINHOOD_MAX_ORDER_USD)")
    if not rh.online:
        print(bar)
        print("  Cannot check auth — add the credentials above to .env, then rerun.")
        print(bar)
        return 1

    print("  → GET account (verifies signing on your real account)…")
    acct = rh.get_account()
    ok = acct["buying_power"] > 0 or acct["equity"] > 0 or acct["cash"] >= 0
    print(f"    buying_power=${acct['buying_power']:,.2f}  equity=${acct['equity']:,.2f}")
    print("  → GET BTC-USD quote…")
    px = rh.get_price("BTC-USD")
    print(f"    BTC-USD mid = ${px:,.2f}")
    print(bar)
    if px > 0 and ok:
        print("  ✓ AUTH OK — signing works and market data flows. Safe to proceed to")
        print("    a DRY-RUN desk run (BROKER=robinhood_crypto) before ever arming.")
        print(bar)
        return 0
    print("  ✗ Auth or data check failed — see errors above (likely a 401 = bad")
    print("    signature/key, or a malformed ROBINHOOD_PRIVATE_KEY). Fix before arming.")
    print(bar)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
