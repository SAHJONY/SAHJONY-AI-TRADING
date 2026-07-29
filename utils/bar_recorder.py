"""Record live quotes into OHLCV bars — the only path from Robinhood to a backtest.

**Why this exists.** Robinhood's crypto trading API has no candles. It serves
`best_bid_ask` — one live quote — and nothing else; `utils/brokers/robinhood_crypto.py`
says so in its own docstring and backfills *daily* closes from CoinGecko for the
council. So Robinhood market data cannot backfill a 5-minute backtest, no matter
what network access you have. That is an API capability limit, not an outage.

What it *can* do is accumulate history going forward. The desk already polls a
price every cycle; this stores those observations as bars, so that after N days
there is a real BTC series to run `backtest/` against instead of synthetic bars.

**Two honest limitations, both of which change what the bars mean:**

1. **Volume is a tick count, not traded volume.** `best_bid_ask` reports no size.
   The `volume` column counts how many quotes landed in the bar. Strategies keyed
   on volume (S2's `vol_mult`, S15's volume spike, S1's capitulation filter) are
   therefore measuring *sampling frequency*, not participation, on these bars.
   Do not read their volume gates as meaningful here.
2. **Bar resolution is bounded by the poll cadence.** A bar can only have a high
   above its low if at least two quotes landed inside it. At the desk's observed
   ~16-minute cycle, a 5-minute bucket gets one observation or none: the bars
   that do exist have open == high == low == close, so their range — and every
   ATR, wick and intrabar stop computed from it — is fabricated, not measured.
   Genuine 5-minute bars need a 5-minute (or faster) poll. Nothing else does it.

That is why the recorder writes **several intervals at once** (`intervals`). The
coarse one is usable today at the current cadence; the fine one costs one extra
row per cycle and becomes usable the moment the poll speeds up, with no gap in
the record. `backtest.data.load_desk_db` picks between them and refuses bars
built from too few observations.

Bars are keyed `(symbol, bucket_start, interval)` with an upsert, so re-running a
cycle or overlapping recorders cannot double-count.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

log = get_logger("bar_recorder")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol     TEXT    NOT NULL,
    ts         INTEGER NOT NULL,          -- bucket start, epoch seconds UTC
    interval_m INTEGER NOT NULL,
    open       REAL    NOT NULL,
    high       REAL    NOT NULL,
    low        REAL    NOT NULL,
    close      REAL    NOT NULL,
    volume     REAL    NOT NULL DEFAULT 0, -- TICK COUNT, not traded volume
    source     TEXT,
    PRIMARY KEY (symbol, ts, interval_m)
);
CREATE INDEX IF NOT EXISTS idx_bars_symbol_ts ON bars(symbol, ts);
"""


class BarRecorder:
    """Folds live quotes into OHLCV bars and persists them.

    Passive by construction: it observes prices the desk already fetched and
    writes rows. It never calls the broker, never influences a decision, and any
    failure is swallowed with a log — recording history must not be able to
    disturb trading.
    """

    def __init__(self, db, interval_minutes=5, source: str = ""):
        self.db = db
        raw = interval_minutes if isinstance(interval_minutes, (list, tuple, set)) \
            else [interval_minutes]
        self.intervals = sorted({max(1, int(x)) for x in raw if int(x) > 0}) or [5]
        self.interval = self.intervals[0]      # the finest — back-compat alias
        self.source = source or "live"
        self._ready = False
        try:
            db.conn.executescript(_SCHEMA)
            db.conn.commit()
            self._ready = True
        except Exception as exc:
            log.error("bar table init failed: %s", exc)

    def _bucket(self, ts: float, interval: Optional[int] = None) -> int:
        step = (interval or self.interval) * 60
        return int(ts // step * step)

    def record(self, symbol: str, price: float, ts: Optional[float] = None) -> None:
        """Fold one observation into its bar, at every configured interval.

        Cheap, idempotent, never raises.
        """
        if not self._ready or not price or price <= 0 or price != price:
            return
        when = ts if ts is not None else time.time()
        for iv in self.intervals:
            try:
                self.db.conn.execute(
                    """INSERT INTO bars (symbol, ts, interval_m, open, high, low,
                                         close, volume, source)
                       VALUES (?,?,?,?,?,?,?,1,?)
                       ON CONFLICT(symbol, ts, interval_m) DO UPDATE SET
                           high   = MAX(bars.high, excluded.close),
                           low    = MIN(bars.low,  excluded.close),
                           close  = excluded.close,
                           volume = bars.volume + 1""",
                    (symbol, self._bucket(when, iv), iv, price, price, price,
                     price, self.source))
            except Exception as exc:
                log.warning("bar record(%s@%dm) failed: %s", symbol, iv, exc)

    def record_many(self, prices: Dict[str, float], ts: Optional[float] = None) -> None:
        for sym, px in (prices or {}).items():
            self.record(sym, px, ts)
        try:
            self.db.conn.commit()
        except Exception as exc:
            log.warning("bar commit failed: %s", exc)

    # -- reading back --------------------------------------------------------
    def coverage(self) -> List[Dict[str, Any]]:
        """What has been accumulated so far, per symbol — the honest answer to
        'is there enough history to backtest yet?'."""
        if not self._ready:
            return []
        try:
            rows = self.db.conn.execute(
                """SELECT symbol, interval_m, COUNT(*) n, MIN(ts) first, MAX(ts) last,
                          AVG(volume) tpb,
                          SUM(CASE WHEN volume <= 1 THEN 1 ELSE 0 END) single
                   FROM bars GROUP BY symbol, interval_m ORDER BY n DESC""").fetchall()
        except Exception as exc:
            log.warning("bar coverage failed: %s", exc)
            return []
        out = []
        for r in rows:
            n, first, last = int(r["n"]), int(r["first"]), int(r["last"])
            # A bar with one observation has no measured range. Reporting the
            # count without this share would overstate how backtestable the
            # record is — which is the whole question `coverage()` is asked.
            single_pct = round(100.0 * int(r["single"]) / max(1, n), 1)
            out.append({"symbol": r["symbol"], "interval_m": int(r["interval_m"]),
                        "bars": n, "first_ts": first, "last_ts": last,
                        "span_days": round((last - first) / 86400.0, 2),
                        "ticks_per_bar": round(float(r["tpb"] or 0), 2),
                        "single_tick_pct": single_pct,
                        "usable_bars": n - int(r["single"])})
        return out

    def export_csv(self, symbol: str, path: str, interval_m: Optional[int] = None) -> int:
        """Write bars in the format `backtest/data.py` reads. Returns row count."""
        import csv
        import os
        iv = int(interval_m or self.interval)
        rows = self.db.conn.execute(
            """SELECT ts, open, high, low, close, volume FROM bars
               WHERE symbol=? AND interval_m=? ORDER BY ts""", (symbol, iv)).fetchall()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ts", "open", "high", "low", "close", "volume"])
            for r in rows:
                w.writerow([int(r["ts"]) * 1000, r["open"], r["high"], r["low"],
                            r["close"], r["volume"]])
        return len(rows)
