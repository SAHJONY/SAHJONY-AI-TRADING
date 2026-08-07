"""Intraday confirmation overlay — does the recent tape agree with the daily call?

**The gap this fills.** The council is a DAILY-horizon estimator: its agents ask
for `sma(200)`, `ret_over(252) - ret_over(21)` (12-1 momentum), a 52-week high,
and an annualized vol computed with `periods_per_year=252`. On the live crypto
desk it is fed CoinGecko daily closes, which is the right series for those
questions. But the desk re-runs it every CYCLE_MINUTES, so it re-asks a
once-a-day question up to 288 times a day and unsurprisingly gets the same
answer. The desk has no intraday view at all.

**Why this is an overlay and not a new history source.** Handing those same
agents 15-minute bars would not improve them, it would silently redefine them:
`sma(200)` becomes a 50-hour average, 12-1 momentum becomes 2.6 days, and
annualized vol is understated by ~sqrt(96). Nothing raises, every number just
becomes quietly wrong. Preserving their meaning on 15m bars needs 19,200 of them
(200 trading days); the recorder has about four days. So the daily series stays
exactly as it is, and the intraday data is used for the one thing a finer series
can legitimately do with a few days of history: say whether the recent tape
agrees with the slower view.

**Confirmation, not a directional bet.** This deliberately does not pick
"momentum" or "mean reversion" — that choice is a regime claim, and there is no
evidence here to make it. It scores the recent move, compares its SIGN to the
direction the council already chose, and nudges conviction up on agreement and
down on disagreement. Buying into an intraday slide your daily signal likes is a
timing error regardless of which regime you believe in.

**Bounded and subordinate.** The tilt is clamped to ±0.05 — a third of the
alt-data overlay's ±0.15, because that one reflects disclosed filings while this
is an unvalidated estimator on four days of self-recorded data. It cannot flip a
verdict, only shade it. It returns exactly 0.0 (neutral) whenever the data is
insufficient, degenerate, or unreadable, and it never raises.

Off by default (`INTRADAY_OVERLAY_ENABLED`). Validate it against
`tools.conviction_calibration` before arming it on a real-money desk.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from utils.logger import get_logger

log = get_logger("intraday")

# Clamp. Small on purpose — see the module docstring.
MAX_TILT = 0.05

# A bar whose volume (a TICK COUNT on this recorder, not traded size) is below
# this was observed once, so its high equals its low and its range is assumed
# rather than measured. backtest.data.load_desk_db uses the same threshold for
# the same reason.
MIN_TICKS_PER_BAR = 2

# Usable bars required before this says anything at all. Below this the standard
# deviation in the denominator is noise and the score is not meaningful.
MIN_USABLE_BARS = 24

# How many bars the "recent move" spans. 6 bars is 6 hours on the 60m series —
# long enough to be a move, short enough to still be intraday.
LOOKBACK_BARS = 6


@dataclass
class IntradayRead:
    symbol: str
    tilt: float = 0.0          # conviction nudge in [-MAX_TILT, MAX_TILT]
    score: float = 0.0         # normalized recent move in [-1, 1]
    interval_m: int = 0
    bars_used: int = 0
    agrees: Optional[bool] = None
    summary: str = "no intraday data"


def _clamp(v, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return max(lo, min(hi, v))


def _direction_sign(direction: str) -> int:
    d = str(direction or "").strip().lower()
    if d in ("long", "buy", "bullish"):
        return 1
    if d in ("short", "sell", "bearish"):
        return -1
    return 0


class IntradayOverlay:
    """Reads the desk's own recorded bars and scores agreement with the council."""

    def __init__(self, cfg, db):
        self.cfg = cfg
        self.db = db
        self.enabled = bool(getattr(cfg, "intraday_overlay_enabled", False))

    # ── data ────────────────────────────────────────────────────────────────
    def _best_interval(self, symbol: str) -> Optional[int]:
        """The recorded interval with the most bars that have a MEASURED range.

        Ranked on usable bars, never on row count: the finer series always has
        more rows and is always the less usable one, so ranking by rows reliably
        picks the worst available data. On the live desk today that is 15m with
        2 usable bars of 182 versus 60m with 57 of 77.
        """
        try:
            rows = self.db.conn.execute(
                """SELECT interval_m, COUNT(*) AS usable
                     FROM bars
                    WHERE symbol = ? AND volume >= ?
                 GROUP BY interval_m
                 ORDER BY usable DESC""",
                (symbol, float(MIN_TICKS_PER_BAR)),
            ).fetchall()
        except Exception as exc:
            log.debug("intraday interval lookup failed for %s: %s", symbol, exc)
            return None
        for row in rows:
            interval = int(row["interval_m"] if hasattr(row, "keys") else row[0])
            usable = int(row["usable"] if hasattr(row, "keys") else row[1])
            if usable >= MIN_USABLE_BARS:
                return interval
        return None

    def _closes(self, symbol: str, interval_m: int):
        try:
            rows = self.db.conn.execute(
                """SELECT close FROM bars
                    WHERE symbol = ? AND interval_m = ? AND volume >= ?
                 ORDER BY ts""",
                (symbol, int(interval_m), float(MIN_TICKS_PER_BAR)),
            ).fetchall()
        except Exception as exc:
            log.debug("intraday bar read failed for %s: %s", symbol, exc)
            return []
        out = []
        for row in rows:
            try:
                price = float(row["close"] if hasattr(row, "keys") else row[0])
            except (TypeError, ValueError):
                continue
            if math.isfinite(price) and price > 0:
                out.append(price)
        return out

    # ── signal ──────────────────────────────────────────────────────────────
    @staticmethod
    def _score(closes) -> float:
        """Recent move normalized by this series' own bar-to-bar volatility.

        Normalizing matters: a 1% move means something different in BTC than in
        a quiet hour of LTC, and an unnormalized return would make the tilt a
        function of which asset is noisier rather than of what happened.
        Squashed with tanh so an outlier bar cannot saturate the overlay.
        """
        n = len(closes)
        if n < MIN_USABLE_BARS:
            return 0.0
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, n)]
        if len(rets) < 2:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        sd = var ** 0.5
        if not math.isfinite(sd) or sd <= 0:
            return 0.0          # a flat series has no information
        span = min(LOOKBACK_BARS, n - 1)
        move = closes[-1] / closes[-1 - span] - 1.0
        # Per-bar move in standard deviations, so the lookback length does not
        # by itself inflate the score.
        z = move / (sd * math.sqrt(span))
        if not math.isfinite(z):
            return 0.0
        return _clamp(math.tanh(z), -1.0, 1.0)

    def read(self, symbol: str, direction: str) -> IntradayRead:
        """Never raises. Returns a neutral read on any problem."""
        if not self.enabled:
            return IntradayRead(symbol, summary="overlay disabled")
        try:
            sign = _direction_sign(direction)
            if sign == 0:
                # The council is flat; there is nothing to confirm or contradict.
                return IntradayRead(symbol, summary="council flat — no tilt")
            interval = self._best_interval(symbol)
            if not interval:
                return IntradayRead(
                    symbol, summary=f"fewer than {MIN_USABLE_BARS} bars with a measured range")
            closes = self._closes(symbol, interval)
            score = self._score(closes)
            if score == 0.0:
                return IntradayRead(symbol, interval_m=interval, bars_used=len(closes),
                                    summary="no usable intraday signal")
            agreement = score * sign          # >0 when the tape agrees with the call
            tilt = _clamp(agreement * MAX_TILT, -MAX_TILT, MAX_TILT)
            agrees = agreement > 0
            return IntradayRead(
                symbol=symbol, tilt=tilt, score=round(score, 4), interval_m=interval,
                bars_used=len(closes), agrees=agrees,
                summary=(f"{interval}m tape {'confirms' if agrees else 'contradicts'} "
                         f"the {direction} call (score {score:+.2f}, {len(closes)} bars)"),
            )
        except Exception as exc:       # an overlay must never sink a cycle
            log.warning("intraday overlay failed for %s: %s", symbol, exc)
            return IntradayRead(symbol, summary=f"unavailable ({type(exc).__name__})")

    def reads(self, pairs) -> Dict[str, IntradayRead]:
        """pairs: iterable of (symbol, direction)."""
        out: Dict[str, IntradayRead] = {}
        for symbol, direction in pairs or []:
            out[symbol] = self.read(symbol, direction)
        return out
