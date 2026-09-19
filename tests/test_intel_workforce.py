"""Intel Workforce tests — plain pytest, no live network.

Covers the 8 agents (active + abstain paths), the IntelFinding clamp
honesty discipline, desk-level fault isolation, and the RiskOfficer
de-risk-only guarantee. All HTTP and the sibling top-traders module are
stubbed or monkeypatched — nothing here touches the network.
"""
from __future__ import annotations

import math
import sys
import types

import pytest
import requests

from intel.workforce import (
    ALL_INTEL_AGENTS,
    CopySignalScout,
    ExecutionOptimizer,
    IntelAgent,
    IntelDesk,
    IntelFinding,
    MacroAnalyst,
    QuantResearcher,
    RegimeAnalyst,
    RiskOfficer,
    SentimentAnalyst,
    WhaleWatcher,
)


# ── mocks ────────────────────────────────────────────────────────────────────
class MockClient:
    """get_history raises when a symbol's feed is down or absent."""

    def __init__(self, histories=None):
        self._hist = histories or {}

    def get_history(self, symbol, n=60):
        closes = self._hist.get(symbol)
        if closes is None:
            raise RuntimeError(f"no history for {symbol}")
        return {"closes": closes, "volumes": [1e6] * len(closes)}

    def get_price(self, symbol):
        return 100.0

    def get_account(self):
        return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}


class MockDB:
    def __init__(self, trades=None, equity=None):
        self._trades = trades if trades is not None else []
        self._equity = equity if equity is not None else []

    def recent_trades(self, limit=25):
        return self._trades[:limit]

    def equity_history_regime(self, limit=500):
        return self._equity[:limit]


def make_ctx(client=None, db=None, state=None, cfg=None, tickers=None,
             reconciliation=None):
    return {
        "client": client or MockClient(),
        "db": db or MockDB(),
        "state": state if state is not None else {},
        "cfg": cfg,
        "tickers": tickers if tickers is not None else ["BTC/USD"],
        "research": [],
        "reconciliation": reconciliation,
    }


@pytest.fixture
def fake_top_traders(monkeypatch):
    """Stub the sibling intel/top_traders.py against its published contract.

    load_payload -> dict ({} when missing); summary_for_status(payload) ->
    dict; refresh -> dict. Each test overrides load_payload as needed.
    """
    mod = types.ModuleType("intel.top_traders")
    mod.load_payload = lambda path=None: {}
    mod.summary_for_status = lambda payload: {"available": bool(payload)}
    mod.refresh = lambda out_path=None, cache_path=None: {}
    monkeypatch.setitem(sys.modules, "intel.top_traders", mod)
    return mod


def _uptrend(n=60, drift=0.003):
    return [100.0 * (1.0 + drift) ** i for i in range(n)]


def _downtrend(n=60, drift=-0.004):
    return [100.0 * (1.0 + drift) ** i for i in range(n)]


def _choppy():
    return [100.0 + (5.0 if i % 2 == 0 else -5.0) for i in range(60)]


# ── roster ───────────────────────────────────────────────────────────────────
def test_all_nine_agents_registered():
    assert len(ALL_INTEL_AGENTS) == 9
    names = [a.name for a in ALL_INTEL_AGENTS]
    assert names == [
        "Regime Analyst", "Whale Watcher", "Sentiment Analyst", "Macro Analyst",
        "Risk Officer", "Quant Researcher", "Execution Optimizer",
        "Copy-Signal Scout", "Funding-Rate Intel",
    ]


# ── clamp honesty ────────────────────────────────────────────────────────────
def test_clamp_nonfinite_fails_to_neutral():
    for bad in (float("nan"), float("inf"), float("-inf")):
        f = IntelFinding(
            name="x", role="r", status="active", finding="f",
            conviction_delta=bad, confidence=bad, rationale="r",
            inputs=[], ts="t").clamp()
        assert f.conviction_delta == 0.0, bad
        assert f.confidence == 0.0, bad


def test_clamp_bounds():
    f = IntelFinding(
        name="x", role="r", status="active", finding="f",
        conviction_delta=2.5, confidence=1.5, rationale="r",
        inputs=[], ts="t").clamp()
    assert f.conviction_delta == 1.0
    assert f.confidence == 1.0


