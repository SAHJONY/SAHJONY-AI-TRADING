"""Multi-venue layer tests: registry parsing, router fail-closed behavior,
per-venue live gating, and the get_broker() integration seam.

    python -m tests.test_venues

No pytest required. No credentials, no network: every adapter is constructed
offline (simulator venue, unarmed Robinhood venue, credential-less Alpaca
venue). Live gating is verified by asserting venues can NEVER report LIVE
without the full ack chain.
"""
from __future__ import annotations

import contextlib
import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")
# NOTE: never pop credential env vars at module import time — pytest imports
# every test module during collection, so a module-level pop here would strip
# the deterministic test keypair that test_robinhood_safety.py installs at its
# own import, breaking the arming/signature tests. Credential isolation happens
# per-test inside env() below instead.

from config import load_config
from utils.broker import REQUIRED, get_broker
from venues.base import is_crypto_like, normalize_symbol
from venues.registry import build_venue_specs, parse_venues
from venues.router import VenueRouter

_SAFE_ENV = {
    "BROKER": "alpaca",
    "VENUES": "",
    "TICKERS": "AAPL,BTC/USD",
    "TICKERS_ROBINHOOD_CRYPTO": "",
    "TICKERS_ALPACA": "",
    "TICKERS_SIMULATOR": "",
    "MAX_ORDER_USD_SIMULATOR": "",
    "MAX_ORDER_USD_ALPACA": "",
    "MAX_ORDER_USD_ROBINHOOD_CRYPTO": "",
    "ROBINHOOD_LIVE": "false",
    "ALPACA_LIVE": "false",
    "ALPACA_LIVE_ACK": "",
    "LIVE_TRADING_ACK": "",
}


@contextlib.contextmanager
def env(**overrides):
    """Isolated env per test: safe defaults, then overrides; restored after."""
    saved = dict(os.environ)
    try:
        # Never let ambient credentials make a test "live" (scoped here, not at
        # module import — see note above).
        for _k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY",
                   "ROBINHOOD_API_KEY", "ROBINHOOD_PRIVATE_KEY"):
            os.environ.pop(_k, None)
        for k, v in _SAFE_ENV.items():
            os.environ[k] = v
        for k, v in overrides.items():
            os.environ[k] = v
        yield load_config()
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _sim_router(**over):
    base = dict(VENUES="simulator:paper", TICKERS="AAPL,BTC/USD")
    base.update(over)
    with env(**base) as cfg:
        specs = build_venue_specs(cfg)
    return VenueRouter(specs)


# ── symbol helpers ───────────────────────────────────────────────────────────
def test_normalize_symbol():
    _check(normalize_symbol("btc-usd") == "BTC/USD", "dash → slash normalization")
    _check(normalize_symbol("BTC/USD") == "BTC/USD", "slash form stable")
    _check(normalize_symbol(" aapl ") == "AAPL", "trim + upper")


def test_is_crypto_like():
    _check(is_crypto_like("BTC/USD"), "BTC/USD is crypto-like")
    _check(is_crypto_like("eth-usdt"), "eth-usdt is crypto-like")
    _check(not is_crypto_like("AAPL"), "AAPL is not crypto-like")
    _check(not is_crypto_like("SPY"), "SPY is not crypto-like")


# ── VENUES parsing ───────────────────────────────────────────────────────────
def test_parse_venues():
    _check(parse_venues("robinhood_crypto:live,alpaca:paper,simulator") == [
        ("robinhood_crypto", "live"), ("alpaca", "paper"), ("simulator", "paper")],
        "parse pairs; mode defaults to paper")
    _check(parse_venues("") == [], "empty → no venues")
    for bad in ("faketrade:paper", "alpaca:paper,alpaca:paper", "alpaca:realmoney"):
        try:
            parse_venues(bad)
            _check(False, f"parse_venues({bad!r}) should raise")
        except ValueError:
            pass
    print("✓ parse_venues rejects unknown/duplicate/bad-mode")


# ── registry ─────────────────────────────────────────────────────────────────
def test_registry_simulator_auto_assign():
    with env(VENUES="simulator:paper", TICKERS="AAPL,BTC/USD") as cfg:
        specs = build_venue_specs(cfg)
    _check(len(specs) == 1, "one spec built")
    _check(specs[0].venue_id == "simulator", "simulator spec")
    _check(set(specs[0].tickers) == {"AAPL", "BTC/USD"}, "tickers auto-assigned")
    _check(not specs[0].live_armed, "simulator never armed")


def test_registry_explicit_tickers_split():
    with env(VENUES="alpaca:paper,simulator:paper", TICKERS="AAPL,MSFT,BTC/USD",
             TICKERS_ALPACA="AAPL,MSFT") as cfg:
        specs = build_venue_specs(cfg)
    by_id = {s.venue_id: s for s in specs}
    _check(set(by_id["alpaca"].tickers) == {"AAPL", "MSFT"}, "explicit tickers honored")
    _check(set(by_id["simulator"].tickers) == {"BTC/USD"}, "remainder auto-assigned")


def test_registry_rejects_unsupported_explicit_ticker():
    with env(VENUES="robinhood_crypto:paper",
             TICKERS_ROBINHOOD_CRYPTO="AAPL") as cfg:
        try:
            build_venue_specs(cfg)
            _check(False, "AAPL on robinhood_crypto should raise")
        except ValueError:
            print("✓ registry rejects stock ticker on crypto venue")


