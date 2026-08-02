import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from intelligence.historical_data import (
    AlpacaHistoricalDataProvider,
    HistoricalDataError,
    HistoricalEquityBars,
    validate_historical_bars,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 20, 20, tzinfo=UTC)


def bars(count=200, *, timestamps=None, symbol="AAPL", latest=NOW):
    times = timestamps or tuple(latest - timedelta(days=count - 1 - i) for i in range(count))
    return HistoricalEquityBars(
        symbol=symbol, closes=tuple(100.0 + i / 10 for i in range(count)),
        volumes=tuple(1_000.0 + i for i in range(count)), timestamps=times,
        retrieved_at=NOW, feed_timestamp=times[-1] if times else NOW,
        exchange_timestamp=times[-1] if times else NOW, provider="alpaca",
    )


class FakeDataClient:
    def __init__(self, rows=None, error=None):
        self.rows = rows if rows is not None else []
        self.error = error
        self.calls = []
        self.order_calls = []

    def get_stock_bars(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return SimpleNamespace(data={"AAPL": self.rows})

    def submit_order(self, *args, **kwargs):
        self.order_calls.append((args, kwargs))
        raise AssertionError("historical provider called an order method")


def test_valid_alpaca_bars_normalize_to_typed_utc_history():
    rows = [SimpleNamespace(timestamp=NOW - timedelta(days=199 - i), close=100 + i,
                            volume=1_000 + i) for i in range(200)]
    client = FakeDataClient(rows)
    provider = AlpacaHistoricalDataProvider("key", "secret", client=client, clock=lambda: NOW)

    normalized = validate_historical_bars(provider.get_equity_bars("aapl", 365), "AAPL",
                                          min_bars=200, max_staleness_hours=72, now=NOW)

    assert normalized.symbol == "AAPL"
    assert normalized.provider == "alpaca"
    assert len(normalized.closes) == len(normalized.volumes) == len(normalized.timestamps) == 200
    assert all(ts.tzinfo is UTC for ts in normalized.timestamps)
    assert client.calls
    assert client.order_calls == []


def test_provider_source_imports_no_trading_or_order_api():
    import intelligence.historical_data as module

    tree = ast.parse(inspect.getsource(module))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    names = [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
             for alias in node.names]
    assert not any(name.startswith("alpaca.trading") for name in imports)
    assert "TradingClient" not in names
    assert not any("Order" in name for name in names)


def test_missing_credentials_fail_closed(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(HistoricalDataError, match="credentials"):
        AlpacaHistoricalDataProvider()


def test_empty_history_fails():
    with pytest.raises(HistoricalDataError, match="empty"):
        AlpacaHistoricalDataProvider("key", "secret", client=FakeDataClient(),
                                    clock=lambda: NOW).get_equity_bars("AAPL", 365)


def test_malformed_timezone_naive_timestamp_fails():
    times = list(bars().timestamps)
    times[10] = times[10].replace(tzinfo=None)
    with pytest.raises(HistoricalDataError, match="timezone-aware"):
        validate_historical_bars(bars(timestamps=tuple(times)), "AAPL", min_bars=200,
                                 max_staleness_hours=72, now=NOW)


def test_duplicate_timestamps_fail():
    times = list(bars().timestamps)
    times[50] = times[49]
    with pytest.raises(HistoricalDataError, match="duplicate"):
        validate_historical_bars(bars(timestamps=tuple(times)), "AAPL", min_bars=200,
                                 max_staleness_hours=72, now=NOW)


def test_non_monotonic_timestamps_fail():
    times = list(bars().timestamps)
    times[50], times[51] = times[51], times[50]
    with pytest.raises(HistoricalDataError, match="non-monotonic"):
        validate_historical_bars(bars(timestamps=tuple(times)), "AAPL", min_bars=200,
                                 max_staleness_hours=72, now=NOW)


def test_stale_history_fails():
    stale = NOW - timedelta(hours=73)
    with pytest.raises(HistoricalDataError, match="stale"):
        validate_historical_bars(bars(latest=stale), "AAPL", min_bars=200,
                                 max_staleness_hours=72, now=NOW)


def test_insufficient_history_fails():
    with pytest.raises(HistoricalDataError, match="insufficient"):
        validate_historical_bars(bars(count=199), "AAPL", min_bars=200,
                                 max_staleness_hours=72, now=NOW)


def test_provider_timeout_fails_closed():
    provider = AlpacaHistoricalDataProvider(
        "key", "secret", client=FakeDataClient(error=TimeoutError()), clock=lambda: NOW)
    with pytest.raises(HistoricalDataError, match="TimeoutError"):
        provider.get_equity_bars("AAPL", 365)


def test_provider_symbol_mismatch_fails():
    with pytest.raises(HistoricalDataError, match="provider-symbol mismatch"):
        validate_historical_bars(bars(symbol="MSFT"), "AAPL", min_bars=200,
                                 max_staleness_hours=72, now=NOW)
