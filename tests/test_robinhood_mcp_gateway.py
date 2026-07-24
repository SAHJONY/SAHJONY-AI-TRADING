from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection

import pytest
import requests

from config import load_config
from scripts.robinhood_mcp_gateway import (GatewayError, GatewayService,
                                           TransientPositionsError, TransientQuoteError,
                                           _validate_upstream_payload, make_handler)
from utils.brokers.robinhood_mcp import RobinhoodMCPBroker
from http.server import ThreadingHTTPServer


class FakeBridge:
    def __init__(self, *, last4: str = "1131") -> None:
        self.last4 = last4
        self.calls: list[tuple[str, dict]] = []

    def call(self, operation: str, **parameters):
        self.calls.append((operation, parameters))
        account = {
            "account_number_last4": self.last4,
            "account_type": "Agentic individual cash",
            "status": "active",
            "cash": -5.01,
            "buying_power": -5.01,
            "equity": 0.88,
        }
        if operation == "account_snapshot":
            return account
        if operation == "positions":
            return {"account": account, "positions": [{"symbol": "VTI", "qty": 1.0}]}
        if operation == "quote":
            return {"symbol": parameters["symbol"], "price": 321.45,
                    "as_of": "2026-07-15T06:00:00Z", "source": "robinhood-trading-mcp"}
        if operation == "crypto_capability":
            return {"supported": False, "reason": "tool_unavailable", "account": account,
                    "positions": [], "observed_at": datetime.now(timezone.utc).isoformat()}
        raise AssertionError(operation)


def test_service_verifies_identity_and_normalizes_contract():
    service = GatewayService(FakeBridge(), expected_last4="1131", cache_seconds=0)
    assert service.health()["read_only"] is True
    assert service.health()["market_open"] is False
    assert service.account()["account_number_last4"] == "1131"
    assert service.positions()["positions"][0]["symbol"] == "VTI"
    assert service.quote("vti")["price"] == 321.45
    assert service.quote("vti")["source"] == "robinhood-trading-mcp"
    assert service.crypto_capability()["supported"] is False


def test_crypto_capability_normalizes_authenticated_rows():
    payload = {
        "supported": True, "reason": "available",
        "account": {"account_number_last4": "1131", "account_type": "Agentic cash",
                    "status": "active"},
        "positions": [{"symbol": "btc", "qty": "0.00005", "market_value": "5.91",
                       "asset_type": "crypto",
                       "observed_at": "2026-07-23T20:00:00Z"}],
        "observed_at": "2026-07-23T20:00:00Z",
    }
    result = _validate_upstream_payload("crypto_capability", payload, {})
    assert result["supported"] is True
    assert result["positions"][0] == {
        "symbol": "BTC", "qty": 0.00005, "market_value": 5.91,
        "avg_entry_price": 0.0, "asset_type": "crypto",
        "observed_at": "2026-07-23T20:00:00Z",
    }


def test_crypto_capability_rejects_invented_unsupported_positions():
    payload = {
        "supported": False, "reason": "tool_unavailable",
        "account": {"account_number_last4": "1131", "account_type": "Agentic cash",
                    "status": "active"},
        "positions": [{"symbol": "BTC"}],
        "observed_at": "2026-07-23T20:00:00Z",
    }
    with pytest.raises(GatewayError, match="unsupported crypto capability"):
        _validate_upstream_payload("crypto_capability", payload, {})


def test_identity_mismatch_fails_closed():
    service = GatewayService(FakeBridge(last4="9999"), expected_last4="1131", cache_seconds=0)
    with pytest.raises(GatewayError, match="identity"):
        service.account()


def test_invalid_quote_symbol_is_rejected_before_bridge_call():
    bridge = FakeBridge()
    service = GatewayService(bridge, expected_last4="1131")
    with pytest.raises(ValueError, match="invalid symbol"):
        service.quote("../../orders")
    assert bridge.calls == []


class ScriptedQuoteBridge:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def call(self, operation, **parameters):
        self.calls.append((operation, parameters))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def positions_payload():
    return {"account": {
        "account_number_last4": "1131", "account_type": "Agentic individual cash",
        "status": "active",
    }, "positions": [{"symbol": "VTI", "qty": 1.0}]}


def test_positions_first_attempt_success_has_no_backoff():
    bridge = ScriptedQuoteBridge([positions_payload()])
    sleeps = []
    service = GatewayService(bridge, expected_last4="1131", cache_seconds=0, sleep=sleeps.append)
    assert service.positions()["positions"][0]["symbol"] == "VTI"
    assert len(bridge.calls) == 1
    assert sleeps == []


