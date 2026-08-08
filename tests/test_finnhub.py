import importlib.util
import json
from pathlib import Path

import pytest

from market_data.finnhub import FinnhubClient, FinnhubError


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_quote_is_normalized_and_read_only():
    seen = []

    def opener(req, **_kwargs):
        seen.append(req.full_url)
        return Response({"c": 201.5, "d": 1.5, "dp": 0.75, "h": 202,
                         "l": 199, "o": 200, "pc": 200, "t": 1786070000})

    client = FinnhubClient("top-secret", opener=opener)
    quote = client.quote("aapl")
    assert quote["symbol"] == "AAPL"
    assert quote["source"] == "finnhub"
    assert quote["c"] == 201.5
    assert "token=top-secret" in seen[0]
    assert not hasattr(client, "submit_order")


def test_key_is_never_exposed_in_transport_error():
    def opener(*_args, **_kwargs):
        raise RuntimeError("network unavailable")

    with pytest.raises(FinnhubError) as raised:
        FinnhubClient("top-secret", opener=opener).quote("AAPL")
    assert "top-secret" not in str(raised.value)


@pytest.mark.parametrize("symbol", ["", "BTC/USD", "AAPL&token=bad", "AAPL MSFT"])
def test_invalid_or_ambiguous_symbols_fail_closed(symbol):
    with pytest.raises(FinnhubError, match="symbol"):
        FinnhubClient("key", opener=lambda *_a, **_k: Response({})).quote(symbol)


def test_zero_or_missing_quote_fails_closed():
    with pytest.raises(FinnhubError, match="price"):
        FinnhubClient("key", opener=lambda *_a, **_k: Response({"c": 0, "t": 1})).quote("AAPL")


SPEC = importlib.util.spec_from_file_location("finnhub_api", Path("api/finnhub.py"))
API = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(API)


class FakeClient:
    def quote(self, symbol):
        return {"symbol": symbol, "c": 1}


def test_proxy_route_allowlists_actions():
    payload, max_age = API.route({"action": ["quote"], "symbol": ["AAPL"]}, FakeClient())
    assert payload == {"symbol": "AAPL", "c": 1}
    assert max_age == 30
    with pytest.raises(FinnhubError, match="unsupported"):
        API.route({"action": ["orders"]}, FakeClient())
