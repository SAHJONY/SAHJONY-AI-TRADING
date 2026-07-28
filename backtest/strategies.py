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


def _zone_ok(mode: str, fib_ok: bool, ema_ok: bool) -> bool:
    """Which definition of "the pullback area" has to agree — see S6.PARAMS."""
    if mode == "fib":
        return fib_ok
    if mode == "ema":
        return ema_ok
    return fib_ok and ema_ok


def _upper_frac(o, h, l, c) -> float:
    """Where the close sits inside the bar's range, 0 (low) .. 1 (high)."""
    rng = h - l
    return 0.5 if rng <= 0 else float((c - l) / rng)


# ── S1 · Anchored VWAP σ-band fade ────────────────────────────────────────────
class S1_VWAPBandFade(Strategy):
    id = "s1"
    name = "AVWAP σ-Band Fade"
    warmup = 300
    # The funnel showed six hard-AND conditions leaving 4 setups in 51k bars —
    # the conjunction, not any one gate, was the problem. The context conditions
    # are now scored instead of ANDed; `min_score` = 1.0 requires all of them and
    # reproduces the specification exactly. Lowering it trades selectivity for
    # frequency, and the right value must be found on real data, not chosen here.
    PARAMS = {
        "band_sigma": 2.0, "stop_sigma": 2.5, "stop_atr_mult": 1.2,
        "stop_cap_pct": 0.0055, "adx_max": 20.0, "atr_pct_max": 0.0030,
        "anchor_min_bars": 24.0, "vol_mult": 1.5, "rsi_lo": 5.0, "rsi_hi": 95.0,
        "min_score": 1.0, "time_stop": 12.0, "adx_exit": 25.0, "tp1_frac": 0.6,
    }

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        vwap, sig = ta.anchored_vwap(b.high, b.low, b.close, b.volume, b.day_id)
        a = ta.atr(b.high, b.low, b.close, 14)
        adx, _, _ = ta.adx(b.high, b.low, b.close, 14)
        # bars elapsed since the 00:00 UTC re-anchor — σ is meaningless right
        # after it, which is what put the stop inside the fee in validation
        d = b.day_id
        age = np.zeros(len(b), dtype=float)
        k = 0
        for i in range(len(b)):
            k = 0 if (i and d[i] != d[i - 1]) else k + 1
            age[i] = k
        return {"atr": a, "vwap": vwap, "sigma": sig, "adx": adx, "anchor_age": age,
                "rsi2": ta.rsi(b.close, 2), "vsma": ta.sma(b.volume, 20),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        p = self.p
        adx, ap = ind["adx"][t], ind["atr_pct"][t]
        if not self._g("indicators_ready", np.isfinite(adx) and np.isfinite(ap)):
            return None
        vw, sg, a = ind["vwap"][t], ind["sigma"][t], ind["atr"][t]
        if not self._g("sigma>0", np.isfinite(sg) and sg > 0):
            return None
        band = p["band_sigma"]
        lo2, hi2 = vw - band * sg, vw + band * sg
        pierce_lo = b.low[t] <= lo2 < b.close[t]
        pierce_hi = b.high[t] >= hi2 > b.close[t]
        # the pierce is structural — it defines the entry price, so it is never
        # scored away; everything else is context and is scored
        if not self._g("sigma_band_pierce_reject", pierce_lo or pierce_hi):
            return None
        side = 1 if pierce_lo else -1
        r2 = ind["rsi2"]
        conds = {
            "adx<max_and_flat": bool(adx < p["adx_max"] and adx <= ind["adx"][t - 3]),
            "atr%<max": bool(ap < p["atr_pct_max"]),
            "anchor_age_ok": bool(ind["anchor_age"][t] >= p["anchor_min_bars"]),
            "vol>=mult": bool(b.volume[t] >= p["vol_mult"] * ind["vsma"][t]),
            "rsi2_extreme": bool(min(r2[t], r2[t - 1]) < p["rsi_lo"] if side > 0
                                 else max(r2[t], r2[t - 1]) > p["rsi_hi"]),
        }
        for k, v in conds.items():
            self._g(k, v)
        score = sum(conds.values()) / len(conds)
        if not self._g("confluence_score>=min", score >= p["min_score"] - 1e-9):
            return None

        f1 = p["tp1_frac"]
        if side > 0:
            entry = lo2
            stop = min(vw - p["stop_sigma"] * sg, entry - p["stop_atr_mult"] * a)
            stop = max(stop, entry * (1 - p["stop_cap_pct"]))
            return self._emit(Setup(
                side=1, entry_kind="limit", entry_price=entry, valid_bars=2,
                stop=stop, targets=[(vw, f1), (vw + sg, 1 - f1)],
                time_stop_bars=int(p["time_stop"]), tag="long"))
        entry = hi2
        stop = max(vw + p["stop_sigma"] * sg, entry + p["stop_atr_mult"] * a)
        stop = min(stop, entry * (1 + p["stop_cap_pct"]))
        return self._emit(Setup(
            side=-1, entry_kind="limit", entry_price=entry, valid_bars=2,
            stop=stop, targets=[(vw, f1), (vw - sg, 1 - f1)],
            time_stop_bars=int(p["time_stop"]), tag="short"))

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        return "adx_trend" if ind["adx"][t] > self.p["adx_exit"] else None


# ── S2 · Session opening-range expansion ──────────────────────────────────────
class S2_OpeningRange(Strategy):
    id = "s2"
    name = "Session ORB Expansion"
    warmup = 300
    SESSIONS = (420, 810, 1380)      # 07:00 London, 13:30 CME/US, 23:00 CME reopen
    OR_BARS = 3
    MAX_BARS = 48                    # 4h session window
    PARAMS = {
        "min_session_atr_pct": 0.0015, "width_min_atr": 0.4, "width_max_atr": 2.5,
        "vol_mult": 1.3, "close_frac": 0.6, "buf_atr": 0.05, "stop_atr": 1.0,
        "narrow_mult": 1.2, "tp1_mult": 1.0, "tp2_mult": 2.0, "trail_atr": 3.0,
    }

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
        if not self._g("OR_complete", s >= 0 and np.isfinite(hi)
                       and np.isfinite(a_pre) and a_pre > 0):
            return None
        if not self._g("in_session_window", t - s <= self.MAX_BARS
                       and s not in self._traded):
            return None
        p = self.p
        if not self._g("session_atr%>=min", a_pre / b.close[s] >= p["min_session_atr_pct"]):
            return None
        width = hi - lo
        if not self._g("OR_width_in_band",
                       p["width_min_atr"] * a_pre <= width <= p["width_max_atr"] * a_pre):
            return None
        if not self._g("vol>=mult", b.volume[t] >= p["vol_mult"] * ind["vsma"][t]):
            return None
        a, e50 = ind["atr"][t], ind["ema50"][t]
        buf = p["buf_atr"] * a
        f = _upper_frac(b.open[t], b.high[t], b.low[t], b.close[t])
        up, dn = b.close[t] > hi, b.close[t] < lo
        if not self._g("close_beyond_OR", up or dn):
            return None
        cf = p["close_frac"]
        if not self._g("close_in_outer_band", (up and f >= cf) or (dn and f <= 1 - cf)):
            return None
        if not self._g("ema50_agrees",
                       (up and f >= cf and b.close[t] > e50)
                       or (dn and f <= 1 - cf and b.close[t] < e50)):
            return None

        if b.close[t] > hi and f >= cf and b.close[t] > e50:
            self._traded.add(s)
            entry = hi + buf
            stop = ((lo + hi) / 2 if width < p["narrow_mult"] * a
                    else entry - p["stop_atr"] * a)
            return self._emit(Setup(
                side=1, entry_kind="stop", entry_price=entry, valid_bars=2,
                stop=stop,
                targets=[(entry + p["tp1_mult"] * width, 0.5),
                         (entry + p["tp2_mult"] * width, 0.3),
                         (entry + 6 * width, 0.2)],
                trail_atr_mult=p["trail_atr"], trail_after_leg=2,
                time_stop_bars=self.MAX_BARS, tag="long"))
        if b.close[t] < lo and f <= 1 - cf and b.close[t] < e50:
            self._traded.add(s)
            entry = lo - buf
            stop = ((lo + hi) / 2 if width < p["narrow_mult"] * a
                    else entry + p["stop_atr"] * a)
            return self._emit(Setup(
                side=-1, entry_kind="stop", entry_price=entry, valid_bars=2,
                stop=stop,
                targets=[(entry - p["tp1_mult"] * width, 0.5),
                         (entry - p["tp2_mult"] * width, 0.3),
                         (entry - 6 * width, 0.2)],
                trail_atr_mult=p["trail_atr"], trail_after_leg=2,
                time_stop_bars=self.MAX_BARS, tag="short"))
        return None


# ── S3 · Squeeze compression breakout ─────────────────────────────────────────
class S3_SqueezeBreakout(Strategy):
    id = "s3"
    name = "Squeeze Compression Breakout"
    warmup = 400
    PARAMS = {
        "min_run": 6.0, "bw_pct_max": 0.20, "vol_mult": 1.4, "atr_pct_max": 0.0060,
        "stop_atr": 1.5, "tp1_mult": 1.5, "tp2_mult": 3.0,
    }

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
        p = self.p
        sq, ap = ind["sq"], ind["atr_pct"][t]
        if not self._g("not_extreme_vol", np.isfinite(ap) and ap < p["atr_pct_max"]):
            return None
        if not self._g("squeeze_fires", (not sq[t]) and sq[t - 1]):
            return None
        run = 0
        while run < 60 and sq[t - 1 - run]:
            run += 1
        if not self._g("squeeze_run>=min", run >= p["min_run"]):
            return None
        bwp = ind["bw_pct"][t - 1]
        if not self._g("bandwidth_bottom_pct",
                       np.isfinite(bwp) and bwp <= p["bw_pct_max"]):
            return None
        if not self._g("vol>=mult", b.volume[t] >= p["vol_mult"] * ind["vsma"][t]):
            return None
        i0 = t - run
        sq_hi, sq_lo = b.high[i0:t].max(), b.low[i0:t].min()
        rng = sq_hi - sq_lo
        if not self._g("range>0", rng > 0):
            return None
        mom, a, c = ind["mom"], ind["atr"][t], b.close[t]
        up = mom[t] > 0 and mom[t] > mom[t - 1] and c > ind["kcu"][t] and c > sq_hi
        dn = mom[t] < 0 and mom[t] < mom[t - 1] and c < ind["kcl"][t] and c < sq_lo
        if not self._g("momentum+KC+range_break", up or dn):
            return None

        if up:
            stop = max(sq_lo, c - p["stop_atr"] * a)
            return self._emit(Setup(
                side=1, entry_kind="close", stop=stop,
                targets=[(c + p["tp1_mult"] * rng, 0.5), (c + p["tp2_mult"] * rng, 0.3),
                         (c + 12.0 * rng, 0.2)],
                tag="long", meta={"sq_hi": sq_hi, "sq_lo": sq_lo}))
        stop = min(sq_hi, c + p["stop_atr"] * a)
        return self._emit(Setup(
            side=-1, entry_kind="close", stop=stop,
            targets=[(c - p["tp1_mult"] * rng, 0.5), (c - p["tp2_mult"] * rng, 0.3),
                     (c - 12.0 * rng, 0.2)],
            tag="short", meta={"sq_hi": sq_hi, "sq_lo": sq_lo}))

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
    PARAMS = {
        "sweep_atr": 0.15, "min_level_age": 12.0, "reclaim_range_atr": 0.8,
        "close_third": 0.667, "stop_buf_atr": 0.25, "stop_max_atr": 1.5,
        "trail_atr": 2.0, "no_progress_bars": 10.0,
    }

    def prepare(self, b: Bars) -> Dict[str, np.ndarray]:
        a = ta.atr(b.high, b.low, b.close, 14)
        fh, fl, fhi, fli = ta.fractals(b.high, b.low, 3)
        return {"atr": a, "fh": fh, "fl": fl, "fh_idx": fhi.astype(float),
                "fl_idx": fli.astype(float), "rsi": ta.rsi(b.close, 14),
                "atr_pct": a / b.close}

    def signal(self, t, b, ind) -> Optional[Setup]:
        a = ind["atr"][t]
        if not self._g("atr_ready", np.isfinite(a) and a > 0):
            return None
        p = self.p
        w = self.SWEEP_WINDOW
        rng_frac = (b.high[t] - b.low[t]) / a
        if not self._g("reclaim_bar>=min_atr", rng_frac >= p["reclaim_range_atr"]):
            return None
        f = _upper_frac(b.open[t], b.high[t], b.low[t], b.close[t])
        c = b.close[t]

        lvl_lo, i_lo = ind["fl"][t], int(ind["fl_idx"][t])
        if self._g("level_age>=min", np.isfinite(lvl_lo) and i_lo >= 0
                   and t - i_lo >= p["min_level_age"]):
            sweep_lo = b.low[t - w + 1:t + 1].min()
            if (self._g("swept_by>=min_atr", sweep_lo <= lvl_lo - p["sweep_atr"] * a)
                    and self._g("closed_back_inside", c > lvl_lo)
                    and self._g("close_in_outer_third", f >= p["close_third"])):
                stop = sweep_lo - p["stop_buf_atr"] * a
                if self._g("stop<=max_atr", c - stop <= p["stop_max_atr"] * a):
                    tgt_hi = ind["fh"][t]
                    if not np.isfinite(tgt_hi) or tgt_hi <= c:
                        tgt_hi = c + 3.0 * (c - stop)
                    return self._emit(Setup(
                        side=1, entry_kind="close", stop=stop,
                        targets=[((c + tgt_hi) / 2, 0.4), (tgt_hi, 0.4),
                                 (c + 6 * (c - stop), 0.2)],
                        trail_atr_mult=p["trail_atr"], trail_after_leg=2,
                        tag="long", meta={"sweep": sweep_lo}))

        lvl_hi, i_hi = ind["fh"][t], int(ind["fh_idx"][t])
        if self._g("level_age>=min", np.isfinite(lvl_hi) and i_hi >= 0
                   and t - i_hi >= p["min_level_age"]):
            sweep_hi = b.high[t - w + 1:t + 1].max()
            if (self._g("swept_by>=min_atr", sweep_hi >= lvl_hi + p["sweep_atr"] * a)
                    and self._g("closed_back_inside", c < lvl_hi)
                    and self._g("close_in_outer_third", f <= 1 - p["close_third"])):
                stop = sweep_hi + p["stop_buf_atr"] * a
                if self._g("stop<=max_atr", stop - c <= p["stop_max_atr"] * a):
                    tgt_lo = ind["fl"][t]
                    if not np.isfinite(tgt_lo) or tgt_lo >= c:
                        tgt_lo = c - 3.0 * (stop - c)
                    return self._emit(Setup(
                        side=-1, entry_kind="close", stop=stop,
                        targets=[((c + tgt_lo) / 2, 0.4), (tgt_lo, 0.4),
                                 (c - 6 * (stop - c), 0.2)],
                        trail_atr_mult=p["trail_atr"], trail_after_leg=2,
                        tag="short", meta={"sweep": sweep_hi}))
        return None

    def manage(self, t, b, ind, pos: Position) -> Optional[str]:
        sw = pos.setup.meta.get("sweep")
        if sw is not None:
            if pos.side > 0 and b.close[t] < sw:
                return "reclaim_failed"
            if pos.side < 0 and b.close[t] > sw:
                return "reclaim_failed"
        if pos.legs_done == 0 and t - pos.entry_bar >= self.p["no_progress_bars"]:
            return "no_progress"
        return None


# ── S6 · EMA ribbon pullback continuation ─────────────────────────────────────
class S6_RibbonPullback(Strategy):
    id = "s6"
    name = "EMA Ribbon Pullback"
    warmup = 400
    MAX_PER_LEG = 2
    # `zone_mode` exists because the funnel showed the Fib 38-62% window and the
    # EMA21-55 zone are two definitions of the same "pullback area" that agree
    # only 43% of the time; requiring both costs ~93% of surviving setups.
    # "both" is the specification; "fib" / "ema" pick one. Which (if either) is
    # better is a real-data question.
    PARAMS = {
        "adx_min": 22.0, "retr_lo": 0.382, "retr_hi": 0.618, "max_pull_bars": 8.0,
        "vol_ratio": 0.8, "stop_atr": 1.5, "trail_atr": 2.5, "zone_tol_atr": 0.3,
        "atr_pct_max": 0.0060, "zone_mode": "both",
    }

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
        if not self._g("emas_ready", all(np.isfinite(x[t]) for x in (e8, e21, e55, e200))):
            return None
        p = self.p
        if not self._g("adx>min_rising", np.isfinite(adx) and adx > p["adx_min"]
                       and adx > ind["adx"][t - 3]):
            return None
        if not self._g("not_extreme_vol", np.isfinite(ap) and ap < p["atr_pct_max"]):
            return None
        c = b.close[t]
        f = _upper_frac(b.open[t], b.high[t], b.low[t], b.close[t])

        up = (e8[t] > e21[t] > e55[t] and e8[t] > e8[t - 5] and e21[t] > e21[t - 5]
              and e55[t] > e55[t - 5] and c > e200[t])
        dn = (e8[t] < e21[t] < e55[t] and e8[t] < e8[t - 5] and e21[t] < e21[t - 5]
              and e55[t] < e55[t - 5] and c < e200[t])
        if not self._g("ribbon_stacked+ema200", up or dn):
            return None

        if up:
            w = b.high[t - 10:t + 1]
            k = int(w.argmax())
            imp_hi = float(w[k])
            imp_i = t - 10 + k
            if not self._g("fresh_20bar_extreme", imp_hi >= b.high[t - 30:t - 10].max()):
                return None
            leg_lo = float(b.low[max(0, imp_i - 30):imp_i + 1].min())
            leg = imp_hi - leg_lo
            pull_bars = t - imp_i
            if not self._g("pullback<=max_bars",
                           leg > 0 and 1 <= pull_bars <= p["max_pull_bars"]):
                return None
            pull_lo = float(b.low[imp_i:t + 1].min())
            retr = (imp_hi - pull_lo) / leg
            fib_ok = p["retr_lo"] <= retr <= p["retr_hi"]
            ema_ok = e55[t] - p["zone_tol_atr"] * a <= pull_lo <= e21[t]
            if not self._g("pullback_zone", _zone_ok(p["zone_mode"], fib_ok, ema_ok)):
                return None
            v_imp = b.volume[max(0, imp_i - 5):imp_i + 1].mean()
            if not self._g("low_volume_pullback",
                           b.volume[imp_i:t + 1].mean() < p["vol_ratio"] * v_imp):
                return None
            # spec trigger: a close back above EMA8 after price pulled into the
            # ribbon. Requiring the cross on this exact bar was over-strict —
            # it cut 60 valid setups to 3 in validation.
            if not self._g("close_back_above_ema8",
                           c > e8[t] and pull_lo <= e8[t] and f >= 0.5):
                return None
            if not self._g("leg_budget<=2", self._leg_ok(imp_hi)):
                return None
            stop = max(min(e55[t] - 0.5 * a, pull_lo), c - p["stop_atr"] * a)
            if not self._g("stop_valid", c - stop > 0):
                return None
            self._leg_count += 1
            return self._emit(Setup(
                side=1, entry_kind="close", stop=stop,
                targets=[(imp_hi, 0.4), (pull_lo + 1.618 * leg, 0.3),
                         (c + 10 * (c - stop), 0.3)],
                trail_atr_mult=p["trail_atr"], trail_after_leg=2, tag="long"))

        if dn:
            w = b.low[t - 10:t + 1]
            k = int(w.argmin())
            imp_lo = float(w[k])
            imp_i = t - 10 + k
            if not self._g("fresh_20bar_extreme", imp_lo <= b.low[t - 30:t - 10].min()):
                return None
            leg_hi = float(b.high[max(0, imp_i - 30):imp_i + 1].max())
            leg = leg_hi - imp_lo
            pull_bars = t - imp_i
            if not self._g("pullback<=max_bars",
                           leg > 0 and 1 <= pull_bars <= p["max_pull_bars"]):
                return None
            pull_hi = float(b.high[imp_i:t + 1].max())
            retr = (pull_hi - imp_lo) / leg
            fib_ok = p["retr_lo"] <= retr <= p["retr_hi"]
            ema_ok = e21[t] <= pull_hi <= e55[t] + p["zone_tol_atr"] * a
            if not self._g("pullback_zone", _zone_ok(p["zone_mode"], fib_ok, ema_ok)):
                return None
            v_imp = b.volume[max(0, imp_i - 5):imp_i + 1].mean()
            if not self._g("low_volume_pullback",
                           b.volume[imp_i:t + 1].mean() < p["vol_ratio"] * v_imp):
                return None
            if not self._g("close_back_above_ema8",
                           c < e8[t] and pull_hi >= e8[t] and f <= 0.5):
                return None
            if not self._g("leg_budget<=2", self._leg_ok(imp_lo)):
                return None
            stop = min(max(e55[t] + 0.5 * a, pull_hi), c + p["stop_atr"] * a)
            if not self._g("stop_valid", stop - c > 0):
                return None
            self._leg_count += 1
            return self._emit(Setup(
                side=-1, entry_kind="close", stop=stop,
                targets=[(imp_lo, 0.4), (pull_hi - 1.618 * leg, 0.3),
                         (c - 10 * (stop - c), 0.3)],
                trail_atr_mult=p["trail_atr"], trail_after_leg=2, tag="short"))
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
    PARAMS = {
        "atr_pct_max": 0.0030, "bw_pct_min": 0.30, "width_min_atr": 3.0,
        "width_max_atr": 8.0, "vol_mult": 1.2, "rsi_lo": 10.0, "rsi_hi": 90.0,
        "stop_range_frac": 0.35, "stop_max_atr": 1.2, "time_stop": 15.0,
        "intact_tol_atr": 0.25, "max_fades": 2.0,
    }

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
        if used >= self.p["max_fades"]:
            return False
        self._faded[k] = used + 1
        return True

    def signal(self, t, b, ind) -> Optional[Setup]:
        a, ap = ind["atr"][t], ind["atr_pct"][t]
        hi, lo = ind["dc_hi"][t], ind["dc_lo"][t]
        bwp = ind["bw_pct"][t]
        if not self._g("indicators_ready",
                       all(np.isfinite(x) for x in (a, ap, hi, lo, bwp)) and a > 0):
            return None
        p = self.p
        if not self._g("atr%<max", ap < p["atr_pct_max"]):     # ranging tape only
            return None
        if not self._g("bandwidth>min", bwp > p["bw_pct_min"]):  # not a squeeze (S3's)
            return None
        width = hi - lo
        # NB: the playbook's original "0.5-3.0 x ATR" window is arithmetically
        # wrong for a *20-bar* Donchian. For a random walk the expected n-bar
        # range is ~1.6·σ·√n, and ATR(14) ≈ 1.13·σ, so a 20-bar range sits near
        # 6.4x ATR by construction — the old window matched 0.8% of bars. This
        # band keeps the intent (a normal-width range: not a squeeze, not an
        # already-expanded move) at the right scale.
        if not self._g("range_width_in_band",
                       p["width_min_atr"] * a <= width <= p["width_max_atr"] * a):
            return None
        c, w = b.close[t], self.WINDOW
        r2, vs = ind["rsi2"], ind["vsma"]

        def intact(i0: int) -> bool:
            """Spec: the range must have been holding for >= 20 bars before the
            break. The Donchian at i0 already covers the 20 bars before it, so
            the test is whether the *preceding* 20 bars also sat inside the same
            channel — a range that has contained price for 40 bars, not 20.

            (Comparing the channel to itself 20 bars earlier does not work: those
            windows are disjoint, so for a random walk they differ by roughly the
            range itself — that version passed 0.5% of breaks and took no trades.)
            """
            if i0 - 40 < 0:
                return False
            tol = p["intact_tol_atr"] * a
            return (b.high[i0 - 40:i0 - 20].max() <= ind["dc_hi"][i0] + tol
                    and b.low[i0 - 40:i0 - 20].min() >= ind["dc_lo"][i0] - tol)

        # failed downside break -> fade long
        brk = [i for i in range(t - w + 1, t + 1) if b.low[i] < lo]
        if (self._g("broke_out", bool(brk))
                and self._g("closed_back_inside", c > lo)
                and self._g("range_intact_20bars", intact(brk[0]))):
            i0 = brk[0]
            if (self._g("break_vol<mult", b.volume[i0] < p["vol_mult"] * vs[i0])
                    and self._g("rsi2_extreme", min(r2[i] for i in brk) < p["rsi_lo"])):
                ext = float(min(b.low[i] for i in brk))
                stop = max(ext - p["stop_range_frac"] * width, c - p["stop_max_atr"] * a)
                if self._g("stop_valid", c - stop > 0) and self._g(
                        "fade_budget<=2", self._budget(lo, 1)):
                    return self._emit(Setup(
                        side=1, entry_kind="close", stop=stop,
                        targets=[((hi + lo) / 2, 0.5), (hi, 0.5)],
                        time_stop_bars=int(p["time_stop"]), tag="long",
                        meta={"lo": lo, "hi": hi, "side_lvl": lo}))

        # failed upside break -> fade short
        brk = [i for i in range(t - w + 1, t + 1) if b.high[i] > hi]
        if (self._g("broke_out", bool(brk))
                and self._g("closed_back_inside", c < hi)
                and self._g("range_intact_20bars", intact(brk[0]))):
            i0 = brk[0]
            if (self._g("break_vol<mult", b.volume[i0] < p["vol_mult"] * vs[i0])
                    and self._g("rsi2_extreme", max(r2[i] for i in brk) > p["rsi_hi"])):
                ext = float(max(b.high[i] for i in brk))
                stop = min(ext + p["stop_range_frac"] * width, c + p["stop_max_atr"] * a)
                if self._g("stop_valid", stop - c > 0) and self._g(
                        "fade_budget<=2", self._budget(hi, -1)):
                    return self._emit(Setup(
                        side=-1, entry_kind="close", stop=stop,
                        targets=[((hi + lo) / 2, 0.5), (lo, 0.5)],
                        time_stop_bars=int(p["time_stop"]), tag="short",
                        meta={"lo": lo, "hi": hi, "side_lvl": hi}))
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

# S11-S18 are additional candidates (backtest/strategies_extra.py). Imported at
# the bottom to keep this module's own definitions readable; the registry is the
# single place the CLI, portfolio router and optimizer look for a strategy.
from backtest.strategies_extra import ALL_EXTRA          # noqa: E402

ALL = ALL + ALL_EXTRA
REGISTRY = {c.id: c for c in ALL}