def test_positions_timeout_then_success_retries_once():
    bridge = ScriptedQuoteBridge([TransientPositionsError("timeout"), positions_payload()])
    sleeps = []
    service = GatewayService(bridge, expected_last4="1131", cache_seconds=0, sleep=sleeps.append)
    assert service.positions()["positions"][0]["symbol"] == "VTI"
    assert len(bridge.calls) == 2
    assert sleeps == [1]


def test_three_positions_timeouts_fail_closed_without_simulated_fallback():
    bridge = ScriptedQuoteBridge([TransientPositionsError("timeout") for _ in range(3)])
    sleeps = []
    service = GatewayService(bridge, expected_last4="1131", cache_seconds=0, sleep=sleeps.append)
    with pytest.raises(TransientPositionsError, match="timeout"):
        service.positions()
    assert len(bridge.calls) == 3
    assert sleeps == [1, 2]


def normalized_quote(symbol="NVDA"):
    return {"symbol": symbol, "price": 212.79,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": "robinhood-trading-mcp"}


def test_quote_first_attempt_success_has_no_backoff():
    bridge = ScriptedQuoteBridge([normalized_quote()])
    sleeps = []
    service = GatewayService(
        bridge, expected_last4="1131", cache_seconds=0, sleep=sleeps.append
    )
    assert service.quote("NVDA")["price"] == 212.79
    assert len(bridge.calls) == 1
    assert sleeps == []


def test_transient_quote_failure_then_success_retries_with_backoff():
    bridge = ScriptedQuoteBridge([TransientQuoteError("upstream 502"), normalized_quote()])
    sleeps = []
    service = GatewayService(
        bridge, expected_last4="1131", cache_seconds=0, sleep=sleeps.append
    )
    assert service.quote("NVDA")["symbol"] == "NVDA"
    assert len(bridge.calls) == 2
    assert sleeps == [1]


def test_three_consecutive_transient_quote_failures_stop_after_three_attempts():
    bridge = ScriptedQuoteBridge([TransientQuoteError("timeout") for _ in range(3)])
    sleeps = []
    service = GatewayService(
        bridge, expected_last4="1131", cache_seconds=0, sleep=sleeps.append
    )
    with pytest.raises(TransientQuoteError, match="timeout"):
        service.quote("NVDA")
    assert len(bridge.calls) == 3
    assert sleeps == [1, 2]


def test_quote_failure_has_no_simulated_fallback():
    bridge = ScriptedQuoteBridge([TransientQuoteError("non-JSON") for _ in range(3)])
    service = GatewayService(bridge, expected_last4="1131", cache_seconds=0, sleep=lambda _: None)
    with pytest.raises(TransientQuoteError, match="non-JSON"):
        service.quote("NVDA")
    assert len(bridge.calls) == 3


def raw_quote(symbol="NVDA", *, age_seconds=0):
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    regular_stamp = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds + 60)).isoformat()
    return {"data": {"results": [{"quote": {
        "symbol": symbol, "last_trade_price": "211.79",
        "venue_last_trade_time": regular_stamp, "last_non_reg_trade_price": "212.79",
        "venue_last_non_reg_trade_time": stamp, "has_traded": True, "state": "active",
    }}]}}


def test_documented_equity_quote_shape_is_normalized():
    result = _validate_upstream_payload("quote", raw_quote(), {"symbol": "NVDA"})
    assert result["symbol"] == "NVDA"
    assert result["price"] == 212.79
    assert result["as_of"]
    assert result["source"] == "robinhood-trading-mcp"
    top_level = raw_quote()["data"]
    assert _validate_upstream_payload("quote", top_level, {"symbol": "NVDA"})["price"] == 212.79


def test_wrong_symbol_response_is_rejected():
    with pytest.raises(GatewayError, match="does not match"):
        _validate_upstream_payload("quote", raw_quote("MSFT"), {"symbol": "NVDA"})


def test_ambiguous_quote_response_is_rejected():
    ambiguous = raw_quote()
    ambiguous["data"]["results"].append(ambiguous["data"]["results"][0])
    with pytest.raises(GatewayError, match="ambiguous"):
        _validate_upstream_payload("quote", ambiguous, {"symbol": "NVDA"})


def test_stale_quote_response_is_rejected():
    with pytest.raises(GatewayError, match="stale"):
        _validate_upstream_payload("quote", raw_quote(age_seconds=3600), {"symbol": "NVDA"})


