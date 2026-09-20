"""Strict fail-closed snapshot policy (owner decision 2026-09-20).

If a held asset cannot be priced, the broker snapshot fails closed —
halt new risk with a loud alert — never omit-and-continue. The bot must be
physically incapable of trading blind.

    python -m pytest tests/test_snapshot_fail_closed.py -q

No credentials, no network.
"""
from __future__ import annotations

import base64
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("LOG_LEVEL", "ERROR")

try:
    import nacl.signing  # noqa: F401
except ImportError:
    pytest.skip("pynacl is not installed — Robinhood venue tests cannot run",
                allow_module_level=True)

_SEED = b"\x33" * 32


@pytest.fixture(autouse=True)
def _isolated_robinhood_creds(monkeypatch):
    """Throwaway creds, restored after each test (test isolation: never stomp
    the process env at import time — test_robinhood_safety.py verifies
    signatures against its own deterministic seed)."""
    monkeypatch.setenv("ROBINHOOD_API_KEY", "test-api-key-123")
    monkeypatch.setenv("ROBINHOOD_PRIVATE_KEY", base64.b64encode(_SEED).decode())

from config import load_config  # noqa: E402
from utils.broker import BrokerSnapshotError  # noqa: E402
from utils.brokers.robinhood_crypto import RobinhoodCryptoBroker  # noqa: E402
from workforce import Firm  # noqa: E402


def _broker():
    return RobinhoodCryptoBroker(load_config())


def test_unpriceable_holding_raises_not_omitted():
    """The core strict-policy proof: an unpriceable holding raises
    BrokerSnapshotError instead of being silently omitted."""
    rh = _broker()
    rh._request = lambda *a, **k: {
        "results": [{"asset_code": "ETH", "total_quantity": "0.5"}]}
    rh.get_price = lambda symbol: 0.0  # no feed can price it
    with pytest.raises(BrokerSnapshotError, match="failed closed"):
        rh.get_broker_positions()


def test_get_account_stashes_snapshot_error():
    rh = _broker()
    rh._request = lambda m, p, b=None: (
        {"buying_power": "67.54"} if "accounts" in p else
        {"results": [{"asset_code": "ETH", "total_quantity": "0.5"}]})
    rh.get_price = lambda symbol: 0.0
    acct = rh.get_account()
    assert acct == {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}
    assert "failed closed" in rh.snapshot_error()
    assert "ETH" in rh.snapshot_error()


def test_snapshot_error_clears_on_clean_read():
    rh = _broker()
    rh._request = lambda m, p, b=None: (
        {"buying_power": "67.54"} if "accounts" in p else
        {"results": [{"asset_code": "ETH", "total_quantity": "0.5"}]})
    rh.get_price = lambda symbol: 0.0
    rh.get_account()
    assert rh.snapshot_error() != ""
    # Next read prices fine → error clears
    rh.get_price = lambda symbol: 3000.0
    acct = rh.get_account()
    assert acct["equity"] == pytest.approx(67.54 + 0.5 * 3000.0)
    assert rh.snapshot_error() == ""


def _firm_stub(client):
    return SimpleNamespace(client=client)


def test_gate_halts_new_risk_on_snapshot_error():
    stub_client = SimpleNamespace(
        snapshot_error=lambda: "Robinhood holding ETH has no valid price — "
                               "snapshot failed closed")
    firm = _firm_stub(stub_client)
    halt = {"halted": False, "reason": ""}
    halt, allow = Firm._snapshot_fail_closed_gate(firm, halt, True)
    assert allow is False
    assert halt["halted"] is True
    assert "failed closed" in halt["reason"]


def test_gate_noop_when_snapshot_clean():
    stub_client = SimpleNamespace(snapshot_error=lambda: "")
    firm = _firm_stub(stub_client)
    halt = {"halted": False, "reason": ""}
    halt2, allow = Firm._snapshot_fail_closed_gate(firm, halt, True)
    assert allow is True
    assert halt2["halted"] is False
    assert halt2["reason"] == ""


def test_gate_noop_for_venues_without_accessor():
    firm = _firm_stub(SimpleNamespace())  # e.g. sim/paper/alpaca client
    halt = {"halted": False, "reason": ""}
    halt2, allow = Firm._snapshot_fail_closed_gate(firm, halt, True)
    assert allow is True
    assert halt2["halted"] is False


# ── re-arm: the data_freshness stand-down clears itself on green health ───────

def test_standdown_auto_clears_on_green_health():
    """Re-arm path (no manual state surgery): an active data_freshness
    escalation with dry_run_standdown clears the first cycle feeds grade
    healthy again, and trading_blocked() releases."""
    from intel.self_heal import SelfHeal
    sh = SelfHeal()
    state = {"self_heal": {
        "health": {"data_freshness": {"state": "degraded", "healthy_streak": 0}},
        "strikes": {"data_freshness": 3},
        "escalation": {"active": True, "subsystem": "data_freshness",
                       "ts": "2026-09-19T23:00:00Z",
                       "note": "data_freshness failed 3 auto-recoveries",
                       "dry_run_standdown": True},
        "log": [], "breaker": {"tripped": False},
    }}
    # while feeds are still bad, the stand-down holds
    sh.observe(state, {"account_ok": True, "account_error": None,
                       "price_errors": {}, "price_symbols": 18,
                       "exceptions": [], "feed_ok": False, "cycle": 1})
    blocked, _ = sh.trading_blocked(state)
    assert blocked is True
    # feeds green again (Hermes quarantines clear once quotes land) →
    # strikes reset and the escalation auto-clears; no cache surgery needed
    sh.observe(state, {"account_ok": True, "account_error": None,
                       "price_errors": {}, "price_symbols": 18,
                       "exceptions": [], "feed_ok": True, "cycle": 2})
    mem = state["self_heal"]
    assert mem["strikes"]["data_freshness"] == 0
    assert mem["escalation"]["active"] is False
    assert "cleared_at" in mem["escalation"]
    blocked, _ = sh.trading_blocked(state)
    assert blocked is False
