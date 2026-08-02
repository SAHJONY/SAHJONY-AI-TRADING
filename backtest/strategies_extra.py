"""Additional candidate strategies for the 5m BTC book (S11–S18).

These are **candidates, not winners.** Every one is a transparent, public-domain
pattern — Donchian breakout, Connors RSI(2), %B reversion, NR7 expansion, volume
continuation, engulfing reversal, session seasonality, dual-timeframe pullback.
None has been validated on real BTC data. Whether any of them earns size is
decided by `backtest/optimize.py`'s promotion gate on out-of-sample evidence, not
by the fact that they are written down here.

They are deliberately *cheaper* in conditions than S1–S9. The funnel work in
docs/btc_futures_5m_backtest.md showed the original book's problem was not weak
signals but conjunctions so deep nothing fired. These use 3–5 conditions each so
they can actually produce a measurable sample.

Same contract as strategies.py: pure decision engines, causal indicators, every
condition routed through `self._g` so `--funnel` explains them.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from backtest import indicators as ta
from backtest.data import Bars
from backtest.engine import Position, Setup, Strategy


def _frac(h, l, c) -> float:
    rng = h - l
    return 0.5 if rng <= 0 else float((c - l) / rng)


# ── S11 · Donchian breakout (turtle-style) ────────────────────────────────────
class S11_DonchianBreakout(Strategy):
    """Classic trend following: break the N-bar extreme, exit on the opposite
    M-bar extreme. The oldest systematic trend rule there is, and the honest
    baseline every fancier trend strategy should be measured against."""
    id, name, warmup = "s11", "Donchian Turtle Breakout", 300
    PARAMS = {"entry_n": 20.0, "exit_n": 10.0, "stop_atr": 2.0,
              "tp1_atr": 2.0, "tp2_atr": 4.0, "trail_atr": 3.0,
              "atr_pct_min": 0.0010}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        n, m = int(self.p["entry_n"]), int(self.p["exit_n"])
        hi, lo = ta.donchian(b.high, b.low, n)
        xhi, xlo = ta.donchian(b.high, b.low, m)
        return {"atr": a, "dc_hi": hi, "dc_lo": lo, "ex_hi": xhi, "ex_lo": xlo,
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        hi, lo = ind["dc_hi"][t], ind["dc_lo"][t]
        if not self._g("ready", np.isfinite(a) and a > 0 and np.isfinite(hi)):
            return None
        if not self._g("atr%>=min", ind["atr_pct"][t] >= p["atr_pct_min"]):
            return None
        up, dn = c > hi, c < lo
        if not self._g("breaks_channel", up or dn):
            return None
        s = 1 if up else -1
        stop = c - s * p["stop_atr"] * a
        return self._emit(Setup(
            side=s, entry_kind="close", stop=stop,
            targets=[(c + s * p["tp1_atr"] * a, 0.5),
                     (c + s * p["tp2_atr"] * a, 0.3),
                     (c + s * 12.0 * a, 0.2)],
            trail_atr_mult=p["trail_atr"], trail_after_leg=2,
            tag="long" if up else "short"))

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        # turtle exit: give it back at the opposite M-bar extreme
        if pos.side > 0 and b.close[t] < ind["ex_lo"][t]:
            return "channel_exit"
        if pos.side < 0 and b.close[t] > ind["ex_hi"][t]:
            return "channel_exit"
        return None


# ── S12 · Connors RSI(2) with a trend filter ──────────────────────────────────
class S12_ConnorsRSI2(Strategy):
    """Buy a short-term oversold reading only in the direction of the long-term
    trend. Published, widely replicated, and the closest thing to a null model for
    'does mean reversion work here at all'."""
    id, name, warmup = "s12", "Connors RSI(2) Pullback", 400
    PARAMS = {"rsi_lo": 5.0, "rsi_hi": 95.0, "trend_sma": 200.0, "exit_sma": 5.0,
              "stop_atr": 2.0, "tp_atr": 2.5, "time_stop": 24.0}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        return {"atr": a, "rsi2": ta.rsi(b.close, 2),
                "trend": ta.sma(b.close, int(self.p["trend_sma"])),
                "exit_sma": ta.sma(b.close, int(self.p["exit_sma"])),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        tr, r2 = ind["trend"][t], ind["rsi2"][t]
        if not self._g("ready", np.isfinite(a) and a > 0 and np.isfinite(tr)):
            return None
        long_ok = c > tr and r2 < p["rsi_lo"]
        short_ok = c < tr and r2 > p["rsi_hi"]
        if not self._g("oversold_with_trend", long_ok or short_ok):
            return None
        s = 1 if long_ok else -1
        stop = c - s * p["stop_atr"] * a
        return self._emit(Setup(
            side=s, entry_kind="close", stop=stop,
            targets=[(c + s * p["tp_atr"] * a, 1.0)],
            time_stop_bars=int(p["time_stop"]), tag="long" if long_ok else "short"))

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        # Connors' own exit: leave when the short SMA is recovered
        if pos.side > 0 and b.close[t] > ind["exit_sma"][t]:
            return "sma_exit"
        if pos.side < 0 and b.close[t] < ind["exit_sma"][t]:
            return "sma_exit"
        return None


# ── S13 · Bollinger %B reversion, trend-filtered ──────────────────────────────
class S13_PercentBReversion(Strategy):
    """Fade a band excursion, but only with the higher-timeframe trend. The
    trend filter is what separates this from S1 — it never fades a trend day."""
    id, name, warmup = "s13", "Bollinger %B Reversion", 400
    PARAMS = {"bb_n": 20.0, "bb_k": 2.0, "pb_lo": 0.05, "pb_hi": 0.95,
              "trend_sma": 200.0, "stop_atr": 1.5, "tp_mid": 1.0, "time_stop": 18.0}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        mid, up, lo = ta.bollinger(b.close, int(self.p["bb_n"]), self.p["bb_k"])
        with np.errstate(invalid="ignore", divide="ignore"):
            pb = (b.close - lo) / (up - lo)
        return {"atr": a, "mid": mid, "pb": pb,
                "trend": ta.sma(b.close, int(self.p["trend_sma"])),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        pb, mid, tr = ind["pb"][t], ind["mid"][t], ind["trend"][t]
        if not self._g("ready", np.isfinite(a) and a > 0 and np.isfinite(pb)
                       and np.isfinite(tr)):
            return None
        long_ok = pb <= p["pb_lo"] and c > tr
        short_ok = pb >= p["pb_hi"] and c < tr
        if not self._g("band_extreme_with_trend", long_ok or short_ok):
            return None
        s = 1 if long_ok else -1
        stop = c - s * p["stop_atr"] * a
        return self._emit(Setup(
            side=s, entry_kind="close", stop=stop,
            targets=[(mid, 1.0)] if abs(mid - c) > 0 else [(c + s * a, 1.0)],
            time_stop_bars=int(p["time_stop"]), tag="long" if long_ok else "short"))


# ── S14 · NR7 volatility-contraction expansion ────────────────────────────────
class S14_NR7Expansion(Strategy):
    """The narrowest range of the last 7 bars is a coil; trade the break of that
    bar. Same premise as S3 but measured on a single bar rather than a band
    relationship, so it fires far more often."""
    id, name, warmup = "s14", "NR7 Range Expansion", 300
    PARAMS = {"lookback": 7.0, "buf_atr": 0.05, "stop_atr": 1.0,
              "tp1_atr": 1.5, "tp2_atr": 3.0, "trail_atr": 2.5, "valid_bars": 3.0}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        rng = b.high - b.low
        n = int(self.p["lookback"])
        return {"atr": a, "rng": rng, "rng_min": ta.rolling_min(rng, n),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a = self.p, ind["atr"][t]
        if not self._g("ready", np.isfinite(a) and a > 0):
            return None
        # bar t is the narrowest of the last `lookback` bars
        if not self._g("is_NR7", ind["rng"][t] <= ind["rng_min"][t] + 1e-12):
            return None
        if not self._g("coil_is_tight", ind["rng"][t] < 0.8 * a):
            return None
        buf = p["buf_atr"] * a
        # a stop-entry on each side would be two positions; take the side the bar
        # closed toward, which is the cheap directional prior
        s = 1 if _frac(b.high[t], b.low[t], b.close[t]) >= 0.5 else -1
        entry = (b.high[t] + buf) if s > 0 else (b.low[t] - buf)
        stop = entry - s * p["stop_atr"] * a
        return self._emit(Setup(
            side=s, entry_kind="stop", entry_price=entry,
            valid_bars=int(p["valid_bars"]), stop=stop,
            targets=[(entry + s * p["tp1_atr"] * a, 0.5),
                     (entry + s * p["tp2_atr"] * a, 0.3),
                     (entry + s * 10.0 * a, 0.2)],
            trail_atr_mult=p["trail_atr"], trail_after_leg=2,
            tag="long" if s > 0 else "short"))


# ── S15 · Volume-spike continuation ───────────────────────────────────────────
class S15_VolumeSpikeContinuation(Strategy):
    """A wide, high-volume bar closing on its extreme is participation, not noise.
    Trade its continuation rather than fading it."""
    id, name, warmup = "s15", "Volume-Spike Continuation", 300
    PARAMS = {"vol_mult": 3.0, "range_atr": 1.2, "close_frac": 0.75,
              "stop_frac": 0.5, "tp1_r": 1.5, "tp2_r": 3.0, "trail_atr": 2.5,
              "ema_n": 20.0}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        return {"atr": a, "vsma": ta.sma(b.volume, 20),
                "ema": ta.ema(b.close, int(self.p["ema_n"])), "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        if not self._g("ready", np.isfinite(a) and a > 0 and np.isfinite(ind["ema"][t])):
            return None
        if not self._g("volume_spike", b.volume[t] >= p["vol_mult"] * ind["vsma"][t]):
            return None
        if not self._g("wide_bar", (b.high[t] - b.low[t]) >= p["range_atr"] * a):
            return None
        f = _frac(b.high[t], b.low[t], c)
        up = f >= p["close_frac"] and c > ind["ema"][t]
        dn = f <= 1 - p["close_frac"] and c < ind["ema"][t]
        if not self._g("closes_on_extreme_with_ema", up or dn):
            return None
        s = 1 if up else -1
        # stop inside the signal bar — its midpoint; the bar defines the risk
        stop = b.low[t] + p["stop_frac"] * (b.high[t] - b.low[t]) if s > 0 else \
               b.high[t] - p["stop_frac"] * (b.high[t] - b.low[t])
        risk = abs(c - stop)
        if not self._g("stop_valid", risk > 0):
            return None
        return self._emit(Setup(
            side=s, entry_kind="close", stop=stop,
            targets=[(c + s * p["tp1_r"] * risk, 0.5),
                     (c + s * p["tp2_r"] * risk, 0.3),
                     (c + s * 8.0 * risk, 0.2)],
            trail_atr_mult=p["trail_atr"], trail_after_leg=2,
            tag="long" if up else "short"))


# ── S16 · Engulfing reversal at a channel extreme ─────────────────────────────
class S16_EngulfingAtExtreme(Strategy):
    """Price action, not indicators: an engulfing bar at a 20-bar extreme is a
    one-bar shift in control. Cheap to state, easy to falsify."""
    id, name, warmup = "s16", "Engulfing Reversal at Extreme", 300
    PARAMS = {"channel_n": 20.0, "body_ratio": 1.0, "stop_buf_atr": 0.25,
              "tp1_r": 1.5, "tp2_r": 3.0, "time_stop": 20.0, "atr_pct_max": 0.0060}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        hi, lo = ta.donchian(b.high, b.low, int(self.p["channel_n"]))
        return {"atr": a, "dc_hi": hi, "dc_lo": lo, "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        if not self._g("ready", np.isfinite(a) and a > 0 and np.isfinite(ind["dc_lo"][t])):
            return None
        if not self._g("not_extreme_vol", ind["atr_pct"][t] < p["atr_pct_max"]):
            return None
        body = abs(c - b.open[t])
        prev_body = abs(b.close[t - 1] - b.open[t - 1])
        if not self._g("engulfs_prior_body", body >= p["body_ratio"] * prev_body
                       and body > 0):
            return None
        bull = (c > b.open[t] and b.close[t - 1] < b.open[t - 1]
                and c > b.open[t - 1] and b.low[t] <= ind["dc_lo"][t])
        bear = (c < b.open[t] and b.close[t - 1] > b.open[t - 1]
                and c < b.open[t - 1] and b.high[t] >= ind["dc_hi"][t])
        if not self._g("reversal_at_extreme", bull or bear):
            return None
        s = 1 if bull else -1
        stop = (b.low[t] - p["stop_buf_atr"] * a) if s > 0 else \
               (b.high[t] + p["stop_buf_atr"] * a)
        risk = abs(c - stop)
        if not self._g("stop_valid", risk > 0):
            return None
        return self._emit(Setup(
            side=s, entry_kind="close", stop=stop,
            targets=[(c + s * p["tp1_r"] * risk, 0.5),
                     (c + s * p["tp2_r"] * risk, 0.5)],
            time_stop_bars=int(p["time_stop"]), tag="long" if bull else "short"))


# ── S17 · Session-seasonality momentum ────────────────────────────────────────
class S17_SessionMomentum(Strategy):
    """Crypto is 24/7 but its participants are not. This trades a configurable
    UTC window with a momentum filter, so the seasonality claim is testable and
    the window is a searchable parameter rather than folklore."""
    id, name, warmup = "s17", "Session-Window Momentum", 300
    PARAMS = {"start_min": 780.0, "end_min": 960.0,   # 13:00–16:00 UTC (US open)
              "mom_bars": 12.0, "mom_atr": 0.75, "stop_atr": 1.5,
              "tp1_atr": 1.5, "tp2_atr": 3.0, "time_stop": 36.0}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        return {"atr": a, "mod": b.minute_of_day.astype(float),
                "ema": ta.ema(b.close, 50), "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        if not self._g("ready", np.isfinite(a) and a > 0):
            return None
        m = ind["mod"][t]
        if not self._g("in_session_window", p["start_min"] <= m <= p["end_min"]):
            return None
        k = int(p["mom_bars"])
        if not self._g("history", t - k >= 0):
            return None
        move = c - b.close[t - k]
        if not self._g("momentum>=min_atr", abs(move) >= p["mom_atr"] * a):
            return None
        s = 1 if move > 0 else -1
        if not self._g("ema50_agrees", (s > 0 and c > ind["ema"][t])
                       or (s < 0 and c < ind["ema"][t])):
            return None
        stop = c - s * p["stop_atr"] * a
        return self._emit(Setup(
            side=s, entry_kind="close", stop=stop,
            targets=[(c + s * p["tp1_atr"] * a, 0.5), (c + s * p["tp2_atr"] * a, 0.5)],
            time_stop_bars=int(p["time_stop"]), tag="long" if s > 0 else "short"))


# ── S18 · Dual-timeframe pullback (30m trend, 5m entry) ───────────────────────
class S18_DualTimeframePullback(Strategy):
    """Trend from a higher timeframe, timing from this one — the structure most
    discretionary traders actually use. The 30m series is built by aggregating
    six 5m bars, so it is causal by construction: the current 30m bar only ever
    uses 5m bars that have already closed."""
    id, name, warmup = "s18", "Dual-Timeframe Pullback", 400
    PARAMS = {"htf_bars": 6.0, "htf_fast": 12.0, "htf_slow": 26.0,
              "pull_rsi_lo": 40.0, "pull_rsi_hi": 60.0, "stop_atr": 1.5,
              "tp1_atr": 2.0, "tp2_atr": 4.0, "trail_atr": 2.5}

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        k = int(self.p["htf_bars"])
        n = len(b)
        # last CLOSED higher-timeframe close, forward-filled onto the 5m grid
        htf_close = np.full(n, np.nan)
        last = np.nan
        for i in range(n):
            if i % k == k - 1:          # this 5m bar completes a 30m bar
                last = b.close[i]
            htf_close[i] = last
        ok = ~np.isnan(htf_close)
        fast = np.full(n, np.nan)
        slow = np.full(n, np.nan)
        if ok.sum() > int(self.p["htf_slow"]):
            f = ta.ema(htf_close[ok], int(self.p["htf_fast"]))
            s_ = ta.ema(htf_close[ok], int(self.p["htf_slow"]))
            fast[ok], slow[ok] = f, s_
        return {"atr": a, "htf_fast": fast, "htf_slow": slow,
                "rsi": ta.rsi(b.close, 14), "ema": ta.ema(b.close, 20),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p, a, c = self.p, ind["atr"][t], b.close[t]
        f, s_ = ind["htf_fast"][t], ind["htf_slow"][t]
        if not self._g("ready", np.isfinite(a) and a > 0 and np.isfinite(f)
                       and np.isfinite(s_)):
            return None
        up, dn = f > s_, f < s_
        if not self._g("htf_trend", up or dn):
            return None
        r = ind["rsi"][t]
        pulled = (up and r <= p["pull_rsi_hi"]) or (dn and r >= p["pull_rsi_lo"])
        if not self._g("pulled_back", pulled):
            return None
        side = 1 if up else -1
        # trigger: price reclaims the fast 5m EMA in the trend direction
        if not self._g("reclaims_ema20", (side > 0 and c > ind["ema"][t])
                       or (side < 0 and c < ind["ema"][t])):
            return None
        stop = c - side * p["stop_atr"] * a
        return self._emit(Setup(
            side=side, entry_kind="close", stop=stop,
            targets=[(c + side * p["tp1_atr"] * a, 0.4),
                     (c + side * p["tp2_atr"] * a, 0.3),
                     (c + side * 10.0 * a, 0.3)],
            trail_atr_mult=p["trail_atr"], trail_after_leg=2,
            tag="long" if up else "short"))


ALL_EXTRA = [S11_DonchianBreakout, S12_ConnorsRSI2, S13_PercentBReversion,
             S14_NR7Expansion, S15_VolumeSpikeContinuation, S16_EngulfingAtExtreme,
             S17_SessionMomentum, S18_DualTimeframePullback]
