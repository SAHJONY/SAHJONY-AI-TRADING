"""Bar loading for the 5m BTC backtests.

Two ways in:
  • `load_csv(path)`      — any CSV with timestamp/open/high/low/close/volume.
  • `fetch(source, ...)`  — pull 5m klines from a public venue and cache to CSV.

`fetch` is deliberately thin and dependency-free (requests only). In sandboxes
whose egress policy blocks exchange hosts it will raise `DataUnavailable` with
the blocked host named — that is a policy denial to report, not to route around.
"""
from __future__ import annotations

import csv
import io
import os
import time
import zipfile
from dataclasses import dataclass
from typing import List, Optional

import numpy as np


class DataUnavailable(RuntimeError):
    """Raised when bars cannot be obtained (network policy, empty response…)."""


@dataclass
class Bars:
    """Immutable OHLCV series. `ts` is epoch milliseconds, UTC, ascending."""
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    symbol: str = "BTCUSDT"
    tf_minutes: int = 5

    def __len__(self) -> int:
        return int(self.ts.size)

    @property
    def day_id(self) -> np.ndarray:
        """UTC calendar day index — the anchor for session VWAP."""
        return (self.ts // 86_400_000).astype(np.int64)

    @property
    def minute_of_day(self) -> np.ndarray:
        return ((self.ts % 86_400_000) // 60_000).astype(np.int64)

    def slice(self, i: int, j: int) -> "Bars":
        return Bars(self.ts[i:j], self.open[i:j], self.high[i:j], self.low[i:j],
                    self.close[i:j], self.volume[i:j], self.symbol, self.tf_minutes)

    def describe(self) -> str:
        import datetime as _dt
        a = _dt.datetime.utcfromtimestamp(self.ts[0] / 1000).strftime("%Y-%m-%d")
        b = _dt.datetime.utcfromtimestamp(self.ts[-1] / 1000).strftime("%Y-%m-%d")
        gaps = int((np.diff(self.ts) != self.tf_minutes * 60_000).sum())
        return (f"{self.symbol} {self.tf_minutes}m | {len(self):,} bars | {a} → {b} "
                f"| {gaps} timestamp gaps")


def _to_bars(rows: List[dict], symbol: str, tf: int) -> Bars:
    if not rows:
        raise DataUnavailable("no rows parsed")
    rows.sort(key=lambda r: r["ts"])
    # de-duplicate on timestamp (venues occasionally repeat a kline at a page edge)
    seen, keep = set(), []
    for r in rows:
        if r["ts"] in seen:
            continue
        seen.add(r["ts"])
        keep.append(r)
    g = lambda k: np.array([r[k] for r in keep], dtype=float)  # noqa: E731
    return Bars(np.array([r["ts"] for r in keep], dtype=np.int64),
                g("open"), g("high"), g("low"), g("close"), g("volume"), symbol, tf)


# ── CSV ───────────────────────────────────────────────────────────────────────
_ALIASES = {
    "ts": ("ts", "timestamp", "time", "open_time", "date", "datetime"),
    "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"),
    "close": ("close", "c"), "volume": ("volume", "v", "vol"),
}


def _parse_ts(raw: str) -> int:
    raw = raw.strip()
    try:
        v = float(raw)
        if v > 1e17:      # nanoseconds
            return int(v / 1e6)
        if v > 1e14:      # microseconds
            return int(v / 1e3)
        if v > 1e11:      # milliseconds
            return int(v)
        return int(v * 1000)                     # seconds
    except ValueError:
        pass
    import datetime as _dt
    s = raw.replace("Z", "+00:00")
    d = _dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return int(d.timestamp() * 1000)


def load_csv(path: str, symbol: str = "BTCUSDT", tf: int = 5) -> Bars:
    with open(path, newline="") as fh:
        rdr = csv.DictReader(fh)
        if not rdr.fieldnames:
            raise DataUnavailable(f"{path}: empty CSV")
        cols = {c.lower().strip(): c for c in rdr.fieldnames}
        pick = {}
        for want, names in _ALIASES.items():
            hit = next((cols[n] for n in names if n in cols), None)
            if hit is None:
                raise DataUnavailable(f"{path}: no column for '{want}' in {rdr.fieldnames}")
            pick[want] = hit
        rows = []
        for r in rdr:
            try:
                rows.append({"ts": _parse_ts(r[pick["ts"]]),
                             **{k: float(r[pick[k]]) for k in
                                ("open", "high", "low", "close", "volume")}})
            except (ValueError, TypeError):
                continue          # skip malformed lines rather than abort a long file
    return _to_bars(rows, symbol, tf)


def save_csv(bars: Bars, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for i in range(len(bars)):
            w.writerow([int(bars.ts[i]), bars.open[i], bars.high[i],
                        bars.low[i], bars.close[i], bars.volume[i]])
    return path


# ── venue fetchers ────────────────────────────────────────────────────────────
def _get(url: str, **kw):
    try:
        import requests
    except ImportError as exc:                        # pragma: no cover
        raise DataUnavailable("requests not installed") from exc
    try:
        r = requests.get(url, timeout=30, **kw)
    except Exception as exc:
        host = url.split("/")[2]
        raise DataUnavailable(
            f"cannot reach {host}: {type(exc).__name__}: {exc}. If this is a proxy "
            f"403/407 it is an egress-policy denial — report the host, do not retry."
        ) from exc
    if r.status_code != 200:
        raise DataUnavailable(f"{url.split('/')[2]} returned HTTP {r.status_code}")
    return r


def _fetch_binance_vision(symbol: str, months: List[str]) -> List[dict]:
    """Monthly USD-M futures kline archives — the cheapest way to get years of 5m."""
    rows = []
    for m in months:
        url = (f"https://data.binance.vision/data/futures/um/monthly/klines/"
               f"{symbol}/5m/{symbol}-5m-{m}.zip")
        z = zipfile.ZipFile(io.BytesIO(_get(url).content))
        with z.open(z.namelist()[0]) as fh:
            for line in io.TextIOWrapper(fh, "utf-8"):
                p = line.split(",")
                if not p or not p[0].strip().isdigit():
                    continue                       # header row in newer archives
                rows.append({"ts": int(p[0]), "open": float(p[1]), "high": float(p[2]),
                             "low": float(p[3]), "close": float(p[4]), "volume": float(p[5])})
    return rows


def _fetch_binance_api(symbol: str, start_ms: int, end_ms: int) -> List[dict]:
    rows, cur = [], start_ms
    while cur < end_ms:
        url = ("https://fapi.binance.com/fapi/v1/klines"
               f"?symbol={symbol}&interval=5m&startTime={cur}&limit=1500")
        js = _get(url).json()
        if not js:
            break
        for k in js:
            rows.append({"ts": int(k[0]), "open": float(k[1]), "high": float(k[2]),
                         "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])})
        cur = int(js[-1][0]) + 300_000
        time.sleep(0.25)
    return rows


def _fetch_bybit(symbol: str, start_ms: int, end_ms: int) -> List[dict]:
    rows, cur = [], start_ms
    while cur < end_ms:
        url = ("https://api.bybit.com/v5/market/kline?category=linear"
               f"&symbol={symbol}&interval=5&start={cur}&limit=1000")
        js = _get(url).json().get("result", {}).get("list", [])
        if not js:
            break
        for k in reversed(js):                     # bybit returns newest-first
            rows.append({"ts": int(k[0]), "open": float(k[1]), "high": float(k[2]),
                         "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])})
        cur = int(js[0][0]) + 300_000
        time.sleep(0.2)
    return rows


def fetch(source: str = "binance-vision", symbol: str = "BTCUSDT",
          months: Optional[List[str]] = None, start_ms: int = 0, end_ms: int = 0,
          cache: Optional[str] = None) -> Bars:
    """Pull 5m bars from a venue. `months` is ['2026-01', ...] for binance-vision."""
    if cache and os.path.exists(cache):
        return load_csv(cache, symbol)
    if source == "binance-vision":
        rows = _fetch_binance_vision(symbol, months or [])
    elif source == "binance":
        rows = _fetch_binance_api(symbol, start_ms, end_ms or int(time.time() * 1000))
    elif source == "bybit":
        rows = _fetch_bybit(symbol, start_ms, end_ms or int(time.time() * 1000))
    else:
        raise DataUnavailable(f"unknown source '{source}'")
    bars = _to_bars(rows, symbol, 5)
    if cache:
        save_csv(bars, cache)
    return bars
