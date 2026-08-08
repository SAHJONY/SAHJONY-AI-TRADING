"""Server-side, read-only Finnhub client with strict response validation."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
import re
from typing import Any, Callable
from urllib import parse, request


class FinnhubError(RuntimeError):
    """A redacted Finnhub configuration, transport, or validation failure."""


_SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,14}")


def _symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not _SYMBOL.fullmatch(symbol):
        raise FinnhubError("invalid symbol")
    return symbol


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FinnhubError(f"invalid {name}") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise FinnhubError(f"invalid {name}")
    return number


class FinnhubClient:
    """Capability-limited client: it exposes data reads and no order methods."""

    base_url = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None = None, *, timeout: float = 8.0,
                 opener: Callable[..., Any] | None = None):
        self._api_key = str(api_key if api_key is not None else os.getenv(
            "FINNHUB_API_KEY", "")).strip()
        if not self._api_key:
            raise FinnhubError("FINNHUB_API_KEY is not configured")
        self.timeout = max(1.0, float(timeout))
        self._opener = opener or request.urlopen

    def _get(self, path: str, **params: str) -> Any:
        query = parse.urlencode({**params, "token": self._api_key})
        req = request.Request(f"{self.base_url}/{path}?{query}", headers={
            "Accept": "application/json", "User-Agent": "SAHJONY-Finnhub/1.0",
        })
        try:
            with self._opener(req, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except Exception as exc:
            # Never include the requested URL: Finnhub authenticates in its query string.
            raise FinnhubError(f"Finnhub request failed: {type(exc).__name__}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise FinnhubError("Finnhub rejected the request")
        return payload

    def quote(self, symbol: str) -> dict[str, Any]:
        requested = _symbol(symbol)
        payload = self._get("quote", symbol=requested)
        if not isinstance(payload, dict):
            raise FinnhubError("invalid quote response")
        price = _finite(payload.get("c"), "quote price", positive=True)
        timestamp = int(_finite(payload.get("t"), "quote timestamp", positive=True))
        as_of = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        return {
            "symbol": requested, "sym": requested, "source": "finnhub",
            "as_of": as_of, "t": timestamp, "c": price,
            "d": _finite(payload.get("d", 0.0), "change"),
            "dp": _finite(payload.get("dp", 0.0), "percent change"),
            "h": _finite(payload.get("h", price), "high"),
            "l": _finite(payload.get("l", price), "low"),
            "o": _finite(payload.get("o", price), "open"),
            "pc": _finite(payload.get("pc", price), "previous close"),
        }

    def general_news(self, *, limit: int = 40) -> list[dict[str, Any]]:
        payload = self._get("news", category="general")
        if not isinstance(payload, list):
            raise FinnhubError("invalid news response")
        return list(payload[:max(1, min(int(limit), 100))])

    def company_news(self, symbol: str, from_date: str, to_date: str,
                     *, limit: int = 20) -> list[dict[str, Any]]:
        requested = _symbol(symbol)
        payload = self._get("company-news", symbol=requested,
                            **{"from": from_date, "to": to_date})
        if not isinstance(payload, list):
            raise FinnhubError("invalid company news response")
        return list(payload[:max(1, min(int(limit), 100))])

    def earnings(self, from_date: str, to_date: str) -> dict[str, Any]:
        payload = self._get("calendar/earnings", **{"from": from_date, "to": to_date})
        if not isinstance(payload, dict) or not isinstance(
                payload.get("earningsCalendar", []), list):
            raise FinnhubError("invalid earnings response")
        return {"earningsCalendar": payload.get("earningsCalendar", [])[:100]}
