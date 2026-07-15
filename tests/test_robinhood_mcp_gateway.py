from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection

import pytest

from config import load_config
from scripts.robinhood_mcp_gateway import (GatewayError, GatewayService,
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
        raise AssertionError(operation)


def test_service_verifies_identity_and_normalizes_contract():
    service = GatewayService(FakeBridge(), expected_last4="1131", cache_seconds=0)
    assert service.health()["read_only"] is True
    assert service.health()["market_open"] is False
    assert service.account()["account_number_last4"] == "1131"
    assert service.positions()["positions"][0]["symbol"] == "VTI"
    assert service.quote("vti")["price"] == 321.45
    assert service.quote("vti")["source"] == "robinhood-trading-mcp"


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


def test_quote_identity_ambiguity_and_freshness_fail_closed():
    with pytest.raises(GatewayError, match="does not match"):
        _validate_upstream_payload("quote", raw_quote("MSFT"), {"symbol": "NVDA"})
    ambiguous = raw_quote()
    ambiguous["data"]["results"].append(ambiguous["data"]["results"][0])
    with pytest.raises(GatewayError, match="ambiguous"):
        _validate_upstream_payload("quote", ambiguous, {"symbol": "NVDA"})
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
