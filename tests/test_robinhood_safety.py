"""Robinhood Crypto — safety & signing tests (offline, no network, no money).

    python -m tests.test_robinhood_safety

Verifies the two things about the real-money adapter that CAN be checked without
live credentials: (1) the Ed25519 request signature is computed over exactly
`api_key + timestamp + path + method + body` and verifies against the key's
public half; (2) orders are hard-gated — a broker that isn't deliberately armed
places NOTHING, and the per-order USD cap is enforced. Live auth itself can only
be confirmed by the owner via `python -m scripts.robinhood_check`.
"""
from __future__ import annotations

import base64
import os
import sys

os.environ.setdefault("LOG_LEVEL", "ERROR")

import nacl.signing

# Deterministic test keypair — set BEFORE constructing the broker so it picks
# these up. This is a throwaway key generated from a fixed seed; not a secret.
_SEED = b"\x11" * 32
os.environ["ROBINHOOD_API_KEY"] = "test-api-key-123"
os.environ["ROBINHOOD_PRIVATE_KEY"] = base64.b64encode(_SEED).decode()

from config import load_config
from utils.brokers.robinhood_crypto import RobinhoodCryptoBroker, _rh_symbol


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def test_signature_message_and_verify():
    rh = RobinhoodCryptoBroker(load_config())
    _check(rh.online, "signer initialized from base64 seed")
    path, method, body = "/api/v1/crypto/trading/accounts/", "GET", ""
    h = rh._headers(method, path, body)
    _check(h["x-api-key"] == "test-api-key-123", "x-api-key header set")
    _check(h["x-timestamp"].isdigit(), "x-timestamp is a unix seconds string")
    # Reconstruct the exact signed message and verify with the PUBLIC key.
    message = f"{h['x-api-key']}{h['x-timestamp']}{path}{method}{body}".encode()
    vk = nacl.signing.SigningKey(_SEED).verify_key
    try:
        vk.verify(message, base64.b64decode(h["x-signature"]))
        verified = True
    except Exception:
        verified = False
    _check(verified, "x-signature verifies over api_key+timestamp+path+method+body (base64 Ed25519)")
    # A tampered message must NOT verify (guards against a wrong concat order).
    try:
        vk.verify(b"WRONG" + message, base64.b64decode(h["x-signature"]))
        tampered_ok = True
    except Exception:
        tampered_ok = False
    _check(not tampered_ok, "a modified message fails verification (signing is real)")


def test_orders_hard_gated_when_unarmed():
    rh = RobinhoodCryptoBroker(load_config())
    rh.get_price = lambda s: 100.0            # avoid any network
    _check(not rh.armed, "broker is NOT armed by default (no LIVE_TRADING_ACK/ROBINHOOD_LIVE)")
    _check(rh.mode == "robinhood-dryrun", "unarmed mode is 'robinhood-dryrun', never 'LIVE'")
    res = rh.submit_equity_order("BTC-USD", 0.01, "buy")   # ~$1, under the cap
    _check(res.get("dry_run") is True and res.get("simulated") is True,
           "unarmed order is a DRY-RUN — nothing placed")


def test_per_order_usd_cap_enforced():
    rh = RobinhoodCryptoBroker(load_config())
    rh.get_price = lambda s: 100000.0          # BTC-ish
    rh.max_order_usd = 25.0
    res = rh.submit_equity_order("BTC-USD", 1.0, "buy")     # ~$100k ≫ $25 cap
    _check(res.get("status") == "rejected" and "MAX_ORDER" in res.get("reason", ""),
           "order above ROBINHOOD_MAX_ORDER_USD is rejected before any placement")


def test_symbol_normalization():
    _check(_rh_symbol("BTC") == "BTC-USD", "'BTC' → 'BTC-USD'")
    _check(_rh_symbol("ETH/USD") == "ETH-USD", "'ETH/USD' → 'ETH-USD'")
    _check(_rh_symbol("sol-usd") == "SOL-USD", "'sol-usd' → 'SOL-USD'")


def test_coingecko_id_mapping():
    from utils.brokers.robinhood_crypto import _coingecko_id
    _check(_coingecko_id("BTC-USD") == "bitcoin", "'BTC-USD' → coingecko id 'bitcoin'")
    _check(_coingecko_id("ETH/USD") == "ethereum", "'ETH/USD' → 'ethereum'")
    _check(_coingecko_id("WAT-USD") == "", "unmapped asset → '' (triggers flat fallback)")


def test_history_parses_coingecko_without_network():
    """get_history backfills daily closes from CoinGecko so the council isn't blind
    on crypto. Stub the HTTP layer so this stays offline/deterministic."""
    import requests
    rh = RobinhoodCryptoBroker(load_config())

    class _Resp:
        ok = True
        status_code = 200
        def json(self):
            return {"prices": [[0, 100.0], [1, 101.0], [2, 102.5]],
                    "total_volumes": [[0, 5.0], [1, 6.0], [2, 7.0]]}

    saved = requests.get
    requests.get = lambda *a, **k: _Resp()
    try:
        h = rh.get_history("BTC-USD", days=3)
    finally:
        requests.get = saved
    _check(list(h["closes"]) == [100.0, 101.0, 102.5], "closes parsed from CoinGecko 'prices'")
    _check(list(h["volumes"]) == [5.0, 6.0, 7.0], "volumes parsed from 'total_volumes'")


def test_history_falls_back_when_feed_unavailable():
    """Any feed failure (unmapped, network, rate-limit) must degrade to the flat
    live-price series — never raise — so the 24/7 loop can't be broken by CoinGecko."""
    rh = RobinhoodCryptoBroker(load_config())
    rh.get_price = lambda s: 250.0                       # avoid network on the fallback
    rh._coingecko_history = lambda symbol, days: None    # simulate feed down / unmapped
    h = rh.get_history("BTC-USD", days=120)
    _check(h["closes"].size == 2 and float(h["closes"][0]) == 250.0,
           "feed down → flat 2-point live-price series (safe degrade, no crash)")


def main() -> int:
    test_signature_message_and_verify()
    test_orders_hard_gated_when_unarmed()
    test_per_order_usd_cap_enforced()
    test_symbol_normalization()
    test_coingecko_id_mapping()
    test_history_parses_coingecko_without_network()
    test_history_falls_back_when_feed_unavailable()
    print("\nROBINHOOD SAFETY TESTS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
