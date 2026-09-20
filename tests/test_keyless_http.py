"""Tests for intel/keyless_http.py — fully offline, no real network.

A fake transport (scripted responses / exceptions) plus a fake clock stand in
for the network, so pacing and backoff timing are asserted deterministically.
Plus parity tests proving the migrated engines (intel/news.py,
intel/onchain.py) produce the same payloads and the same errors/stale
semantics as before, through the shared client.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import news, onchain as oc  # noqa: E402
from intel.keyless_http import (  # noqa: E402
    DEFAULT_HOST_RATE,
    HostRate,
    KeylessHttpClient,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeClock:
    """Deterministic clock: sleep() advances time instead of blocking."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        assert s >= 0, f"negative sleep {s}"
        self.sleeps.append(s)
        self.now += s


class FakeResponse:
    def __init__(self, status: int = 200, text: str = "", headers: dict | None = None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class FakeTransport:
    """Scripted transport: pops a FakeResponse or raises the scripted exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        assert self.script, "transport script exhausted"
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _j(resp: dict, status: int = 200, headers: dict | None = None) -> FakeResponse:
    return FakeResponse(status, json.dumps(resp), headers)


def _client(script, host: str = "h.test", rate: float = 100.0, burst: int = 100,
            **kw) -> tuple[KeylessHttpClient, FakeClock, FakeTransport]:
    clock = FakeClock()
    transport = FakeTransport(script)
    client = KeylessHttpClient(
        rates={host: HostRate(rate, burst)},
        transport=transport,
        time_fn=clock.monotonic,
        sleep_fn=clock.sleep,
        jitter_s=0.0,  # deterministic backoff timing
        **kw,
    )
    return client, clock, transport


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

def test_token_bucket_spaces_a_burst():
    client, clock, transport = _client([FakeResponse(200, "ok")] * 3,
                                      rate=1.0, burst=1)
    for _ in range(3):
        res = client.get("http://h.test/x")
        assert res.ok
    assert clock.sleeps == pytest.approx([1.0, 1.0])  # 1 token per second
    assert len(transport.calls) == 3


def test_token_bucket_honors_burst_capacity():
    client, clock, transport = _client([FakeResponse(200, "ok")] * 4,
                                      rate=1.0, burst=3)
    for _ in range(3):
        assert client.get("http://h.test/x").ok
    assert clock.sleeps == []  # first three ride the burst
    assert client.get("http://h.test/x").ok
    assert clock.sleeps == pytest.approx([1.0])  # fourth must wait


def test_token_bucket_refills_over_time():
    client, clock, transport = _client([FakeResponse(200, "ok")] * 2,
                                      rate=2.0, burst=1)
    assert client.get("http://h.test/x").ok
    clock.sleep(1.0)  # two tokens refill at 2/s
    assert client.get("http://h.test/x").ok
    assert clock.sleeps == [1.0]  # only the manual advance


def test_per_host_rates_and_default_rate():
    client, _, _ = _client([])  # only h.test is overridden here
    assert client._rate_for("api.coingecko.com") == HostRate(0.5, 1)
    assert client._rate_for("some.unknown.host") == DEFAULT_HOST_RATE
    custom = KeylessHttpClient(rates={"api.coingecko.com": HostRate(0.2, 1)},
                              transport=FakeTransport([]))
    assert custom._rate_for("api.coingecko.com") == HostRate(0.2, 1)


# ---------------------------------------------------------------------------
# Backoff / retry policy
# ---------------------------------------------------------------------------

def test_429_backoff_is_exponential_then_success():
    script = [FakeResponse(429), FakeResponse(429), _j({"a": 1})]
    client, clock, transport = _client(script, max_retries=3, base_backoff_s=1.0,
                                      backoff_cap_s=60.0)
    res = client.get_json("http://h.test/x")
    assert res.ok
    assert res.payload == {"a": 1}
    assert res.attempts == 3
    assert res.retried is True
    assert res.rate_limited is True
    assert clock.sleeps == pytest.approx([1.0, 2.0])  # 1s, then 2s
    assert res.total_wait_ms == pytest.approx(3000.0)


def test_max_retries_exhausted_returns_structured_error_never_raises():
    script = [FakeResponse(429)] * 10
    client, clock, transport = _client(script, max_retries=2, base_backoff_s=1.0)
    res = client.get_json("http://h.test/x")
    assert res.ok is False
    assert res.status == 429
    assert res.attempts == 3  # 1 initial + 2 retries
    assert res.rate_limited is True
    assert clock.sleeps == pytest.approx([1.0, 2.0])
    assert res.total_wait_ms == pytest.approx(3000.0)
    # Structured error: status code, host, attempts, total wait.
    assert "429" in res.error
    assert "h.test" in res.error
    assert "3 attempt" in res.error
    assert "3.0s" in res.error


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_4xx_other_than_429_never_retries(status):
    client, clock, transport = _client([FakeResponse(status, "nope")] * 5)
    res = client.get("http://h.test/x")
    assert res.ok is False
    assert res.status == status
    assert res.attempts == 1  # no retry
    assert clock.sleeps == []
    assert str(status) in res.error
    assert "not retryable" in res.error


def test_500_is_retried():
    client, clock, _ = _client([FakeResponse(500), FakeResponse(200, "fine")],
                              max_retries=3, base_backoff_s=1.0)
    res = client.get("http://h.test/x")
    assert res.ok is True
    assert res.attempts == 2
    assert clock.sleeps == pytest.approx([1.0])


def test_transient_timeout_is_retried_then_exhausts_never_raises():
    script = [requests.ConnectTimeout("connect timed out")] * 5
    client, clock, transport = _client(script, max_retries=2, base_backoff_s=1.0)
    res = client.get("http://h.test/x")
    assert res.ok is False
    assert res.status is None
    assert res.attempts == 3
    assert "ConnectTimeout" in res.error
    assert clock.sleeps == pytest.approx([1.0, 2.0])
    # Explicit bounded (connect, read) timeout on every attempt.
    assert transport.calls[0]["timeout"] == (5.0, 15.0)


def test_scalar_timeout_maps_to_connect_read_tuple():
    client, _, transport = _client([FakeResponse(200, "ok")])
    client.get("http://h.test/x", timeout=20)
    assert transport.calls[0]["timeout"] == (5.0, 20.0)


def test_retry_after_honored_but_capped():
    # Absurd Retry-After (300s) is capped by backoff_cap_s.
    script = [FakeResponse(429, headers={"Retry-After": "300"}), _j({"ok": True})]
    client, clock, _ = _client(script, max_retries=1, base_backoff_s=1.0,
                              backoff_cap_s=15.0)
    res = client.get_json("http://h.test/x")
    assert res.ok
    assert clock.sleeps == pytest.approx([15.0])


def test_small_retry_after_does_not_shorten_exponential_wait():
    # A Retry-After below the exponential wait is honored as the floor's
    # challenger, not a shortener: the server asked us to back off, so we
    # wait at least the exponential step.
    script = [FakeResponse(429, headers={"Retry-After": "0.5"}), _j({"ok": True})]
    client, clock, _ = _client(script, max_retries=1, base_backoff_s=1.0)
    res = client.get_json("http://h.test/x")
    assert res.ok
    assert clock.sleeps == pytest.approx([1.0])


def test_max_total_wait_is_bounded():
    client, clock, _ = _client([FakeResponse(429)] * 5, max_retries=5,
                              base_backoff_s=10.0, max_total_wait_s=2.5)
    res = client.get("http://h.test/x")
    assert res.ok is False
    assert res.attempts == 1  # the first retry's 10s wait exceeds the budget
    assert res.total_wait_ms == 0.0
    assert "wait budget" in res.error


def test_invalid_json_is_structured_failure_never_raises():
    client, _, _ = _client([FakeResponse(200, "this is not json {{{")])
    res = client.get_json("http://h.test/x")
    assert res.ok is False
    assert res.status == 200
    assert "invalid JSON" in res.error
    assert res.payload is None


def test_user_agent_sent_not_a_credential():
    client, _, transport = _client([FakeResponse(200, "ok")])
    client.get("http://h.test/x")
    headers = transport.calls[0]["headers"]
    assert headers["User-Agent"].startswith("SAHJONY-Capital/")


def test_thread_safe_concurrent_use():
    script = [FakeResponse(200, "ok")] * 40
    client, _, transport = _client(script, rate=1000.0, burst=1000)
    results: list = []
    errors: list = []

    def worker():
        try:
            for _ in range(5):
                results.append(client.get("http://h.test/x"))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(results) == 40
    assert all(r.ok and r.attempts == 1 for r in results)
    assert len(transport.calls) == 40


# ---------------------------------------------------------------------------
# Engine parity fixtures (same shapes as the engines' own test suites)
# ---------------------------------------------------------------------------

FNG_FIXTURE = {
    "name": "Fear and Greed Index",
    "data": [
        {"value": "71", "value_classification": "Greed", "timestamp": "1789862400"},
        {"value": "56", "value_classification": "Greed", "timestamp": "1789689600"},
        {"value": "57", "value_classification": "Greed", "timestamp": "1789344000"},
    ],
}

GDELT_FIXTURE = {
    "timeline": [
        {"series": "Search Results",
         "data": [
             {"date": "20260913000000", "volume": 100},
             {"date": "20260914000000", "volume": 110},
             {"date": "20260915000000", "volume": 90},
             {"date": "20260916000000", "volume": 105},
             {"date": "20260917000000", "volume": 115},
             {"date": "20260918000000", "volume": 100},
             {"date": "20260919000000", "volume": 400},
         ]},
    ]
}

TRENDING_FIXTURE = {
    "coins": [
        {"item": {"id": "zcoin", "name": "Firo", "symbol": "FIRO",
                  "market_cap_rank": 812}},
        {"item": {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC",
                  "market_cap_rank": 1}},
    ],
}

FEES_FIXTURE = {"fastestFee": 2, "halfHourFee": 1, "hourFee": 1}

MEMPOOL_BLOCKS_FIXTURE = [
    {"blockVSize": 997998.0, "medianFee": 1.10},
    {"blockVSize": 997966.0, "medianFee": 0.34},
    {"blockVSize": 997998.0, "medianFee": 0.32},
    {"blockVSize": 33358667.0, "medianFee": 0.12},  # catch-all, excluded
]

HASHRATE_FIXTURE = {
    "values": [
        {"x": 1787529600, "y": 8.880543248996867e8},
        {"x": 1787616000, "y": 9.505933618644534e8},
        {"x": 1787702400, "y": 9.130699396855934e8},
    ],
}

DIFFICULTY_FIXTURE = {
    "values": [
        {"x": 1787529600, "y": 1.25807076547198e14},
        {"x": 1787616000, "y": 1.25807076547198e14},
        {"x": 1787702400, "y": 1.2580707654719811e14},
    ],
}


def _engine_client(script, hosts: tuple[str, ...]):
    """Client for a migrated engine: fast clocks, generous buckets (no pacing
    waits in tests), jitter off."""
    clock = FakeClock()
    transport = FakeTransport(script)
    client = KeylessHttpClient(
        rates={h: HostRate(100.0, 100) for h in hosts},
        transport=transport,
        time_fn=clock.monotonic,
        sleep_fn=clock.sleep,
        jitter_s=0.0,
    )
    return client, transport


# ---------------------------------------------------------------------------
# news.py parity (through the shared client)
# ---------------------------------------------------------------------------

_NEWS_HOSTS = ("api.alternative.me", "api.gdelt.org", "api.coingecko.com")


def test_news_parity_success_same_outputs(monkeypatch, tmp_path):
    script = [
        _j(FNG_FIXTURE),
        _j(GDELT_FIXTURE), _j(GDELT_FIXTURE), _j(GDELT_FIXTURE),
        _j(TRENDING_FIXTURE),
    ]
    client, _ = _engine_client(script, _NEWS_HOSTS)
    monkeypatch.setattr(news, "_HTTP", client)

    payload = news.refresh(out_path=tmp_path / "news.json")

    assert payload["stale"] is False
    assert payload["errors"] == []
    fg = payload["fear_greed"]
    assert fg["value"] == 71.0
    assert fg["classification"] == "Greed"
    assert fg["delta_7d"] == 14.0  # 71 - 57
    assert len(fg["history"]) == 3
    btc = next(e for e in payload["news_volume"] if e["query"] == "bitcoin")
    assert btc["count_24h"] == 400.0
    assert btc["spike"] is True  # 400 vs ~145.7 avg
    assert [c["symbol"] for c in payload["trending_coins"]] == ["FIRO", "BTC"]
    read = payload["sentiment_read"]
    assert read["fear_greed_label"] == "greed"
    assert read["bias"] == "cautious"
    assert "bitcoin" in read["spike_queries"]
    assert payload["schema_version"] == 1
    assert news.load_payload(tmp_path / "news.json")["ts"] == payload["ts"]


def test_news_parity_total_failure_same_error_semantics(monkeypatch, tmp_path):
    client, _ = _engine_client(
        [requests.ConnectTimeout("network down")] * 30, _NEWS_HOSTS)
    monkeypatch.setattr(news, "_HTTP", client)

    payload = news.refresh(out_path=tmp_path / "news.json")

    assert payload["stale"] is True
    assert len(payload["errors"]) == 5  # fng + 3 gdelt + trending, each isolated
    assert payload["errors"][0].startswith("fear_greed: ")
    assert "ConnectTimeout" in payload["errors"][0]
    assert payload["fear_greed"] == {"value": None, "classification": None,
                                    "delta_7d": None, "history": []}
    assert payload["trending_coins"] == []
    assert all(e["count_24h"] is None for e in payload["news_volume"])


def test_news_429_backoff_then_success(monkeypatch, tmp_path):
    """The recurring CoinGecko 429 now backs off instead of failing the source."""
    script = [
        _j(FNG_FIXTURE),
        _j(GDELT_FIXTURE), _j(GDELT_FIXTURE), _j(GDELT_FIXTURE),
        FakeResponse(429), FakeResponse(429), _j(TRENDING_FIXTURE),
    ]
    client, transport = _engine_client(script, _NEWS_HOSTS)
    monkeypatch.setattr(news, "_HTTP", client)

    payload = news.refresh(out_path=tmp_path / "news.json")

    assert payload["stale"] is False  # recovered — no error recorded
    assert payload["errors"] == []
    assert [c["symbol"] for c in payload["trending_coins"]] == ["FIRO", "BTC"]
    trending_calls = [c for c in transport.calls if "trending" in c["url"]]
    assert len(trending_calls) == 3  # 1 initial + 2 backoff retries


def test_news_helper_still_raises_structured_error(monkeypatch):
    client, _ = _engine_client([FakeResponse(404, "gone")], _NEWS_HOSTS)
    monkeypatch.setattr(news, "_HTTP", client)
    with pytest.raises(RuntimeError, match="404"):
        news.fetch_trending_coins()


# ---------------------------------------------------------------------------
# onchain.py parity (through the shared client)
# ---------------------------------------------------------------------------

_ONCHAIN_HOSTS = ("mempool.space", "api.blockchain.info")


def test_onchain_parity_success_same_outputs(monkeypatch, tmp_path):
    script = [
        _j(FEES_FIXTURE),
        _j(MEMPOOL_BLOCKS_FIXTURE),
        FakeResponse(200, "967776"),
        _j(HASHRATE_FIXTURE),
        _j(DIFFICULTY_FIXTURE),
    ]
    client, _ = _engine_client(script, _ONCHAIN_HOSTS)
    monkeypatch.setattr(oc, "_HTTP", client)

    payload = oc.refresh(out_path=tmp_path / "onchain.json")

    assert payload["stale"] is False
    assert payload["errors"] == []
    assert payload["fees"]["fastest_sat_vb"] == 2.0
    assert payload["fees"]["fee_pressure"] == "calm"
    mempool = payload["mempool"]
    assert mempool["tip_height"] == 967776
    assert mempool["full_projected_blocks"] == 3  # catch-all excluded
    assert mempool["congestion"] == "moderate"  # 3-5 full blocks = moderate
    hr = payload["network"]["hashrate_th_s"]
    assert hr["latest"] == pytest.approx(9.130699396855934e8)
    assert hr["change_30d_pct"] == pytest.approx(2.82, rel=1e-3)
    assert payload["chain_read"]["label"] == "steady"
    assert payload["schema_version"] == 1
    assert oc.load_payload(tmp_path / "onchain.json")["ts"] == payload["ts"]


def test_onchain_parity_total_failure_same_error_semantics(monkeypatch, tmp_path):
    client, _ = _engine_client(
        [requests.ConnectTimeout("network down")] * 30, _ONCHAIN_HOSTS)
    monkeypatch.setattr(oc, "_HTTP", client)

    payload = oc.refresh(out_path=tmp_path / "onchain.json")

    assert payload["stale"] is True
    assert len(payload["errors"]) == 3  # fees, mempool, network each isolated
    assert payload["errors"][0].startswith("fees: ")
    assert "ConnectTimeout" in payload["errors"][0]
    assert payload["fees"] == {}
    assert payload["chain_read"]["label"] == "steady"  # neutral, never invented


def test_onchain_text_helper_strips_and_raises(monkeypatch):
    client, _ = _engine_client([FakeResponse(200, "  967776\n")], _ONCHAIN_HOSTS)
    monkeypatch.setattr(oc, "_HTTP", client)
    assert oc._http_get_text("http://x/tip", timeout=15) == "967776"

    bad_client, _ = _engine_client([FakeResponse(503, "down")] * 5, _ONCHAIN_HOSTS)
    monkeypatch.setattr(oc, "_HTTP", bad_client)
    with pytest.raises(RuntimeError, match="503"):
        oc._http_get_text("http://x/tip", timeout=15)
