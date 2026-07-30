"""Validated, reproducible historical market data for offline research.

This module deliberately has no broker imports. Network downloads require an
explicit CoinGecko API key; cached snapshots are content-addressed and verified
again before every use.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
MAX_DAILY_GAP_MS = 3 * 24 * 60 * 60 * 1000
MIN_COVERAGE_RATIO = 0.90


class MarketDataError(RuntimeError):
    """Raised when research data cannot be proven safe to use."""


def _canonical_payload(symbol: str, coin_id: str, days: int, prices: list) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "coingecko",
        "symbol": symbol,
        "coin_id": coin_id,
        "vs_currency": "usd",
        "requested_days": days,
        "prices": prices,
    }


def _checksum(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_snapshot(snapshot: dict, *, expected_symbol: str | None = None,
                      expected_days: int | None = None) -> list[list[float]]:
    """Validate provenance, checksum, coverage and daily observation integrity."""
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise MarketDataError("unsupported or missing market-data schema")
    if snapshot.get("provider") != "coingecko":
        raise MarketDataError("unexpected market-data provider")
    if expected_symbol and snapshot.get("symbol") != expected_symbol:
        raise MarketDataError("snapshot symbol does not match request")
    days = int(snapshot.get("requested_days", 0))
    if expected_days is not None and days != expected_days:
        raise MarketDataError("snapshot period does not match request")
    prices = snapshot.get("prices")
    if not isinstance(prices, list) or len(prices) < max(30, int(days * MIN_COVERAGE_RATIO)):
        raise MarketDataError("insufficient historical coverage")

    last_ts = None
    normalized = []
    for row in prices:
        if not isinstance(row, list) or len(row) != 2:
            raise MarketDataError("malformed price observation")
        ts, price = row
        if isinstance(ts, bool) or isinstance(price, bool):
            raise MarketDataError("invalid price observation type")
        ts, price = int(ts), float(price)
        if ts <= 0 or not math.isfinite(price) or price <= 0:
            raise MarketDataError("nonpositive or nonfinite price observation")
        if last_ts is not None:
            if ts <= last_ts:
                raise MarketDataError("timestamps are duplicated or out of order")
            if ts - last_ts > MAX_DAILY_GAP_MS:
                raise MarketDataError("historical series contains an excessive gap")
        normalized.append([ts, price])
        last_ts = ts

    payload = _canonical_payload(
        snapshot["symbol"], snapshot["coin_id"], days, normalized
    )
    if snapshot.get("sha256") != _checksum(payload):
        raise MarketDataError("market-data checksum mismatch")
    return normalized


class CoinGeckoHistory:
    """Authenticated CoinGecko downloader with immutable local snapshots."""

    def __init__(self, cache_dir: str | Path, *, api_key: str | None = None,
                 pro: bool | None = None, retries: int = 3):
        self.cache_dir = Path(cache_dir)
        pro_key = os.getenv("COINGECKO_PRO_API_KEY")
        self.api_key = api_key or pro_key or os.getenv("COINGECKO_API_KEY")
        self.pro = bool(os.getenv("COINGECKO_PRO_API_KEY")) if pro is None else pro
        self.retries = max(1, int(retries))

    def _cached(self, symbol: str, days: int) -> tuple[list, Path] | None:
        pattern = f"coingecko-{symbol.lower()}-{days}d-*.json"
        for path in sorted(self.cache_dir.glob(pattern), reverse=True):
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                return validate_snapshot(
                    snapshot, expected_symbol=symbol, expected_days=days
                ), path
            except (OSError, ValueError, MarketDataError):
                continue
        return None

    def load(self, symbol: str, coin_id: str, days: int,
             *, offline: bool = False) -> tuple[list[list[float]], dict]:
        cached = self._cached(symbol, days)
        if offline:
            if not cached:
                raise MarketDataError(
                    f"no valid offline snapshot for {symbol} ({days} days)"
                )
            rows, path = cached
            return rows, {"source": "cache", "snapshot": str(path)}

        if not self.api_key:
            raise MarketDataError(
                "CoinGecko API key required; set COINGECKO_API_KEY or explicitly "
                "request --offline replay of a validated snapshot"
            )

        base = "https://pro-api.coingecko.com/api/v3" if self.pro else \
               "https://api.coingecko.com/api/v3"
        query = urllib.parse.urlencode({
            "vs_currency": "usd", "days": days, "interval": "daily"
        })
        request = urllib.request.Request(
            f"{base}/coins/{coin_id}/market_chart?{query}",
            headers={
                ("x-cg-pro-api-key" if self.pro else "x-cg-demo-api-key"):
                    self.api_key,
                "Accept": "application/json",
                "User-Agent": "SAHJONY-research/1.0",
            },
        )
        error = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    body = json.load(response)
                raw_prices = body.get("prices", [])
                rows = [[int(row[0]), float(row[1])] for row in raw_prices]
                payload = _canonical_payload(symbol, coin_id, days, rows)
                snapshot = {
                    **payload,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": _checksum(payload),
                }
                validated = validate_snapshot(
                    snapshot, expected_symbol=symbol, expected_days=days
                )
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                filename = (
                    f"coingecko-{symbol.lower()}-{days}d-"
                    f"{snapshot['sha256'][:16]}.json"
                )
                path = self.cache_dir / filename
                if not path.exists():
                    path.write_text(
                        json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
                    )
                return validated, {
                    "source": "network",
                    "snapshot": str(path),
                    "sha256": snapshot["sha256"],
                }
            except (urllib.error.URLError, TimeoutError, ValueError,
                    KeyError, MarketDataError) as exc:
                error = exc
                if attempt + 1 < self.retries:
                    time.sleep(2 ** attempt)
        raise MarketDataError(f"CoinGecko download failed for {symbol}: {error}")