def test_adapter_cannot_be_armed_or_submit_orders(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_MCP_LIVE", "true")
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    called = []
    broker._request = lambda *args, **kwargs: called.append((args, kwargs))
    assert broker.trading_armed is False
    assert broker.execution_authority is False
    result = broker.submit_equity_order("VTI", 1, "buy")
    assert result["status"] == "rejected"
    assert "read-only" in result["reason"]
    assert called == []


def test_adapter_preserves_authenticated_quote_provenance(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    broker._online = True
    observed = datetime.now(timezone.utc).isoformat()
    broker._request = lambda *args, **kwargs: {
        "symbol": "VTI", "price": 321.45, "as_of": observed,
        "source": "robinhood-trading-mcp",
    }
    assert broker.get_quote_snapshot("VTI") == {
        "symbol": "VTI", "price": 321.45, "as_of": observed,
        "source": "robinhood-trading-mcp",
    }


@pytest.mark.parametrize("overrides", [
    {"source": "synthetic"},
    {"source": ""},
    {"as_of": None},
    {"as_of": ""},
])
def test_adapter_rejects_quote_without_authenticated_provenance(monkeypatch, overrides):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    broker._online = True
    payload = {"symbol": "VTI", "price": 321.45,
               "as_of": datetime.now(timezone.utc).isoformat(),
               "source": "robinhood-trading-mcp", **overrides}
    broker._request = lambda *args, **kwargs: payload
    with pytest.raises(RuntimeError, match="No valid MCP quote"):
        broker.get_quote_snapshot("VTI")


def test_adapter_quote_after_45_seconds_within_route_budget_succeeds(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    monkeypatch.setenv("ROBINHOOD_MCP_QUOTE_TIMEOUT_SECONDS", "60")
    broker = RobinhoodMCPBroker(load_config())
    broker.base_url = "http://gateway.test"
    broker._online = True
    calls = []

    class Response:
        content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return normalized_quote("VTI")

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        # A 46-second gateway response would exceed the former 45-second
        # timeout, but remains inside this route's configured 60-second budget.
        assert kwargs["timeout"] == 60
        return Response()

    monkeypatch.setattr(requests, "request", request)
    assert broker.get_quote_snapshot("VTI")["price"] == 212.79
    assert len(calls) == 1


def test_adapter_quote_beyond_total_route_budget_fails_closed_without_retry(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    monkeypatch.setenv("ROBINHOOD_MCP_QUOTE_TIMEOUT_SECONDS", "60")
    broker = RobinhoodMCPBroker(load_config())
    broker.base_url = "http://gateway.test"
    broker._online = True
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        raise requests.Timeout("route budget exhausted")

    monkeypatch.setattr(requests, "request", request)
    with pytest.raises(RuntimeError, match="No valid MCP quote"):
        broker.get_quote_snapshot("VTI")
    assert len(calls) == 1


def test_adapter_uses_explicit_route_specific_timeouts(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    monkeypatch.setenv("ROBINHOOD_MCP_HEALTH_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("ROBINHOOD_MCP_ACCOUNT_TIMEOUT_SECONDS", "11")
    monkeypatch.setenv("ROBINHOOD_MCP_POSITIONS_TIMEOUT_SECONDS", "222")
    monkeypatch.setenv("ROBINHOOD_MCP_QUOTE_TIMEOUT_SECONDS", "233")
    broker = RobinhoodMCPBroker(load_config())
    assert broker._timeout_for("/health") == 10
    assert broker._timeout_for("/account") == 11
    assert broker._timeout_for("/positions") == 222
    assert broker._timeout_for("/quotes/VTI") == 233


def test_health_and_account_defaults_cover_codex_bridge_budget(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    for name in (
        "ROBINHOOD_MCP_HEALTH_TIMEOUT_SECONDS",
        "ROBINHOOD_MCP_ACCOUNT_TIMEOUT_SECONDS",
        "ROBINHOOD_MCP_POSITIONS_TIMEOUT_SECONDS",
        "ROBINHOOD_MCP_QUOTE_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    broker = RobinhoodMCPBroker(load_config())
    assert broker._timeout_for("/health") == 90
    assert broker._timeout_for("/account") == 90
    assert broker._timeout_for("/positions") == 285
    assert broker._timeout_for("/quotes/VTI") == 285


def test_health_and_account_after_15_seconds_succeed_with_one_request_each(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_MCP_GATEWAY_URL", "http://gateway.test")
    monkeypatch.setenv("ROBINHOOD_MCP_GATEWAY_TOKEN", "x" * 32)
    calls = []

    class Response:
        content = b"{}"

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    account = {
        "account_number_last4": "1131", "account_type": "Agentic individual cash",
        "status": "active", "equity": 25.94, "cash": 19.99, "buying_power": 19.99,
    }

    def request(method, url, **kwargs):
        path = url.removeprefix("http://gateway.test")
        calls.append((path, kwargs["timeout"]))
        # These represent responses arriving after the old 15-second cutoff,
        # while still inside each new finite 90-second route budget.
        assert kwargs["timeout"] == 90
        return Response({"ok": True} if path == "/health" else account)

    monkeypatch.setattr(requests, "request", request)
    broker = RobinhoodMCPBroker(load_config())
    assert broker.online is True
    assert broker.identity_verified is True
    assert broker.execution_authority is False
    assert broker.trading_armed is False
    assert calls == [("/health", 90), ("/account", 90)]


def test_health_and_account_beyond_90_seconds_fail_closed_without_retry(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_MCP_GATEWAY_URL", "http://gateway.test")
    monkeypatch.setenv("ROBINHOOD_MCP_GATEWAY_TOKEN", "x" * 32)
    calls = []

    def request(method, url, **kwargs):
        path = url.removeprefix("http://gateway.test")
        calls.append((path, kwargs["timeout"]))
        raise requests.Timeout("route budget exhausted")

    monkeypatch.setattr(requests, "request", request)
    broker = RobinhoodMCPBroker(load_config())
    assert broker.online is False
    assert broker.identity_verified is False
    assert broker.mode == "offline"
    assert broker.execution_authority is False
    assert broker.trading_armed is False
    assert calls == [("/health", 90), ("/account", 90)]


def test_adapter_never_substitutes_sim_quote_when_mcp_offline(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    with pytest.raises(RuntimeError, match="authenticated"):
        broker.get_quote_snapshot("VTI")


def test_adapter_never_substitutes_sim_positions_when_mcp_offline(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    with pytest.raises(RuntimeError, match="authenticated"):
        broker.get_broker_positions()


def test_adapter_never_substitutes_sim_account_or_history_when_offline(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    assert broker.mode == "offline"
    with pytest.raises(RuntimeError, match="authenticated.*account"):
        broker.get_account()
    with pytest.raises(RuntimeError, match="authenticated.*history"):
        broker.get_history("VTI")
    assert broker.is_market_open() is False
    assert broker.advance_sim() is None


def test_online_account_and_positions_fail_closed_on_missing_payload(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    broker._online = True
    broker._account = {"equity": 999, "cash": 999, "buying_power": 999}
    broker._request = lambda *args, **kwargs: None
    with pytest.raises(RuntimeError, match="authenticated.*account"):
        broker.get_account()
    with pytest.raises(RuntimeError, match="authenticated.*positions"):
        broker.get_broker_positions()

    broker._request = lambda *args, **kwargs: {}
    with pytest.raises(RuntimeError, match="positions response is invalid"):
        broker.get_broker_positions()


@pytest.mark.parametrize("row", [
    {"symbol": "", "qty": 1},
    {"symbol": "VTI", "qty": float("nan")},
    {"symbol": "VTI", "market_value": float("inf")},
])
def test_adapter_rejects_malformed_authenticated_position_rows(monkeypatch, row):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    broker._online = True
    broker._request = lambda *args, **kwargs: {"positions": [row]}
    with pytest.raises(RuntimeError, match="position"):
        broker.get_broker_positions()


def test_adapter_rejects_nonfinite_quote(monkeypatch):
    monkeypatch.setattr(RobinhoodMCPBroker, "_connect", lambda self: None)
    broker = RobinhoodMCPBroker(load_config())
    broker._online = True
    broker._request = lambda *args, **kwargs: {
        "symbol": "VTI", "price": float("nan"),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "robinhood-trading-mcp",
    }
    with pytest.raises(RuntimeError, match="No valid MCP quote"):
        broker.get_quote_snapshot("VTI")


def test_http_auth_and_write_methods_are_rejected():
    token = "x" * 32
    service = GatewayService(FakeBridge(), expected_last4="1131", cache_seconds=0)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("GET", "/health")
        assert connection.getresponse().status == 401

        connection.request("GET", "/health", headers={"Authorization": f"Bearer {token}"})
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["identity_verified"] is True

        connection.request("POST", "/orders", body=b"{}", headers={"Authorization": f"Bearer {token}"})
        response = connection.getresponse()
        assert response.status == 405
        assert json.loads(response.read()) == {"error": "read-only gateway"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
