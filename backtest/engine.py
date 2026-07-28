"""Bar-by-bar backtest engine for the 5m BTC playbook.

Design rules, chosen so the numbers err against the strategy rather than for it:

  • Causality — a strategy sees bars 0..t when deciding at t. Indicators are
    precomputed but every one of them is causal (see indicators.py).
  • Pessimistic intrabar fills — if a bar's range covers both the stop and a
    take-profit, the **stop** is assumed to have printed first. Always.
  • Fees both sides — taker on entries/stops/time-stops, maker on limit targets.
  • Slippage scales with volatility, and doubles on stop exits (stops are market
    orders and they fire exactly when the book is thinnest).
  • Sizing is fixed-fractional off the stop distance; leverage is an *output*.
    A setup whose ATR-derived notional breaches the cap is skipped, not shrunk.
  • One position at a time per strategy. No pyramiding, no averaging down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from backtest.data import Bars


# ── configuration ─────────────────────────────────────────────────────────────
@dataclass
class CostModel:
    taker_bps: float = 4.5          # per side
    maker_bps: float = 1.5          # per side
    base_slip_bps: float = 0.8      # at ~0.15% ATR
    stop_slip_mult: float = 2.0     # stops fire into a thin book
    event_slip_mult: float = 4.0    # bars whose range > 3x ATR
    funding_bps_per_8h: float = 0.0  # perp carry; 5m trades rarely cross settlement

    def slip_bps(self, atr_pct: float, bar_range_atr: float) -> float:
        s = self.base_slip_bps * (1.0 + max(atr_pct, 0.0) / 0.0015)
        if bar_range_atr > 3.0:
            s *= self.event_slip_mult
        return min(s, 30.0)


@dataclass
class RiskConfig:
    equity0: float = 100_000.0
    risk_pct: float = 0.0035        # 0.35% of equity per trade
    leverage_cap: float = 5.0
    leverage_cap_hivol: float = 3.0
    hivol_atr_pct: float = 0.0045
    daily_loss_stop_pct: float = 0.02
    max_consecutive_losses: int = 4  # -> half size for the rest of the UTC day
    # Playbook §0: never take a setup whose first target cannot clear the
    # round-trip cost several times over. Without this, tight-stop setups are
    # arithmetically unwinnable — the fee alone is most of the risk unit.
    min_edge_mult: float = 3.0


# ── trade plan produced by a strategy ─────────────────────────────────────────
@dataclass
class Setup:
    side: int                                   # +1 long, -1 short
    entry_kind: str = "close"                   # close | next_open | limit | stop
    entry_price: float = 0.0                    # for limit/stop orders
    valid_bars: int = 2                         # pending-order lifetime
    stop: float = 0.0                           # absolute price
    targets: List[Tuple[float, float]] = field(default_factory=list)  # (price, fraction)
    trail_atr_mult: float = 0.0                 # 0 = no trail
    trail_after_leg: int = 0                    # only trail once N legs have filled
    time_stop_bars: int = 0                     # 0 = none
    breakeven_after_leg: int = 1                # move stop to entry after leg N fills
    tag: str = ""
    meta: Dict = field(default_factory=dict)


@dataclass
class Position:
    side: int
    entry_px: float
    qty: float
    qty_open: float
    stop: float
    targets: List[Tuple[float, float]]
    legs_done: int
    entry_bar: int
    risk_unit: float          # $ risked at entry — the denominator of R
    stop0: float
    setup: Setup
    pnl: float = 0.0
    fees: float = 0.0
    mae: float = 0.0          # worst adverse excursion, in R
    mfe: float = 0.0
    peak: float = 0.0         # for the chandelier trail


@dataclass
class Trade:
    strategy: str
    side: int
    entry_ts: int
    exit_ts: int
    entry_px: float
    exit_px: float
    qty: float
    pnl: float
    fees: float
    r: float
    bars_held: int
    mae_r: float
    mfe_r: float
    reason: str
    atr_pct: float
    tag: str = ""


class Strategy:
    """Interface implemented in strategies.py."""
    id = "base"
    name = "base"
    warmup = 300
    funnel = None            # set by Backtester(..., funnel=True)

    def _g(self, name: str, cond) -> bool:
        """Route a signal condition through the funnel recorder when attached."""
        if self.funnel is None:
            return bool(cond)
        return self.funnel.gate(name, cond)

    def _emit(self, setup):
        if self.funnel is not None and setup is not None:
            self.funnel.emitted()
        return setup

    def prepare(self, bars: Bars) -> Dict[str, np.ndarray]:
        return {}

    def signal(self, t: int, bars: Bars, ind: Dict[str, np.ndarray]) -> Optional[Setup]:
        return None

    def manage(self, t: int, bars: Bars, ind: Dict[str, np.ndarray],
               pos: Position) -> Optional[str]:
        """Return a reason string to force a close-of-bar exit, else None."""
        return None


# ── engine ────────────────────────────────────────────────────────────────────
class Backtester:
    def __init__(self, bars: Bars, costs: Optional[CostModel] = None,
                 risk: Optional[RiskConfig] = None, entry_mode: str = "spec",
                 funnel: bool = False):
        self.bars = bars
        self.costs = costs or CostModel()
        self.risk = risk or RiskConfig()
        self.funnel = funnel
        # "spec" honours each strategy's stated entry; "next_open" forces every
        # market entry to the next bar's open (a friction-sensitivity run).
        self.entry_mode = entry_mode

    # -- helpers ---------------------------------------------------------------
    def _fee(self, notional: float, maker: bool) -> float:
        bps = self.costs.maker_bps if maker else self.costs.taker_bps
        return abs(notional) * bps / 10_000.0

    def _fill_px(self, px: float, side: int, atr_pct: float, bar_range_atr: float,
                 is_stop: bool) -> float:
        """Slippage always moves the fill against us."""
        s = self.costs.slip_bps(atr_pct, bar_range_atr)
        if is_stop:
            s *= self.costs.stop_slip_mult
        return px * (1.0 + side * s / 10_000.0)

    # -- main loop -------------------------------------------------------------
    def run(self, strat: Strategy) -> Dict:
        """Backtest one strategy on its own equity — the N=1 case of run_many."""
        return self.run_many([strat])

    def run_many(self, strats: List[Strategy], arm=None) -> Dict:
        """Backtest one or more strategies sharing a single equity curve.

        With several strategies this is the book as §0 actually specifies it:
        one directional position at a time, one portfolio-level daily loss stop,
        one consecutive-loss size reduction. `arm(t, atr_pct)` returns the
        strategy indices eligible at bar t, highest priority first — that is the
        regime-routing table. Default: every strategy, in the order given.
        """
        b = self.bars
        n = len(b)
        inds, atrs = [], []
        for st in strats:
            ind = st.prepare(b)
            if self.funnel:
                from backtest.funnel import Funnel
                st.funnel = Funnel(st.id)
            if ind.get("atr") is None:
                raise ValueError(f"{st.id}: prepare() must expose 'atr'")
            inds.append(ind)
            atrs.append(ind["atr"])
        if arm is None:
            order = list(range(len(strats)))
            def arm(t, atr_pct):        # noqa: E306 - trivial default
                return order

        equity = self.risk.equity0
        eq_curve = np.full(n, np.nan)
        trades: List[Trade] = []
        pos: Optional[Position] = None
        active = 0                                       # strategy owning pos/pending
        atr = atrs[0]
        pending: Optional[Tuple[int, Setup, int]] = None  # (strategy, setup, expiry)
        day = b.day_id
        day_start_equity = equity
        cur_day = day[0]
        day_halted = False
        consec_losses = 0
        size_mult = 1.0
        skipped_leverage = 0
        skipped_halt = 0
        skipped_edge = 0

        def close_position(t: int, px: float, qty: float, reason: str,
                           maker: bool, is_stop: bool) -> None:
            nonlocal equity, pos, consec_losses, size_mult
            assert pos is not None
            a_pct = float(atr[t] / b.close[t]) if b.close[t] else 0.0
            rng = float((b.high[t] - b.low[t]) / atr[t]) if atr[t] else 0.0
            fill = self._fill_px(px, -pos.side, a_pct, rng, is_stop)
            gross = pos.side * (fill - pos.entry_px) * qty
            fee = self._fee(fill * qty, maker)
            pos.pnl += gross - fee
            pos.fees += fee
            pos.qty_open -= qty
            equity += gross - fee
            if pos.qty_open <= 1e-12:
                hold_h = (b.ts[t] - b.ts[pos.entry_bar]) / 3_600_000.0
                if self.costs.funding_bps_per_8h:
                    carry = (abs(pos.entry_px * pos.qty) *
                             self.costs.funding_bps_per_8h / 10_000.0 * hold_h / 8.0)
                    pos.pnl -= carry
                    equity -= carry
                r = pos.pnl / pos.risk_unit if pos.risk_unit else 0.0
                trades.append(Trade(
                    strategy=strats[active].id, side=pos.side,
                    entry_ts=int(b.ts[pos.entry_bar]),
                    exit_ts=int(b.ts[t]), entry_px=pos.entry_px, exit_px=fill,
                    qty=pos.qty, pnl=pos.pnl, fees=pos.fees, r=r,
                    bars_held=t - pos.entry_bar, mae_r=pos.mae, mfe_r=pos.mfe,
                    reason=reason, atr_pct=a_pct, tag=pos.setup.tag))
                consec_losses = consec_losses + 1 if pos.pnl < 0 else 0
                if consec_losses >= self.risk.max_consecutive_losses:
                    size_mult = 0.5
                pos = None

        def open_position(t: int, s: Setup, raw_px: float, maker: bool) -> None:
            nonlocal pos, equity, skipped_leverage, skipped_edge
            stop_dist = abs(raw_px - s.stop)
            if stop_dist <= 0:
                return
            a_pct = float(atr[t] / b.close[t]) if b.close[t] else 0.0
            # -- edge gate: TP1 must clear the round-trip cost by min_edge_mult
            if s.targets:
                cost_bps = 2 * (self.costs.taker_bps
                                + self.costs.slip_bps(a_pct, 1.0))
                tp1_bps = abs(s.targets[0][0] - raw_px) / raw_px * 10_000.0
                if tp1_bps < self.risk.min_edge_mult * cost_bps:
                    skipped_edge += 1
                    return
            rng = float((b.high[t] - b.low[t]) / atr[t]) if atr[t] else 0.0
            fill = self._fill_px(raw_px, s.side, a_pct, rng, is_stop=False)
            stop_dist = abs(fill - s.stop)
            if stop_dist <= 0:
                return
            risk_dollars = equity * self.risk.risk_pct * size_mult
            qty = risk_dollars / stop_dist
            cap = (self.risk.leverage_cap_hivol if a_pct >= self.risk.hivol_atr_pct
                   else self.risk.leverage_cap)
            if qty * fill > cap * equity:
                skipped_leverage += 1
                return                       # skip, never resize up into the cap
            fee = self._fee(fill * qty, maker)
            equity -= fee
            pos = Position(side=s.side, entry_px=fill, qty=qty, qty_open=qty,
                           stop=s.stop, targets=list(s.targets), legs_done=0,
                           entry_bar=t, risk_unit=risk_dollars, stop0=s.stop,
                           setup=s, pnl=-fee, fees=fee, peak=fill)

        for t in range(n):
            # ---- daily bookkeeping -------------------------------------------
            if day[t] != cur_day:
                cur_day, day_start_equity, day_halted = day[t], equity, False
                consec_losses, size_mult = 0, 1.0

            # ---- manage an open position -------------------------------------
            if pos is not None:
                hi, lo, cl = b.high[t], b.low[t], b.close[t]
                unit = pos.risk_unit / pos.qty if pos.qty else 1.0
                if pos.side > 0:
                    pos.mfe = max(pos.mfe, (hi - pos.entry_px) / unit)
                    pos.mae = min(pos.mae, (lo - pos.entry_px) / unit)
                    pos.peak = max(pos.peak, hi)
                else:
                    pos.mfe = max(pos.mfe, (pos.entry_px - lo) / unit)
                    pos.mae = min(pos.mae, (pos.entry_px - hi) / unit)
                    pos.peak = min(pos.peak, lo)

                stopped = (lo <= pos.stop) if pos.side > 0 else (hi >= pos.stop)
                if stopped:
                    close_position(t, pos.stop, pos.qty_open, "stop", maker=False,
                                   is_stop=True)
                else:
                    # take-profit legs, nearest first
                    while pos is not None and pos.legs_done < len(pos.targets):
                        px, frac = pos.targets[pos.legs_done]
                        hit = (hi >= px) if pos.side > 0 else (lo <= px)
                        if not hit:
                            break
                        qty_leg = min(pos.qty * frac, pos.qty_open)
                        pos.legs_done += 1
                        last_leg = pos.legs_done >= len(pos.targets)
                        close_position(t, px, pos.qty_open if last_leg else qty_leg,
                                       f"tp{pos.legs_done}", maker=True, is_stop=False)
                        if pos is not None and pos.legs_done >= pos.setup.breakeven_after_leg:
                            pos.stop = (max(pos.stop, pos.entry_px) if pos.side > 0
                                        else min(pos.stop, pos.entry_px))

                if pos is not None:
                    reason = strats[active].manage(t, b, inds[active], pos)
                    if reason:
                        close_position(t, cl, pos.qty_open, reason, maker=False,
                                       is_stop=False)
                if pos is not None and pos.setup.time_stop_bars:
                    if t - pos.entry_bar >= pos.setup.time_stop_bars:
                        close_position(t, cl, pos.qty_open, "time", maker=False,
                                       is_stop=False)
                if (pos is not None and pos.setup.trail_atr_mult and atr[t] > 0
                        and pos.legs_done >= pos.setup.trail_after_leg):
                    m = pos.setup.trail_atr_mult
                    if pos.side > 0:
                        pos.stop = max(pos.stop, pos.peak - m * atr[t])
                    else:
                        pos.stop = min(pos.stop, pos.peak + m * atr[t])

            # ---- daily circuit breaker ---------------------------------------
            if not day_halted and equity < day_start_equity * (1 - self.risk.daily_loss_stop_pct):
                day_halted = True
                if pos is not None:
                    close_position(t, b.close[t], pos.qty_open, "daily_stop",
                                   maker=False, is_stop=False)

            eq_curve[t] = equity

            # ---- pending order -----------------------------------------------
            if pos is None and pending is not None:
                idx, s, expiry = pending
                if t > expiry:
                    pending = None
                else:
                    filled = None
                    if s.entry_kind == "limit":
                        if (b.low[t] <= s.entry_price) if s.side > 0 else (b.high[t] >= s.entry_price):
                            filled = (s.entry_price, True)
                    elif s.entry_kind == "stop":
                        if (b.high[t] >= s.entry_price) if s.side > 0 else (b.low[t] <= s.entry_price):
                            filled = (s.entry_price, False)
                    elif s.entry_kind == "next_open":
                        filled = (b.open[t], False)
                    if filled:
                        pending = None
                        if not day_halted:
                            active, atr = idx, atrs[idx]
                            open_position(t, s, filled[0], maker=filled[1])
                            # a fill and a stop-out can share a bar; resolve
                            # pessimistically on the same bar
                            if pos is not None:
                                st = (b.low[t] <= pos.stop) if pos.side > 0 else (b.high[t] >= pos.stop)
                                if st:
                                    close_position(t, pos.stop, pos.qty_open,
                                                   "stop_same_bar", maker=False,
                                                   is_stop=True)

            # ---- new signal ---------------------------------------------------
            if pos is None and pending is None and t < n - 1:
                if day_halted:
                    skipped_halt += 1
                else:
                    a_pct = (float(atrs[0][t] / b.close[t])
                             if b.close[t] and np.isfinite(atrs[0][t]) else 0.0)
                    for idx in arm(t, a_pct):
                        if t < strats[idx].warmup:
                            continue
                        s = strats[idx].signal(t, b, inds[idx])
                        if s is None:
                            continue
                        active, atr = idx, atrs[idx]
                        kind = s.entry_kind
                        if self.entry_mode == "next_open" and kind == "close":
                            kind = "next_open"
                        if kind == "close":
                            open_position(t, s, b.close[t], maker=False)
                            if pos is not None:
                                st = (b.low[t] <= pos.stop) if pos.side > 0 else (b.high[t] >= pos.stop)
                                if st:
                                    close_position(t, pos.stop, pos.qty_open,
                                                   "stop_same_bar", maker=False,
                                                   is_stop=True)
                        else:
                            s.entry_kind = kind
                            pending = (idx, s, t + max(1, s.valid_bars))
                        break

        if pos is not None:
            close_position(n - 1, b.close[n - 1], pos.qty_open, "eod_flat",
                           maker=False, is_stop=False)
            eq_curve[n - 1] = equity

        out = {"trades": trades, "equity": eq_curve, "equity_final": equity,
               "skipped_leverage": skipped_leverage, "skipped_halt": skipped_halt,
               "skipped_edge": skipped_edge}
        if len(strats) == 1:
            out.update({"strategy": strats[0].id, "name": strats[0].name,
                        "funnel": strats[0].funnel})
        else:
            out.update({"strategy": "portfolio",
                        "name": f"Portfolio ({', '.join(s.id for s in strats)})",
                        "funnel": None,
                        "funnels": [s.funnel for s in strats if s.funnel]})
        return out
