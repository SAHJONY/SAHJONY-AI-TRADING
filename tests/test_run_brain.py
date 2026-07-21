from datetime import datetime, timedelta, timezone

import numpy as np

from config import Config
from intelligence.historical_data import HistoricalEquityBars
from run_brain import ReadOnlyBroker, run_analysis


class BrokerTripwire:
    online = True
    mode = "live-data"
    identity_verified = True
    trading_armed = False
    execution_authority = False

    def __init__(self, quote_time=None):
        self.quote_time = quote_time or datetime.now(timezone.utc)
        self.order_calls = []

    def get_account(self):
        return {"equity": 10_000, "cash": 8_000, "buying_power": 8_000}

    def get_broker_positions(self):
        return {}

    def get_history(self, symbol, days=250):
        raise AssertionError("Robinhood history must never be used")

    def get_quote_snapshot(self, symbol):
        return {"price": 110.0, "exchange_timestamp": self.quote_time.isoformat()}

    def _order(self, *args, **kwargs):
        self.order_calls.append((args, kwargs))
        raise AssertionError("analysis runner called an order method")

    submit_equity_order = _order
    submit_option_order = _order
    preview_order = _order
    modify_order = _order
    cancel_order = _order


def config():
    return Config(broker="robinhood_mcp", tickers=["AAPL"], benchmark="SPY",
                  ai_brain_enabled=False, auto_update_models=False)


class HistoryProvider:
    def __init__(self, at=None):
        self.at = at or datetime.now(timezone.utc)

    def get_equity_bars(self, symbol, lookback_days):
        timestamps = tuple(self.at - timedelta(days=249 - index) for index in range(250))
        return HistoricalEquityBars(
            symbol, tuple(np.linspace(90, 110, 250)), tuple(np.full(250, 1_000.0)),
            timestamps, self.at, timestamps[-1], timestamps[-1], "test",
        )


def test_analysis_runner_never_exposes_or_calls_order_methods(tmp_path):
    broker = BrokerTripwire()
    assert not hasattr(ReadOnlyBroker(broker), "submit_equity_order")

    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")

    assert broker.order_calls == []
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert result["orders"] == []
    assert result["decisions"][0]["action"] == "OBSERVE_ONLY"
    assert result["data_ready"] is True
    assert result["positions_reconciled"] is True


def test_stale_quote_fails_closed_without_order_calls(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    broker = BrokerTripwire(now - timedelta(hours=1))
    monkeypatch.setenv("BRAIN_MAX_QUOTE_AGE_SECONDS", "60")

    result = run_analysis(config(), broker, state={"positions": {}}, now=now,
                          historical_provider=HistoryProvider(now),
                          status_path=tmp_path / "brain.json")

    assert result["data_ready"] is False
    assert result["decisions"][0]["eligible"] is False
    assert "AAPL: stale quote" in result["blockers"]
    assert broker.order_calls == []


def test_identity_and_reconciliation_fail_closed(tmp_path):
    broker = BrokerTripwire()
    broker.identity_verified = False
    broker.get_broker_positions = lambda: {"MSFT": {"qty": 2, "market_value": 200}}

    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")

    assert result["data_ready"] is False
    assert result["positions_reconciled"] is False
    assert all(d["action"] == "OBSERVE_ONLY" and not d["eligible"] for d in result["decisions"])
    assert result["reconciliation"]["difference_count"] == 1
    assert "differences" not in result["reconciliation"]
    assert broker.order_calls == []


def test_missing_benchmark_quote_marks_data_not_ready(tmp_path):
    broker = BrokerTripwire()
    original = broker.get_quote_snapshot
    broker.get_quote_snapshot = lambda symbol: (_ for _ in ()).throw(RuntimeError()) \
        if symbol == "SPY" else original(symbol)

    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")

    assert result["data_ready"] is False
    assert result["quote_freshness"]["SPY"]["fresh"] is False
    assert broker.order_calls == []


def test_robinhood_never_falls_back_to_broker_history(tmp_path):
    broker = BrokerTripwire()

    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=None, status_path=tmp_path / "brain.json")

    assert result["data_ready"] is False
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert result["decisions"][0]["action"] == "OBSERVE_ONLY"
