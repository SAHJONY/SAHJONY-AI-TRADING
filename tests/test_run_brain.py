from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

import run_brain
from config import Config
from intelligence.historical_data import HistoricalEquityBars
from run_brain import ReadOnlyBroker, run_analysis


class BrokerTripwire:
    online = True
    mode = "live-data"
    identity_verified = True
    trading_armed = False
    execution_authority = False

    def __init__(self, quote_time=None, *, equity=10_000, cash=10_000,
                 positions=None, quote_overrides=None):
        self.quote_time = quote_time or datetime.now(timezone.utc)
        self.equity = equity
        self.cash = cash
        self.positions = positions or {}
        self.quote_overrides = quote_overrides or {}
        self.order_calls = []

    def get_account(self):
        return {"equity": self.equity, "cash": self.cash, "buying_power": self.cash}

    def get_broker_positions(self):
        return self.positions

    def get_history(self, symbol, days=250):
        raise AssertionError("Robinhood history must never be used")

    def get_quote_snapshot(self, symbol):
        return {"symbol": symbol, "price": 110.0, "source": "robinhood-trading-mcp",
                "as_of": self.quote_time.isoformat(), **self.quote_overrides}

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
    assert result["reconciliation"]["execution_blocked"] is True


def test_non_cash_value_with_no_visible_positions_fails_reconciliation(tmp_path):
    broker = BrokerTripwire(equity=25.93, cash=19.99)
    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")
    assert result["positions_reconciled"] is False
    assert result["reconciliation"]["unexplained_value"] == pytest.approx(5.94)
    assert result["reconciliation"]["execution_blocked"] is True


def test_unavailable_broker_snapshot_never_reconciles_empty_positions(tmp_path):
    broker = BrokerTripwire()
    broker.get_account = lambda: (_ for _ in ()).throw(RuntimeError("gateway timeout"))

    result = run_analysis(
        config(), broker, state={"positions": {}},
        historical_provider=HistoryProvider(broker.quote_time),
        status_path=tmp_path / "brain.json",
    )

    assert result["positions_reconciled"] is False
    assert result["reconciliation"]["status"] == "unavailable"
    assert result["reconciliation"]["execution_blocked"] is True
    assert result["reconciliation"]["error"] == "broker snapshot unavailable"
    assert "positions reconciliation unresolved" in result["blockers"]
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert broker.order_calls == []


