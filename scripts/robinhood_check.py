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
    if rh._signer is not None:
        import base64 as _b64
        derived_pub = _b64.b64encode(bytes(rh._signer.verify_key)).decode()
        print(f"  Derived PUBLIC key   : {derived_pub}")
        print( "    ^ This is computed from your stored PRIVATE key (safe to show).")
        print( "      It must EXACTLY match the public key registered on the Robinhood")
        print( "      credential. If it differs, the stored private key is from a")
        print( "      different keypair (or the public key was pasted as the private).")
    print(f"  Per-order cap        : ${rh.max_order_usd:,.2f}  (ROBINHOOD_MAX_ORDER_USD)")
    if not rh.online:
        print(bar)
        print("  Cannot check auth — add the credentials above to .env, then rerun.")
        print(bar)
        return 1

    print("  → GET account (verifies signing on your real account)…")
    # Identify WHICH Robinhood account this credential is bound to. The last 4 of
    # the account number should match the account shown in the app (e.g. •1131);
    # if it doesn't, the keys were created under a different login and the desk
    # is looking at an empty account.
    try:
        raw = rh._request("GET", "/api/v1/crypto/trading/accounts/")
        num = str(raw.get("account_number", "") or "")
        print(f"    account_number  : …{num[-4:] if num else '?'}   status={raw.get('status', '?')}")
        print( "    ^ compare with the account shown in the Robinhood app.")
    except Exception as exc:
        print(f"    (could not read account identity: {str(exc)[:90]})")
    acct = rh.get_account()
    ok = acct["buying_power"] > 0 or acct["equity"] > 0 or acct["cash"] >= 0
    print(f"    buying_power=${acct['buying_power']:,.2f}  equity=${acct['equity']:,.2f}")
    holdings = rh.get_broker_positions()
    if holdings:
        for sym, h in holdings.items():
            print(f"    holding {sym}: {h.get('qty')} (${h.get('market_value', 0):,.2f})")
    else:
        print("    holdings: none reported by the API for this account")
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