def test_abstain_zeroes_delta_and_confidence():
    f = IntelAgent().abstain("feed down")
    assert f.status == "abstained"
    assert f.conviction_delta == 0.0
    assert f.confidence == 0.0
    assert f.abstain_reason == "feed down"
    d = f.as_dict()
    assert set(d) >= {"name", "role", "status", "finding", "conviction_delta",
                      "confidence", "rationale", "inputs", "ts", "abstain_reason"}


# ── 1) RegimeAnalyst ─────────────────────────────────────────────────────────
def test_regime_analyst_active_uptrend():
    client = MockClient({"BTC/USD": _uptrend(), "ETH/USD": _choppy()})
    f = RegimeAnalyst().evaluate(make_ctx(client=client,
                                          tickers=["BTC/USD", "ETH/USD"]))
    assert f.status == "active"
    assert f.conviction_delta > 0
    assert f.inputs == ["client.get_history"]
    assert "BTC/USD uptrend" in f.finding
    assert 0.0 <= f.confidence <= 1.0


def test_regime_analyst_active_downtrend():
    client = MockClient({"BTC/USD": _downtrend()})
    f = RegimeAnalyst().evaluate(make_ctx(client=client, tickers=["BTC/USD"]))
    assert f.status == "active"
    assert f.conviction_delta < 0


def test_regime_analyst_abstains_on_feed_failure():
    client = MockClient({})  # every symbol raises
    f = RegimeAnalyst().evaluate(make_ctx(client=client, tickers=["BTC/USD"]))
    assert f.status == "abstained"
    assert f.conviction_delta == 0.0
    assert f.abstain_reason


def test_regime_analyst_abstains_on_empty_tickers():
    f = RegimeAnalyst().evaluate(make_ctx(client=MockClient(), tickers=[]))
    assert f.status == "abstained"


# ── 2) WhaleWatcher ─────────────────────────────────────────────────────────
def test_whale_watcher_active(fake_top_traders):
    fake_top_traders.load_payload = lambda path=None: {
        "alerts": [
            {"trader": "whale_a", "symbol": "BTC/USD", "side": "buy", "size_usd": 500000},
            {"trader": "whale_b", "symbol": "ETH/USD", "side": "sell", "size_usd": 200000},
        ]}
    f = WhaleWatcher().evaluate(make_ctx())
    assert f.status == "active"
    assert f.conviction_delta == pytest.approx(0.0)  # one buy + one sell cancel
    assert "2 whale alert(s)" in f.finding


def test_whale_watcher_small_net_delta(fake_top_traders):
    fake_top_traders.load_payload = lambda path=None: {
        "alerts": [{"symbol": "BTC/USD", "side": "buy"} for _ in range(4)]}
    f = WhaleWatcher().evaluate(make_ctx())
    assert f.status == "active"
    assert f.conviction_delta == pytest.approx(0.25)  # small by design (<=0.25)


def test_whale_watcher_abstains_on_missing_payload(fake_top_traders):
    f = WhaleWatcher().evaluate(make_ctx())  # load_payload -> {}
    assert f.status == "abstained"
    assert f.conviction_delta == 0.0


def test_whale_watcher_sibling_alert_schema(fake_top_traders):
    """The sibling's real whale_alerts carry asset/amount_usd with no direction:
    the finding summarizes the flow with no directional tilt."""
    fake_top_traders.load_payload = lambda path=None: {
        "whale_alerts": [
            {"asset": "BTC", "amount_usd": 1200000.0, "amount_btc": 12.0,
             "txid": "abc", "from": None, "to": None, "ts": "t",
             "source": "mempool.space"},
            {"asset": "BTC", "amount_usd": 900000.0, "amount_btc": 9.0,
             "txid": "def", "ts": "t", "source": "mempool.space"},
        ]}
    f = WhaleWatcher().evaluate(make_ctx())
    assert f.status == "active"
    assert f.conviction_delta == 0.0  # no direction data -> no tilt
    assert "$2,100,000 total moved" in f.finding


def test_whale_watcher_abstains_when_module_absent(monkeypatch):
    # None in sys.modules makes `from intel.top_traders import ...` raise
    # ImportError — a true simulation of the sibling module being unavailable.
    monkeypatch.setitem(sys.modules, "intel.top_traders", None)
    f = WhaleWatcher().evaluate(make_ctx())
    assert f.status == "abstained"