def test_cash_approximately_equal_to_equity_may_reconcile(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_RECONCILIATION_VALUE_TOLERANCE", "1.00")
    broker = BrokerTripwire(equity=20.49, cash=19.99)
    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")
    assert result["positions_reconciled"] is True


def test_visible_matching_position_and_value_reconcile(tmp_path):
    position = {"AAPL": {"qty": 2, "market_value": 220.0}}
    broker = BrokerTripwire(equity=1_220, cash=1_000, positions=position)
    result = run_analysis(config(), broker, state={"positions": {"AAPL": {"shares": 2}}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")
    assert result["positions_reconciled"] is True


def test_unexplained_value_above_configured_tolerance_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_RECONCILIATION_VALUE_TOLERANCE", "0.25")
    broker = BrokerTripwire(equity=100.26, cash=100.0)
    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")
    assert result["positions_reconciled"] is False
    assert result["reconciliation"]["value_tolerance"] == 0.25


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


@pytest.mark.parametrize("quote_overrides", [
    {"as_of": None},
    {"as_of": "not-a-timestamp"},
    {"as_of": "2026-07-20T12:00:00"},
])
def test_missing_or_invalid_mcp_timestamp_fails_closed(tmp_path, quote_overrides):
    now = datetime.now(timezone.utc)
    broker = BrokerTripwire(now, quote_overrides=quote_overrides)
    result = run_analysis(config(), broker, state={"positions": {}}, now=now,
                          historical_provider=HistoryProvider(now),
                          status_path=tmp_path / "brain.json")
    assert result["data_ready"] is False
    assert result["quote_freshness"]["AAPL"]["fresh"] is False
    assert broker.order_calls == []


def test_120_second_future_mcp_timestamp_passes_with_zero_age(tmp_path):
    now = datetime.now(timezone.utc)
    broker = BrokerTripwire(now + timedelta(seconds=120))
    result = run_analysis(config(), broker, state={"positions": {}}, now=now,
                          historical_provider=HistoryProvider(now),
                          status_path=tmp_path / "brain.json")
    assert result["data_ready"] is True
    assert result["quote_freshness"]["AAPL"]["age_seconds"] == 0.0
    assert result["quote_freshness"]["AAPL"]["source_timestamp"] == broker.quote_time.isoformat()


def test_future_mcp_timestamp_beyond_configured_skew_fails_closed(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("BRAIN_MAX_FUTURE_QUOTE_SKEW_SECONDS", "60")
    broker = BrokerTripwire(now + timedelta(seconds=61))
    result = run_analysis(config(), broker, state={"positions": {}}, now=now,
                          historical_provider=HistoryProvider(now),
                          status_path=tmp_path / "brain.json")
    assert result["data_ready"] is False
    assert result["quote_freshness"]["AAPL"]["fresh"] is False


def test_wrong_symbol_quote_fails_closed(tmp_path):
    broker = BrokerTripwire(quote_overrides={"symbol": "MSFT"})
    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=HistoryProvider(broker.quote_time),
                          status_path=tmp_path / "brain.json")
    assert result["data_ready"] is False
    assert result["quote_freshness"]["AAPL"]["fresh"] is False
    assert broker.order_calls == []


def test_mcp_timestamp_and_provenance_propagate_to_status_file(tmp_path):
    import json
    now = datetime.now(timezone.utc)
    path = tmp_path / "brain.json"
    broker = BrokerTripwire(now)
    result = run_analysis(config(), broker, state={"positions": {}}, now=now,
                          historical_provider=HistoryProvider(now), status_path=path)
    saved = json.loads(path.read_text())
    quote = saved["quote_freshness"]["AAPL"]
    assert quote["source_timestamp"] == now.isoformat()
    assert quote["source"] == "robinhood-trading-mcp"
    assert quote["symbol"] == "AAPL"
    assert quote["price"] == 110.0
    assert 0.0 <= quote["age_seconds"] < 1.0
    assert quote["fresh"] is True
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False


def test_identity_and_reconciliation_fail_closed(tmp_path):
    broker = BrokerTripwire(equity=10_200, cash=10_000)
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


def test_analysis_runner_does_not_retry_missing_quotes(tmp_path):
    broker = BrokerTripwire()
    quote_calls = []

    def missing_quote(symbol):
        quote_calls.append(symbol)
        raise RuntimeError("gateway route budget exhausted")

    broker.get_quote_snapshot = missing_quote
    result = run_analysis(
        config(), broker, state={"positions": {}},
        historical_provider=HistoryProvider(broker.quote_time),
        status_path=tmp_path / "brain.json",
    )

    assert quote_calls == ["AAPL", "SPY"]
    assert "AAPL: missing quote (RuntimeError)" in result["blockers"]
    assert "SPY: missing quote (RuntimeError)" in result["blockers"]
    assert result["data_ready"] is False
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert broker.order_calls == []


def test_later_quote_uses_validation_time_and_generated_at_uses_completion_time(
        tmp_path, monkeypatch):
    run_started = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    quote_collected = run_started + timedelta(minutes=10)
    report_completed = quote_collected + timedelta(seconds=30)
    clock_values = iter([quote_collected, quote_collected, report_completed])

    class AnalysisClock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = next(clock_values)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(run_brain, "datetime", AnalysisClock)
    broker = BrokerTripwire(quote_collected)
    result = run_analysis(
        config(), broker, state={"positions": {}}, now=run_started,
        historical_provider=HistoryProvider(run_started),
        status_path=tmp_path / "brain.json",
    )

    assert result["data_ready"] is True
    assert result["quote_freshness"]["AAPL"]["age_seconds"] == 0.0
    assert result["quote_freshness"]["SPY"]["age_seconds"] == 0.0
    assert result["quote_freshness"]["AAPL"]["source_timestamp"] == quote_collected.isoformat()
    assert result["generated_at"] == report_completed.isoformat()
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert broker.order_calls == []


def test_robinhood_never_falls_back_to_broker_history(tmp_path):
    broker = BrokerTripwire()

    result = run_analysis(config(), broker, state={"positions": {}},
                          historical_provider=None, status_path=tmp_path / "brain.json")

    assert result["data_ready"] is False
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert result["decisions"][0]["action"] == "OBSERVE_ONLY"
