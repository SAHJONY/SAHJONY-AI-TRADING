"""The six OHLCV-only strategies from docs/btc_futures_5m_playbook.md.

S4 (CVD absorption), S7 (liquidation cascade), S8 (perp-spot basis) and S10
(order-book imbalance) are deliberately absent: they need trade ticks, funding /
OI / liquidation feeds, a synchronised index feed, and L2 book respectively. The
playbook says to disable them rather than approximate them from OHLCV, and an
OHLCV proxy would produce a backtest number that means nothing.

Each strategy is a pure decision engine: it reads precomputed causal indicators
and returns a Setup. It never touches the broker, the DB or the clock.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from backtest import indicators as ta
from backtest.data import Bars
from backtest.engine import Position, Setup, Strategy


def _upper_frac(o, h, l, c) -> float:
    """Where the close sits inside the bar's range, 0 (low) .. 1 (high)."""
    rng = h - l
    return 0.5 if rng <= 0 else float((c - l) / rng)


# ── S1 · Anchored VWAP σ-band fade ────────────────────────────────────────────
class S1_VWAPBandFade(Strategy):
    id = "s1"
    name = "AVWAP σ-Band Fade"
    warmup = 300

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        vwap, sig = ta.anchored_vwap(b.high, b.low, b.close, b.volume, b.day_id)
        a = ta.atr(b.high, b.low, b.close, 14)
        adx, _, _ = ta.adx(b.high, b.low, b.close, 14)
        return {"atr": a, "vwap": vwap, "sigma": sig, "adx": adx,
                "rsi2": ta.rsi(b.close, 2), "vsma": ta.sma(b.volume, 20),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        adx, ap = ind["adx"][t], ind["atr_pct"][t]
        if not np.isfinite(adx) or not np.isfinite(ap):
            return None
        if adx >= 20 or adx > ind["adx"][t - 3]:            # trend suppressor
            return None
        if ap >= 0.0030:                                     # LOW/NORMAL only
            return None
        if b.volume[t] < 1.5 * ind["vsma"][t]:
            return None
        vw, sg, a = ind["vwap"][t], ind["sigma"][t], ind["atr"][t]
        if not np.isfinite(sg) or sg <= 0:
            return None
        lo2, hi2 = vw - 2.0 * sg, vw + 2.0 * sg
        r2 = ind["rsi2"]

        if b.low[t] <= lo2 < b.close[t] and min(r2[t], r2[t - 1]) < 5:
            entry = lo2
            stop = min(vw - 2.5 * sg, entry - 1.2 * a)
            stop = max(stop, entry * (1 - 0.0055))           # cap the stop at 55 bps
            return Setup(side=1, entry_kind="limit", entry_price=entry, valid_bars=2,
                         stop=stop, targets=[(vw, 0.6), (vw + sg, 0.4)],
                         time_stop_bars=12, tag="long")
        if b.high[t] >= hi2 > b.close[t] and max(r2[t], r2[t - 1]) > 95:
            entry = hi2
            stop = max(vw + 2.5 * sg, entry + 1.2 * a)
            stop = min(stop, entry * (1 + 0.0055))
            return Setup(side=-1, entry_kind="limit", entry_price=entry, valid_bars=2,
                         stop=stop, targets=[(vw, 0.6), (vw - sg, 0.4)],
                         time_stop_bars=12, tag="short")
        return None

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        return "adx_trend" if ind["adx"][t] > 25 else None


# ── S2 · Session opening-range expansion ──────────────────────────────────────
class S2_OpeningRange(Strategy):
    id = "s2"
    name = "Session ORB Expansion"
    warmup = 300
    SESSIONS = (420, 810, 1380)      # 07:00 London, 13:30 CME/US, 23:00 CME reopen
    OR_BARS = 3
    MAX_BARS = 48                    # 4h session window

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        n = len(b)
        mod = b.minute_of_day
        a = ta.atr(b.high, b.low, b.close, 14)
        start = np.full(n, -1, dtype=int)
        cur = -1
        for i in range(n):
            if int(mod[i]) in self.SESSIONS:
                cur = i
            start[i] = cur
        or_hi = np.full(n, np.nan)
        or_lo = np.full(n, np.nan)
        atr_pre = np.full(n, np.nan)
        for i in range(n):
            s = start[i]
            if s < 1 or i < s + self.OR_BARS:
                continue
            or_hi[i] = b.high[s:s + self.OR_BARS].max()
            or_lo[i] = b.low[s:s + self.OR_BARS].min()
            atr_pre[i] = a[s - 1]
        self._traded = set()
        return {"atr": a, "or_hi": or_hi, "or_lo": or_lo, "start": start,
                "atr_pre": atr_pre, "ema50": ta.ema(b.close, 50),
                "vsma": ta.sma(b.volume, 20), "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        s = int(ind["start"][t])
        hi, lo, a_pre = ind["or_hi"][t], ind["or_lo"][t], ind["atr_pre"][t]
        if s < 0 or not np.isfinite(hi) or not np.isfinite(a_pre) or a_pre <= 0:
            return None
        if t - s > self.MAX_BARS or s in self._traded:
            return None
        if a_pre / b.close[s] < 0.0015:              # dead-tape sessions are skipped
            return None
        width = hi - lo
        if not (0.4 * a_pre <= width <= 2.5 * a_pre):
            return None
        if b.volume[t] < 1.3 * ind["vsma"][t]:
            return None
        a, e50 = ind["atr"][t], ind["ema50"][t]
        buf = 0.05 * a
        f = _upper_frac(b.open[t], b.high[t], b.low[t], b.close[t])

        if b.close[t] > hi and f >= 0.6 and b.close[t] > e50:
            self._traded.add(s)
            entry = hi + buf
            stop = (lo + hi) / 2 if width < 1.2 * a else entry - 1.0 * a
            return Setup(side=1, entry_kind="stop", entry_price=entry, valid_bars=2,
                         stop=stop,
                         targets=[(entry + width, 0.5), (entry + 2 * width, 0.3),
                                  (entry + 6 * width, 0.2)],
                         trail_atr_mult=3.0, trail_after_leg=2,
                         time_stop_bars=self.MAX_BARS, tag="long")
        if b.close[t] < lo and f <= 0.4 and b.close[t] < e50:
            self._traded.add(s)
            entry = lo - buf
            stop = (lo + hi) / 2 if width < 1.2 * a else entry + 1.0 * a
            return Setup(side=-1, entry_kind="stop", entry_price=entry, valid_bars=2,
                         stop=stop,
                         targets=[(entry - width, 0.5), (entry - 2 * width, 0.3),
                                  (entry - 6 * width, 0.2)],
                         trail_atr_mult=3.0, trail_after_leg=2,
                         time_stop_bars=self.MAX_BARS, tag="short")
        return None


# ── S3 · Squeeze compression breakout ─────────────────────────────────────────
class S3_SqueezeBreakout(Strategy):
    id = "s3"
    name = "Squeeze Compression Breakout"
    warmup = 400

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        mid, bbu, bbl = ta.bollinger(b.close, 20, 2.0)
        kmid, kcu, kcl = ta.keltner(b.high, b.low, b.close, 20, 1.5)
        sq = (bbu < kcu) & (bbl > kcl)
        with np.errstate(invalid="ignore"):
            bw = (bbu - bbl) / mid
        hh, ll = ta.rolling_max(b.high, 20), ta.rolling_min(b.low, 20)
        base = (hh + ll) / 2.0
        mom = ta.linreg_value(b.close - (base + ta.sma(b.close, 20)) / 2.0, 20)
        return {"atr": a, "sq": sq, "kcu": kcu, "kcl": kcl, "mom": mom,
                "bw_pct": ta.rolling_pct_rank(bw, 200), "ema21": ta.ema(b.close, 21),
                "vsma": ta.sma(b.volume, 20), "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        sq, ap = ind["sq"], ind["atr_pct"][t]
        if not np.isfinite(ap) or ap >= 0.0060:      # no compression to trade in EXTREME
            return None
        if sq[t] or not sq[t - 1]:                   # must fire on this bar
            return None
        run = 0
        while run < 60 and sq[t - 1 - run]:
            run += 1
        if run < 6:
            return None
        bwp = ind["bw_pct"][t - 1]
        if not np.isfinite(bwp) or bwp > 0.20:
            return None
        if b.volume[t] < 1.4 * ind["vsma"][t]:
            return None
        i0 = t - run
        sq_hi, sq_lo = b.high[i0:t].max(), b.low[i0:t].min()
        rng = sq_hi - sq_lo
        if rng <= 0:
            return None
        mom, a, c = ind["mom"], ind["atr"][t], b.close[t]

        if mom[t] > 0 and mom[t] > mom[t - 1] and c > ind["kcu"][t] and c > sq_hi:
            stop = max(sq_lo, c - 1.5 * a)
            return Setup(side=1, entry_kind="close", stop=stop,
                         targets=[(c + 1.5 * rng, 0.5), (c + 3.0 * rng, 0.3),
                                  (c + 12.0 * rng, 0.2)],
                         tag="long", meta={"sq_hi": sq_hi, "sq_lo": sq_lo})
        if mom[t] < 0 and mom[t] < mom[t - 1] and c < ind["kcl"][t] and c < sq_lo:
            stop = min(sq_hi, c + 1.5 * a)
            return Setup(side=-1, entry_kind="close", stop=stop,
                         targets=[(c - 1.5 * rng, 0.5), (c - 3.0 * rng, 0.3),
                                  (c - 12.0 * rng, 0.2)],
                         tag="short", meta={"sq_hi": sq_hi, "sq_lo": sq_lo})
        return None

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        m = pos.setup.meta
        # failed expansion: price closes back inside the compression range
        if m and m["sq_lo"] <= b.close[t] <= m["sq_hi"]:
            return "back_in_range"
        if pos.legs_done >= 2:                        # runner rides EMA21
            if pos.side > 0 and b.close[t] < ind["ema21"][t]:
                return "ema21_break"
            if pos.side < 0 and b.close[t] > ind["ema21"][t]:
                return "ema21_break"
        return None


# ── S5 · Liquidity sweep reclaim ──────────────────────────────────────────────
class S5_SweepReclaim(Strategy):
    id = "s5"
    name = "Liquidity Sweep Reclaim"
    warmup = 300
    SWEEP_WINDOW = 3
    MIN_LEVEL_AGE = 12

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        fh, fl, fhi, fli = ta.fractals(b.high, b.low, 3)
        return {"atr": a, "fh": fh, "fl": fl, "fh_idx": fhi.astype(float),
                "fl_idx": fli.astype(float), "rsi": ta.rsi(b.close, 14),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        a = ind["atr"][t]
        if not np.isfinite(a) or a <= 0:
            return None
        w = self.SWEEP_WINDOW
        rng_frac = (b.high[t] - b.low[t]) / a
        if rng_frac < 0.8:                       # reclaim bar must have conviction
            return None
        f = _upper_frac(b.open[t], b.high[t], b.low[t], b.close[t])
        c = b.close[t]

        lvl_lo, i_lo = ind["fl"][t], int(ind["fl_idx"][t])
        if np.isfinite(lvl_lo) and i_lo >= 0 and t - i_lo >= self.MIN_LEVEL_AGE:
            sweep_lo = b.low[t - w + 1:t + 1].min()
            if sweep_lo <= lvl_lo - 0.15 * a and c > lvl_lo and f >= 0.667:
                stop = sweep_lo - 0.25 * a
                if c - stop <= 1.5 * a:          # else the wick is too big to size
                    tgt_hi = ind["fh"][t]
                    if not np.isfinite(tgt_hi) or tgt_hi <= c:
                        tgt_hi = c + 3.0 * (c - stop)
                    return Setup(side=1, entry_kind="close", stop=stop,
                                 targets=[((c + tgt_hi) / 2, 0.4), (tgt_hi, 0.4),
                                          (c + 6 * (c - stop), 0.2)],
                                 trail_atr_mult=2.0, trail_after_leg=2,
                                 tag="long", meta={"sweep": sweep_lo})

        lvl_hi, i_hi = ind["fh"][t], int(ind["fh_idx"][t])
        if np.isfinite(lvl_hi) and i_hi >= 0 and t - i_hi >= self.MIN_LEVEL_AGE:
            sweep_hi = b.high[t - w + 1:t + 1].max()
            if sweep_hi >= lvl_hi + 0.15 * a and c < lvl_hi and f <= 0.333:
                stop = sweep_hi + 0.25 * a
                if stop - c <= 1.5 * a:
                    tgt_lo = ind["fl"][t]
                    if not np.isfinite(tgt_lo) or tgt_lo >= c:
                        tgt_lo = c - 3.0 * (stop - c)
                    return Setup(side=-1, entry_kind="close", stop=stop,
                                 targets=[((c + tgt_lo) / 2, 0.4), (tgt_lo, 0.4),
                                          (c - 6 * (stop - c), 0.2)],
                                 trail_atr_mult=2.0, trail_after_leg=2,
                                 tag="short", meta={"sweep": sweep_hi})
        return None

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        sw = pos.setup.meta.get("sweep")
        if sw is not None:
            if pos.side > 0 and b.close[t] < sw:
                return "reclaim_failed"
            if pos.side < 0 and b.close[t] > sw:
                return "reclaim_failed"
        if pos.legs_done == 0 and t - pos.entry_bar >= 10:
            return "no_progress"
        return None


# ── S6 · EMA ribbon pullback continuation ─────────────────────────────────────
class S6_RibbonPullback(Strategy):
    id = "s6"
    name = "EMA Ribbon Pullback"
    warmup = 400
    MAX_PER_LEG = 2

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        adx, _, _ = ta.adx(b.high, b.low, b.close, 14)
        self._leg_ref = None
        self._leg_count = 0
        return {"atr": a, "adx": adx, "ema8": ta.ema(b.close, 8),
                "ema21": ta.ema(b.close, 21), "ema55": ta.ema(b.close, 55),
                "ema200": ta.ema(b.close, 200), "vsma": ta.sma(b.volume, 20),
                "atr_pct": a / b.close}

    def _leg_ok(self, ref: float) -> bool:
        if self._leg_ref is None or abs(ref - self._leg_ref) > 1e-9:
            self._leg_ref, self._leg_count = ref, 0
        return self._leg_count < self.MAX_PER_LEG

    def signal(self, t, b, ind) -> Optional[Setup]:
        e8, e21, e55, e200 = (ind["ema8"], ind["ema21"], ind["ema55"], ind["ema200"])
        a, adx, ap = ind["atr"][t], ind["adx"][t], ind["atr_pct"][t]
        if not all(np.isfinite(x[t]) for x in (e8, e21, e55, e200)):
            return None
        if not np.isfinite(adx) or adx <= 22 or adx <= ind["adx"][t - 3]:
            return None
        if not np.isfinite(ap) or ap >= 0.0060:
            return None
        c = b.close[t]
        f = _upper_frac(b.open[t], b.high[t], b.low[t], b.close[t])

        up = (e8[t] > e21[t] > e55[t] and e8[t] > e8[t - 5] and e21[t] > e21[t - 5]
              and e55[t] > e55[t - 5] and c > e200[t])
        dn = (e8[t] < e21[t] < e55[t] and e8[t] < e8[t - 5] and e21[t] < e21[t - 5]
              and e55[t] < e55[t - 5] and c < e200[t])

        if up:
            w = b.high[t - 10:t + 1]
            k = int(w.argmax())
            imp_hi = float(w[k])
            imp_i = t - 10 + k
            if imp_hi < b.high[t - 30:t - 10].max():        # must be a fresh leg
                return None
            leg_lo = float(b.low[max(0, imp_i - 30):imp_i + 1].min())
            leg = imp_hi - leg_lo
            pull_bars = t - imp_i
            if leg <= 0 or not (1 <= pull_bars <= 8):
                return None
            pull_lo = float(b.low[imp_i:t + 1].min())
            retr = (imp_hi - pull_lo) / leg
            if not (0.382 <= retr <= 0.618):
                return None
            if not (e55[t] - 0.3 * a <= pull_lo <= e21[t]):
                return None
            v_imp = b.volume[max(0, imp_i - 5):imp_i + 1].mean()
            if b.volume[imp_i:t + 1].mean() >= 0.8 * v_imp:
                return None
            # spec trigger: a close back above EMA8 after price pulled into the
            # ribbon. Requiring the cross on this exact bar was over-strict —
            # it cut 60 valid setups to 3 in validation.
            if not (c > e8[t] and pull_lo <= e8[t] and f >= 0.5):
                return None
            if not self._leg_ok(imp_hi):
                return None
            stop = max(min(e55[t] - 0.5 * a, pull_lo), c - 1.5 * a)
            if c - stop <= 0:
                return None
            self._leg_count += 1
            return Setup(side=1, entry_kind="close", stop=stop,
                         targets=[(imp_hi, 0.4), (pull_lo + 1.618 * leg, 0.3),
                                  (c + 10 * (c - stop), 0.3)],
                         trail_atr_mult=2.5, trail_after_leg=2, tag="long")

        if dn:
            w = b.low[t - 10:t + 1]
            k = int(w.argmin())
            imp_lo = float(w[k])
            imp_i = t - 10 + k
            if imp_lo > b.low[t - 30:t - 10].min():
                return None
            leg_hi = float(b.high[max(0, imp_i - 30):imp_i + 1].max())
            leg = leg_hi - imp_lo
            pull_bars = t - imp_i
            if leg <= 0 or not (1 <= pull_bars <= 8):
                return None
            pull_hi = float(b.high[imp_i:t + 1].max())
            retr = (pull_hi - imp_lo) / leg
            if not (0.382 <= retr <= 0.618):
                return None
            if not (e21[t] <= pull_hi <= e55[t] + 0.3 * a):
                return None
            v_imp = b.volume[max(0, imp_i - 5):imp_i + 1].mean()
            if b.volume[imp_i:t + 1].mean() >= 0.8 * v_imp:
                return None
            if not (c < e8[t] and pull_hi >= e8[t] and f <= 0.5):
                return None
            if not self._leg_ok(imp_lo):
                return None
            stop = min(max(e55[t] + 0.5 * a, pull_hi), c + 1.5 * a)
            if stop - c <= 0:
                return None
            self._leg_count += 1
            return Setup(side=-1, entry_kind="close", stop=stop,
                         targets=[(imp_lo, 0.4), (pull_hi - 1.618 * leg, 0.3),
                                  (c - 10 * (stop - c), 0.3)],
                         trail_atr_mult=2.5, trail_after_leg=2, tag="short")
        return None

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        if pos.side > 0 and ind["ema8"][t] < ind["ema21"][t]:
            return "ribbon_cross"
        if pos.side < 0 and ind["ema8"][t] > ind["ema21"][t]:
            return "ribbon_cross"
        return None


# ── S9 · Failed breakout range fade ───────────────────────────────────────────
class S9_FailedBreakFade(Strategy):
    id = "s9"
    name = "Failed Breakout Fade"
    warmup = 400
    WINDOW = 3

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        dc_hi, dc_lo = ta.donchian(b.high, b.low, 20)
        mid, bbu, bbl = ta.bollinger(b.close, 20, 2.0)
        with np.errstate(invalid="ignore"):
            bw = (bbu - bbl) / mid
        self._faded = {}
        return {"atr": a, "dc_hi": dc_hi, "dc_lo": dc_lo, "rsi2": ta.rsi(b.close, 2),
                "vsma": ta.sma(b.volume, 20), "bw_pct": ta.rolling_pct_rank(bw, 200),
                "atr_pct": a / b.close}

    def _budget(self, key, side) -> bool:
        k = (round(key, 1), side)
        used = self._faded.get(k, 0)
        if used >= 2:
            return False
        self._faded[k] = used + 1
        return True

    def signal(self, t, b, ind) -> Optional[Setup]:
        a, ap = ind["atr"][t], ind["atr_pct"][t]
        hi, lo = ind["dc_hi"][t], ind["dc_lo"][t]
        bwp = ind["bw_pct"][t]
        if not all(np.isfinite(x) for x in (a, ap, hi, lo, bwp)) or a <= 0:
            return None
        if ap >= 0.0030 or bwp <= 0.30:      # ranging tape only, and not a squeeze
            return None
        width = hi - lo
        # NB: the playbook's original "0.5-3.0 x ATR" window is arithmetically
        # wrong for a *20-bar* Donchian. For a random walk the expected n-bar
        # range is ~1.6·σ·√n, and ATR(14) ≈ 1.13·σ, so a 20-bar range sits near
        # 6.4x ATR by construction — the old window matched 0.8% of bars. This
        # band keeps the intent (a normal-width range: not a squeeze, not an
        # already-expanded move) at the right scale.
        if not (3.0 * a <= width <= 8.0 * a):
            return None
        c, w = b.close[t], self.WINDOW
        r2, vs = ind["rsi2"], ind["vsma"]

        # failed downside break -> fade long
        brk = [i for i in range(t - w + 1, t + 1) if b.low[i] < lo]
        if brk and c > lo:
            i0 = brk[0]
            if b.volume[i0] < 1.2 * vs[i0] and min(r2[i] for i in brk) < 10:
                ext = float(min(b.low[i] for i in brk))
                stop = max(ext - 0.35 * width, c - 1.2 * a)
                if c - stop > 0 and self._budget(lo, 1):
                    return Setup(side=1, entry_kind="close", stop=stop,
                                 targets=[((hi + lo) / 2, 0.5), (hi, 0.5)],
                                 time_stop_bars=15, tag="long",
                                 meta={"lo": lo, "hi": hi, "side_lvl": lo})

        # failed upside break -> fade short
        brk = [i for i in range(t - w + 1, t + 1) if b.high[i] > hi]
        if brk and c < hi:
            i0 = brk[0]
            if b.volume[i0] < 1.2 * vs[i0] and max(r2[i] for i in brk) > 90:
                ext = float(max(b.high[i] for i in brk))
                stop = min(ext + 0.35 * width, c + 1.2 * a)
                if stop - c > 0 and self._budget(hi, -1):
                    return Setup(side=-1, entry_kind="close", stop=stop,
                                 targets=[((hi + lo) / 2, 0.5), (lo, 0.5)],
                                 time_stop_bars=15, tag="short",
                                 meta={"lo": lo, "hi": hi, "side_lvl": hi})
        return None

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        # a second, *confirmed* break of the same side kills the range thesis
        lvl = pos.setup.meta.get("side_lvl")
        if lvl is None:
            return None
        heavy = b.volume[t] >= 1.5 * ind["vsma"][t]
        if pos.side > 0 and b.close[t] < lvl and heavy:
            return "range_broke"
        if pos.side < 0 and b.close[t] > lvl and heavy:
            return "range_broke"
        return None


ALL = [S1_VWAPBandFade, S2_OpeningRange, S3_SqueezeBreakout,
       S5_SweepReclaim, S6_RibbonPullback, S9_FailedBreakFade]
REGISTRY = {c.id: c for c in ALL}
