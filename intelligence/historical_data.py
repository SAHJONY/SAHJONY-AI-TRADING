"""Read-only, fail-closed historical equity market data.

This module deliberately imports only ``alpaca.data`` APIs.  Broker account and
order capabilities do not belong in the historical-data process.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, Sequence, runtime_checkable


UTC = timezone.utc
COUNCIL_MIN_BARS = 200


class HistoricalDataError(RuntimeError):
    """Historical data is unavailable or unsafe to consume."""


@dataclass(frozen=True)
class HistoricalEquityBars:
    symbol: str
    closes: tuple[float, ...]
    volumes: tuple[float, ...]
    timestamps: tuple[datetime, ...]
    retrieved_at: datetime
    feed_timestamp: datetime
    exchange_timestamp: datetime
    provider: str


@runtime_checkable
class HistoricalDataProvider(Protocol):
    """Narrow market-data-only capability used by the analysis brain."""

    def get_equity_bars(self, symbol: str, lookback_days: int) -> HistoricalEquityBars:
        ...


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise HistoricalDataError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def validate_historical_bars(
    bars: HistoricalEquityBars,
    expected_symbol: str,
    *,
    min_bars: int,
    max_staleness_hours: float,
    now: datetime | None = None,
) -> HistoricalEquityBars:
    """Validate every field and return a normalized immutable UTC record."""
    expected = expected_symbol.strip().upper()
    actual = str(bars.symbol).strip().upper()
    if not expected or actual != expected:
        raise HistoricalDataError("provider-symbol mismatch")
    if not bars.provider.strip():
        raise HistoricalDataError("provider is missing")
    if not bars.closes or not bars.timestamps:
        raise HistoricalDataError("empty history")
    if len(bars.closes) != len(bars.volumes) or len(bars.closes) != len(bars.timestamps):
        raise HistoricalDataError("bar fields have different lengths")
    if len(bars.closes) < max(COUNCIL_MIN_BARS, int(min_bars)):
        raise HistoricalDataError("insufficient history")

    try:
        closes = tuple(float(value) for value in bars.closes)
        volumes = tuple(float(value) for value in bars.volumes)
    except (TypeError, ValueError, OverflowError) as exc:
        raise HistoricalDataError("non-numeric closes or volumes") from exc
    if any(not math.isfinite(value) or value <= 0 for value in closes):
        raise HistoricalDataError("invalid closes")
    if any(not math.isfinite(value) for value in volumes):
        raise HistoricalDataError("invalid volumes")

    timestamps = tuple(_utc(value, "bar timestamp") for value in bars.timestamps)
    if len(set(timestamps)) != len(timestamps):
        raise HistoricalDataError("duplicate timestamps")
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise HistoricalDataError("non-monotonic timestamps")

    retrieved_at = _utc(bars.retrieved_at, "retrieved_at")
    feed_timestamp = _utc(bars.feed_timestamp, "feed_timestamp")
    exchange_timestamp = _utc(bars.exchange_timestamp, "exchange_timestamp")
    checked_at = _utc(now or datetime.now(UTC), "now")
    freshest = max(timestamps[-1], feed_timestamp, exchange_timestamp)
    if freshest > checked_at + timedelta(minutes=5):
        raise HistoricalDataError("history timestamp is in the future")
    if checked_at - freshest > timedelta(hours=float(max_staleness_hours)):
        raise HistoricalDataError("stale history")

    return HistoricalEquityBars(actual, closes, volumes, timestamps, retrieved_at,
                                feed_timestamp, exchange_timestamp, bars.provider.strip())


class AlpacaHistoricalDataProvider:
    """Alpaca stock-bars adapter with no trading or order capabilities."""

    provider = "alpaca"

    def __init__(self, api_key: str | None = None, secret_key: str | None = None,
                 *, client: Any | None = None, clock: Any | None = None):
        self._api_key = (api_key if api_key is not None else os.getenv("APCA_API_KEY_ID", "")).strip()
        self._secret_key = (secret_key if secret_key is not None else os.getenv("APCA_API_SECRET_KEY", "")).strip()
        self._auth_mode = os.getenv("ALPACA_MARKET_DATA_AUTH", "trading").strip().lower()
        self._feed = os.getenv("ALPACA_MARKET_DATA_FEED", "").strip().lower()
        if not self._api_key or not self._secret_key:
            raise HistoricalDataError("Alpaca market-data credentials are missing")
        self._clock = clock or (lambda: datetime.now(UTC))
        if client is None:
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                if self._auth_mode == "broker_sandbox":
                    import requests
                    response = requests.post(
                        "https://authx.sandbox.alpaca.markets/v1/oauth2/token",
                        data={"grant_type": "client_credentials", "client_id": self._api_key,
                              "client_secret": self._secret_key},
                        timeout=20,
                    )
                    response.raise_for_status()
                    token = str(response.json().get("access_token", "")).strip()
                    if not token:
                        raise HistoricalDataError("Alpaca broker token is missing")
                    client = StockHistoricalDataClient(
                        oauth_token=token,
                        url_override="https://data.sandbox.alpaca.markets",
                    )
                elif self._auth_mode == "trading":
                    client = StockHistoricalDataClient(self._api_key, self._secret_key)
                else:
                    raise HistoricalDataError("unsupported Alpaca market-data auth mode")
            except Exception as exc:
                if isinstance(exc, HistoricalDataError):
                    raise
                raise HistoricalDataError("Alpaca market-data client unavailable") from exc
        self._client = client

    def get_equity_bars(self, symbol: str, lookback_days: int) -> HistoricalEquityBars:
        requested = symbol.strip().upper()
        now = _utc(self._clock(), "retrieved_at")
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            request_args = {
                "symbol_or_symbols": requested,
                "timeframe": TimeFrame.Day,
                "start": now - timedelta(days=max(1, int(lookback_days))),
                "end": now,
            }
            if self._feed:
                from alpaca.data.enums import DataFeed
                try:
                    request_args["feed"] = DataFeed(self._feed)
                except ValueError as exc:
                    raise HistoricalDataError("unsupported Alpaca market-data feed") from exc
            request = StockBarsRequest(**request_args)
            response = self._client.get_stock_bars(request)
            rows: Sequence[Any] = response.data.get(requested, ())
        except Exception as exc:
            raise HistoricalDataError(f"Alpaca history unavailable: {type(exc).__name__}") from exc
        if not rows:
            raise HistoricalDataError("empty history")

        try:
            timestamps = tuple(_utc(row.timestamp, "bar timestamp") for row in rows)
            closes = tuple(float(row.close) for row in rows)
            volumes = tuple(float(row.volume) for row in rows)
        except (AttributeError, TypeError, ValueError) as exc:
            raise HistoricalDataError("malformed Alpaca history") from exc
        latest = timestamps[-1]
        return HistoricalEquityBars(requested, closes, volumes, timestamps, now,
                                    latest, latest, self.provider)


def configured_historical_provider() -> HistoricalDataProvider:
    name = (os.getenv("HISTORICAL_DATA_PROVIDER", "alpaca") or "alpaca").strip().lower()
    if name != "alpaca":
        raise HistoricalDataError(f"unsupported historical-data provider: {name}")
    return AlpacaHistoricalDataProvider()