def test_registry_empty_when_unset():
    with env() as cfg:
        _check(build_venue_specs(cfg) == [], "no VENUES → no specs (legacy mode)")


# ── router: contract + routing + fail-closed ─────────────────────────────────
def test_router_implements_contract():
    r = _sim_router()
    _check(all(hasattr(r, m) for m in REQUIRED), "router implements full BrokerAdapter contract")
    _check(r.online is True, "router online (sim always on)")
    _check(r.mode == "paper", "all-paper router reports paper")


def test_router_routes_per_symbol():
    with env(VENUES="alpaca:paper,simulator:paper", TICKERS="AAPL,MSFT,BTC/USD",
             TICKERS_ALPACA="AAPL,MSFT") as cfg:
        r = VenueRouter(build_venue_specs(cfg))
    _check(r.spec_for("AAPL").venue_id == "alpaca", "AAPL → alpaca")
    _check(r.spec_for("BTC/USD").venue_id == "simulator", "BTC/USD → simulator")
    _check(r.spec_for("btc-usd").venue_id == "simulator", "symbol normalization routes")


def test_router_fail_closed_unknown_symbol():
    r = _sim_router()
    _check(r.spec_for("ZZZZ") is None, "no spec for unknown symbol")
    _check(r.get_price("ZZZZ") == 0.0, "unknown symbol prices at 0.0 (fail closed)")
    res = r.submit_equity_order("ZZZZ", 1, "buy")
    _check(res["status"] == "rejected" and "no venue" in res["reason"],
           "unknown symbol order rejected with clear reason")


def test_router_sim_order_fills_paper():
    r = _sim_router()
    px = r.get_price("AAPL")
    _check(px > 0, "sim prices AAPL")
    # $10 notional: safely under the $25 venue cap whatever the sim's
    # synthetic price level is (hard-coding qty broke when AAPL's sim
    # price drifted above $250).
    res = r.submit_equity_order("AAPL", 10.0 / px, "buy")
    _check(res["status"] == "filled", "sim order fills")
    _check(res.get("simulated") is True, "sim fill marked simulated")
    _check(res.get("venue") == "simulator", "fill tagged with venue")


def test_router_per_venue_cap():
    r = _sim_router(MAX_ORDER_USD_SIMULATOR="0.01")
    res = r.submit_equity_order("AAPL", 10, "buy")
    _check(res["status"] == "rejected" and "max_order_usd" in res["reason"],
           "per-venue notional cap enforced")


def test_router_aggregates_accounts():
    with env(VENUES="simulator:paper,alpaca:paper", TICKERS="AAPL") as cfg:
        r = VenueRouter(build_venue_specs(cfg))
    acct = r.get_account()
    _check(set(acct) == {"equity", "cash", "buying_power"}, "aggregate account shape")
    _check(acct["equity"] > 0, "sim brings a funded paper account")


def test_router_describe_venues():
    r = _sim_router()
    desc = r.describe_venues()
    _check(len(desc) == 1, "one venue described")
    d = desc[0]
    _check(d["id"] == "simulator" and d["mode"] == "paper"
           and d["live_armed"] is False and d["symbol_count"] == 2,
           "describe() dashboard block correct")


def test_router_cancel_unsupported_graceful():
    r = _sim_router()
    res = r.cancel_order("abc123", "AAPL")
    _check(res["status"] in ("unsupported", "rejected", "error"),
           "cancel without venue support degrades gracefully")


# ── per-venue live gating ────────────────────────────────────────────────────
def test_simulator_can_never_be_live():
    from venues.simulator_venue import SimulatorVenue
    with env() as cfg:
        v = SimulatorVenue(cfg, live_requested=True)  # :live requested!
    _check(v.mode == "paper" and v.live_armed is False,
           "simulator :live forced back to paper")


def test_alpaca_live_requires_ack():
    from venues.alpaca_venue import AlpacaVenue
    with env(ALPACA_LIVE="true", ALPACA_LIVE_ACK="") as cfg:
        v = AlpacaVenue(cfg, live_requested=True)
    _check(v.mode == "paper" and v.live_armed is False,
           "alpaca live without ack → paper (fail closed)")
    with env() as cfg:
        v2 = AlpacaVenue(cfg, live_requested=False)
    _check(v2.mode == "paper" and v2.claims("AAPL") and v2.claims("BTC/USD"),
           "alpaca paper claims stocks + crypto")


def test_robinhood_venue_unarmed_without_credentials():
    from venues.robinhood_venue import RobinhoodCryptoVenue
    with env() as cfg:
        v = RobinhoodCryptoVenue(cfg)
    _check(not v.armed and v.mode != "LIVE", "no creds → never LIVE")
    _check(v.claims("BTC/USD") and not v.claims("AAPL"),
           "robinhood venue claims crypto only")


# ── get_broker() seam ────────────────────────────────────────────────────────
def test_get_broker_legacy_untouched():
    with env(BROKER="robinhood_crypto") as cfg:
        client = get_broker(cfg)
    _check(type(client).__name__ == "RobinhoodCryptoBroker",
           "VENUES unset → legacy RobinhoodCryptoBroker (zero behavior change)")
    _check(not isinstance(client, VenueRouter), "legacy path is not a router")


def test_get_broker_multivenue():
    with env(VENUES="simulator:paper", TICKERS="AAPL") as cfg:
        client = get_broker(cfg)
    _check(isinstance(client, VenueRouter), "VENUES set → VenueRouter")
    _check(all(hasattr(client, m) for m in REQUIRED), "router satisfies contract")


def main() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} venue tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