# ── 3) SentimentAnalyst ─────────────────────────────────────────────────────
class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_sentiment_active(monkeypatch):
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _Resp({"articles": [{}] * 14}))
    f = SentimentAnalyst().evaluate(make_ctx(tickers=["BTC/USD", "ETH/USD"]))
    assert f.status == "active"
    assert f.conviction_delta == 0.0  # buzz is volume, never directional
    assert "BTC 14 article(s)" in f.finding
    assert "NOT" in f.finding  # labels itself as not-true-sentiment


def test_sentiment_abstains_when_feed_down(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("gdelt unreachable")
    monkeypatch.setattr(requests, "get", _boom)
    f = SentimentAnalyst().evaluate(make_ctx(tickers=["BTC/USD"]))
    assert f.status == "abstained"
    assert f.conviction_delta == 0.0
    assert f.abstain_reason


# ── 4) MacroAnalyst ──────────────────────────────────────────────────────────
def _macro_mocks(monkeypatch):
    def _get(url, *a, **k):
        if "coingecko" in url:
            return _Resp({"data": {"market_cap_percentage": {"btc": 58.2}}})
        if "alternative.me" in url:
            return _Resp({"data": [{"value": "72", "value_classification": "Greed"}]})
        raise AssertionError(f"unexpected GET {url}")

    def _post(url, *a, **k):
        assert "hyperliquid" in url
        # per-hour funding 0.0002 (0.02%/h) across two assets -> mildly crowded longs
        return _Resp([{"universe": [{"name": "BTC"}, {"name": "ETH"}]},
                      [{"funding": "0.0002"}, {"funding": "0.0002"}]])

    monkeypatch.setattr(requests, "get", _get)
    monkeypatch.setattr(requests, "post", _post)


def test_macro_active_partial_and_full(monkeypatch):
    _macro_mocks(monkeypatch)
    f = MacroAnalyst().evaluate(make_ctx())
    assert f.status == "active"
    assert f.inputs == ["CoinGecko BTC dominance", "Hyperliquid funding",
                        "fear/greed index"]
    assert "58.2%" in f.finding and "72" in f.finding
    # greed 72 -> -0.12, funding 0.0002/h -> -0.06 => -0.18 total
    assert f.conviction_delta == pytest.approx(-0.18)


def test_macro_drops_failed_feeds(monkeypatch):
    def _get(url, *a, **k):
        if "alternative.me" in url:
            return _Resp({"data": [{"value": "25", "value_classification": "Fear"}]})
        raise ConnectionError("down")

    def _post(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(requests, "get", _get)
    monkeypatch.setattr(requests, "post", _post)
    f = MacroAnalyst().evaluate(make_ctx())
    assert f.status == "active"
    assert f.inputs == ["fear/greed index"]
    assert "Dropped this cycle" in f.finding
    assert f.conviction_delta == pytest.approx(0.12)  # fear 25 -> +0.12


def test_macro_abstains_when_all_feeds_down(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("everything down")
    monkeypatch.setattr(requests, "get", _boom)
    monkeypatch.setattr(requests, "post", _boom)
    f = MacroAnalyst().evaluate(make_ctx())
    assert f.status == "abstained"
    assert f.conviction_delta == 0.0
    assert "all macro feeds unreachable" in f.abstain_reason


# ── 5) RiskOfficer ──────────────────────────────────────────────────────────
def test_risk_officer_clear_book(cfg):
    state = {"equity_last": 1000.0, "equity_day_start": 1000.0, "positions": {}}
    f = RiskOfficer().evaluate(make_ctx(state=state, cfg=cfg))
    assert f.status == "active"
    assert f.conviction_delta <= 0
    assert "All independent checks clear" in f.finding
    assert "ADVISORY ONLY" in f.finding


def test_risk_officer_never_positive_even_when_everything_fine(cfg):
    # belt and braces: no input combination may produce a positive delta
    for state in [
        {"equity_last": 1000.0, "equity_day_start": 900.0, "positions": {}},
        {"equity_last": 0.0, "equity_day_start": 0.0, "positions": {}},
        {"positions": {}},
    ]:
        f = RiskOfficer().evaluate(make_ctx(state=state, cfg=cfg))
        assert f.conviction_delta <= 0, state


def test_risk_officer_derisks_on_breaches(cfg):
    state = {
        "equity_last": 1000.0,
        "equity_day_start": 1050.0,      # -4.76% day, limit 6% -> near-breaker
        "breaker_latched": True,
        "positions": {"BTC/USD": {"shares": 10.0, "cost_basis": 90.0}},  # 90% deployed
    }
    f = RiskOfficer().evaluate(make_ctx(state=state, cfg=cfg,
                                        reconciliation={"status": "mismatch",
                                                        "reconciled": False}))
    assert f.status == "active"
    assert f.conviction_delta < 0
    assert len(f.details["advisories"]) >= 3  # exposure, breaker, recon (+drawdown)


def test_risk_officer_abstains_without_cfg():
    f = RiskOfficer().evaluate(make_ctx(state={}, cfg=None))
    assert f.status == "abstained"


# ── 6) QuantResearcher ──────────────────────────────────────────────────────
def test_quant_researcher_attribution():
    state = {"hermes_events": [
        {"strategy": "ladder", "realized": 12.5},
        {"strategy": "ladder", "realized": -2.5},
        {"strategy": "wheel", "realized": 4.0},
    ]}
    f = QuantResearcher().evaluate(make_ctx(state=state))
    assert f.status == "active"
    assert f.conviction_delta == 0.0
    assert "ladder: 2 event(s), realized $+10.00" in f.finding
    assert "wheel: 1 event(s), realized $+4.00" in f.finding


def test_quant_researcher_falls_back_to_ledger():
    db = MockDB(trades=[{"strategy": "spread"}, {"strategy": "spread"},
                         {"strategy": "ladder"}])
    f = QuantResearcher().evaluate(make_ctx(db=db))
    assert f.status == "active"
    assert "spread: 2 event(s)" in f.finding


def test_quant_researcher_abstains_with_no_history():
    f = QuantResearcher().evaluate(make_ctx())
    assert f.status == "abstained"


# ── 7) ExecutionOptimizer ──────────────────────────────────────────────────
def test_execution_optimizer_active():
    state = {"transaction_costs": 30.0, "premium_collected": 100.0,
             "realized_pnl": -50.0}
    f = ExecutionOptimizer().evaluate(make_ctx(state=state))
    assert f.status == "active"
    assert f.conviction_delta == 0.0
    assert "costs $30.00" in f.finding
    assert "20% of premium collected" in f.finding  # advisory suggestion fires


def test_execution_optimizer_abstains_with_no_data():
    f = ExecutionOptimizer().evaluate(make_ctx(state={}))
    assert f.status == "abstained"


# ── 8) CopySignalScout ──────────────────────────────────────────────────────
def test_copy_signal_scout_active(fake_top_traders):
    fake_top_traders.load_payload = lambda path=None: {
        "copy_signal": {"trader": "alpha_desk", "symbol": "BTC/USD",
                        "direction": "buy", "conviction": 0.8,
                        "reason": "accumulation prints on the tape"}}
    f = CopySignalScout().evaluate(make_ctx())
    assert f.status == "active"
    assert "intelligence only, not auto-copying" in f.finding
    assert f.conviction_delta == pytest.approx(0.2 * 0.8)  # small by design


def test_copy_signal_scout_abstains_without_signal(fake_top_traders):
    fake_top_traders.load_payload = lambda path=None: {"alerts": []}
    f = CopySignalScout().evaluate(make_ctx())
    assert f.status == "abstained"
    assert f.conviction_delta == 0.0


def test_copy_signal_scout_sibling_schema(fake_top_traders):
    """The sibling's real copy_signal uses net_bias/assets: long with BTC 72%
    and ETH 61% long -> strength 0.44 -> delta 0.2 * 0.44."""
    fake_top_traders.load_payload = lambda path=None: {
        "copy_signal": {"label": "INTELLIGENCE ONLY — not auto-copying",
                        "assets": {"BTC": 72.0, "ETH": 61.0},
                        "net_bias": "long", "ts": "t"}}
    f = CopySignalScout().evaluate(make_ctx())
    assert f.status == "active"
    assert "intelligence only, not auto-copying" in f.finding
    assert f.conviction_delta == pytest.approx(0.2 * (22.0 / 50.0))
    assert "BTC 72% long" in f.finding


def test_whale_and_copy_abstain_with_empty_sibling_payload(monkeypatch):
    """Against the REAL sibling module with an empty payload: both agents
    abstain cleanly instead of crashing. The file read is stubbed so the test
    is hermetic regardless of any real public/top_traders.json on disk."""
    import intel.top_traders as tt
    monkeypatch.setattr(tt, "load_payload", lambda path=None: {})
    assert tt.load_payload() == {}
    assert WhaleWatcher().evaluate(make_ctx()).status == "abstained"
    assert CopySignalScout().evaluate(make_ctx()).status == "abstained"


# ── desk fault isolation ────────────────────────────────────────────────────
def test_desk_run_never_raises_even_when_every_agent_explodes(cfg):
    class Boom(IntelAgent):
        name = "Boom"

        def evaluate(self, ctx):
            raise RuntimeError("kaboom")

    class BadReturn(IntelAgent):
        name = "BadReturn"

        def evaluate(self, ctx):
            return "not a finding"

    desk = IntelDesk(cfg)
    desk.agents = [Boom(), BadReturn()]
    findings = desk.run(make_ctx())
    assert len(findings) == 2
    assert all(f.status == "abstained" for f in findings)
    assert all(f.conviction_delta == 0.0 and f.confidence == 0.0
               for f in findings)


def test_desk_run_never_raises_on_none_ctx(cfg):
    desk = IntelDesk(cfg)
    findings = desk.run(None)
    assert len(findings) == 9
    assert all(isinstance(f, IntelFinding) for f in findings)


def test_desk_enforces_derisk_only(cfg):
    class Sneaky(IntelAgent):
        name = "Sneaky"
        derisk_only = True

        def evaluate(self, ctx):
            return IntelFinding(
                name=self.name, role="r", status="active", finding="f",
                conviction_delta=0.9, confidence=1.0, rationale="r",
                inputs=[], ts="t")

    desk = IntelDesk(cfg)
    desk.agents = [Sneaky()]
    f = desk.run(make_ctx())[0]
    assert f.conviction_delta == 0.0


def test_desk_full_run_with_mocks(cfg, monkeypatch, fake_top_traders):
    """All nine agents through the desk with stubbed data sources and no
    network: nothing raises, every finding is well-formed."""
    def _boom(*a, **k):
        raise ConnectionError("network disabled in tests")
    monkeypatch.setattr(requests, "get", _boom)
    monkeypatch.setattr(requests, "post", _boom)

    state = {"equity_last": 1000.0, "equity_day_start": 1000.0,
             "positions": {},
             "hermes_events": [{"strategy": "ladder", "realized": 5.0}],
             "transaction_costs": 1.0, "premium_collected": 10.0,
             "realized_pnl": 5.0}
    client = MockClient({"BTC/USD": _uptrend()})
    findings = IntelDesk(cfg).run(make_ctx(client=client, state=state, cfg=cfg))
    assert len(findings) == 9
    by_name = {f.name: f for f in findings}
    assert by_name["Regime Analyst"].status == "active"
    assert by_name["Risk Officer"].conviction_delta <= 0
    assert by_name["Quant Researcher"].status == "active"
    assert by_name["Execution Optimizer"].status == "active"
    for name in ("Whale Watcher", "Sentiment Analyst", "Macro Analyst",
                 "Copy-Signal Scout"):
        assert by_name[name].status == "abstained", name
        assert by_name[name].conviction_delta == 0.0
    for f in findings:
        assert -1.0 <= f.conviction_delta <= 1.0
        assert 0.0 <= f.confidence <= 1.0
        assert f.ts and f.finding


def test_risk_officer_delta_never_positive_any_agent_path(cfg):
    """End-to-end through the desk: the RiskOfficer finding can never carry a
    positive tilt, whatever the book looks like."""
    desk = IntelDesk(cfg)
    desk.agents = [RiskOfficer()]
    for state in [
        {},
        {"equity_last": 1000.0, "equity_day_start": 1000.0, "positions": {}},
        {"equity_last": 1000.0, "equity_day_start": 1000.0,
         "positions": {"BTC/USD": {"shares": 1.0, "cost_basis": 900.0}}},
    ]:
        f = desk.run(make_ctx(state=state, cfg=cfg))[0]
        assert f.conviction_delta <= 0, state
