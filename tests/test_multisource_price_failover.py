"""Multi-source price failover for the Robinhood crypto venue.

Verifies the documented keyless chain venue → CoinGecko → Kraken → Coinbase
is actually wired in the live price path (robinhood_crypto.py), plus the
Kraken OHLC history leg in get_history. All helpers must never raise and
unmapped symbols must never touch the network.

    python -m pytest tests/test_multisource_price_failover.py -q

No credentials, no network: HTTP is stubbed at requests.get.
"""
from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("LOG_LEVEL", "ERROR")

try:
    import nacl.signing  # noqa: F401
except ImportError:
    pytest.skip("pynacl is not installed — Robinhood venue tests cannot run",
                allow_module_level=True)

_SEED = b"\x22" * 32


@pytest.fixture(autouse=True)
def _isolated_robinhood_creds(monkeypatch):
    """Set throwaway creds for these tests WITHOUT stomping the process env
    at import time (test isolation: test_robinhood_safety.py uses its own
    deterministic seed for signature verification)."""
    monkeypatch.setenv("ROBINHOOD_API_KEY", "test-api-key-123")
    monkeypatch.setenv("ROBINHOOD_PRIVATE_KEY", base64.b64encode(_SEED).decode())

from config import load_config  # noqa: E402
from utils.brokers.robinhood_crypto import (  # noqa: E402
    RobinhoodCryptoBroker,
    _coinbase_pair,
    _kraken_pair,
)


def _broker():
    rh = RobinhoodCryptoBroker(load_config())
    # Venue transport always down: force the keyless chain.
    rh._request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("venue down"))
    return rh


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


_KRAKEN_TICKER = {"error": [], "result": {"XXBTZUSD": {"c": ["67500.50", "1.2"]}}}
_KRAKEN_OHLC = {"error": [], "result": {"XXBTZUSD": [
    [1720000000, "67000.0", "68000.0", "66000.0", "67500.0", "67200.0", "100.5", 1200],
    [1720086400, "67500.0", "69000.0", "67000.0", "68500.0", "68000.0", "110.2", 1300],
    [1720172800, "68500.0", "70000.0", "68000.0", "69500.0", "69000.0", "120.8", 1400],
], "last": 1720172800}}
_COINBASE_SPOT = {"data": {"base": "BTC", "currency": "USD", "amount": "67600.25"}}


def _fake_get(url, params=None, timeout=None):
    if "kraken.com" in url and "/Ticker" in url:
        return _FakeResp(_KRAKEN_TICKER)
    if "kraken.com" in url and "/OHLC" in url:
        return _FakeResp(_KRAKEN_OHLC)
    if "coinbase.com" in url:
        return _FakeResp(_COINBASE_SPOT)
    if "coingecko.com" in url:
        return _FakeResp({}, status=429)  # CoinGecko down: rate-limited
    raise AssertionError(f"unexpected URL in test: {url}")


def test_pair_mapping_guards_unmapped():
    assert _kraken_pair("BTC-USD") == "XXBTZUSD"
    assert _kraken_pair("ETH/USD") == "ETHUSD"
    assert _kraken_pair("ZZZ-USD") == ""
    assert _coinbase_pair("BTC-USD") == "BTC-USD"
    assert _coinbase_pair("ZZZ-USD") == ""


def test_spot_failover_kraken_then_coinbase(monkeypatch):
    monkeypatch.setattr("requests.get", _fake_get)
    rh = _broker()
    # CoinGecko 429s → Kraken serves
    assert rh.get_price("BTC-USD") == 67500.50
    assert rh.price_source("BTC-USD") == "kraken"


def test_spot_failover_coinbase_when_kraken_down(monkeypatch):
    def no_kraken(url, params=None, timeout=None):
        if "kraken.com" in url:
            return _FakeResp({}, status=500)
        return _fake_get(url, params=params, timeout=timeout)
    monkeypatch.setattr("requests.get", no_kraken)
    rh = _broker()
    assert rh.get_price("BTC-USD") == 67600.25
    assert rh.price_source("BTC-USD") == "coinbase"


def test_spot_all_feeds_down_returns_zero_never_raises(monkeypatch):
    monkeypatch.setattr("requests.get",
                        lambda url, params=None, timeout=None: _FakeResp({}, status=500))
    rh = _broker()
    assert rh.get_price("BTC-USD") == 0.0  # never raises; no cache yet
    assert rh.price_source("BTC-USD") == "cache"


def test_spot_unmapped_symbol_never_hits_network(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise AssertionError("network touched for unmapped symbol")
    monkeypatch.setattr("requests.get", boom)
    rh = _broker()
    assert rh.get_price("ZZZ-USD") == 0.0


def test_history_kraken_ohlc_fallback(monkeypatch):
    monkeypatch.setattr("requests.get", _fake_get)
    rh = _broker()
    rh._coingecko_history = lambda symbol, days: None  # CoinGecko down
    h = rh.get_history("BTC-USD", days=120)
    assert list(h["closes"]) == [67500.0, 68500.0, 69500.0]
    assert list(h["volumes"]) == [100.5, 110.2, 120.8]


def test_history_all_down_flat_fallback_never_raises(monkeypatch):
    monkeypatch.setattr("requests.get",
                        lambda url, params=None, timeout=None: _FakeResp({}, status=500))
    rh = _broker()
    rh._coingecko_history = lambda symbol, days: None
    h = rh.get_history("BTC-USD", days=120)
    # spot is also 0 → empty series; loop degrades safely, never raises
    assert h["closes"].size == 0
