"""Research→live promotion bridge: run validated backtest strategies as live desks.

Backtest strategies (`backtest/strategies.py`, ids s1..s18) speak bars::

    signal(t, bars, ind) -> Setup | None        # enter
    manage(t, bars, ind, pos) -> str | None    # exit reason

Live desks speak ``OrderIntent``. ``BacktestStrategyAdapter`` translates and
implements the ``LiveStrategy`` protocol, so a promoted strategy slots into the
workforce like any other desk.

**Data.** The adapter runs on the desk's own RECORDED bars
(``utils/bar_recorder.py``) — the finest interval with at least ``warmup``
measured-range bars (``volume >= MIN_TICKS_MEASURED_RANGE``; a bar built from
one poll-cadence quote has no measured range and is excluded). Fewer bars than
the strategy's warmup → the adapter stands down silently. It never trades on
insufficient history.

**Honesty notes (read before enabling anything here).**
- The S-strategies were researched on 5-minute BTC-perp bars. Running one on
  15m/60m recorded bars redefines its indicators; only promote a strategy
  whose evidence was produced on the timeframe it will trade live.
- On recorded bars, ``volume`` is a TICK COUNT, not traded size. Volume-gated
  strategies (s1, s2, s15) read sampling frequency as participation here.
- Research code never imports live modules (promotion Gate 0). The import
  direction here is live-side importing research *definitions* — compliant.

**Gating.** Double-gated, default OFF: ``PROMOTED_DESKS_ENABLED`` (global) AND
membership in ``PROMOTED_STRATEGIES`` (comma-separated ids) must both hold.
A promoted desk is still subject to every live rail: RiskEngine approval,
portfolio-governor veto, the regime gate, halts, and the catastrophic sweep.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from backtest.data import Bars
from backtest.engine import Position as BTPosition
from backtest.engine import Setup, Strategy
from backtest.strategies import (
    S1_VWAPBandFade,
    S2_OpeningRange,
    S3_SqueezeBreakout,
    S5_SweepReclaim,
    S6_RibbonPullback,
    S9_FailedBreakFade,
)
from backtest.strategies_extra import (
    S11_DonchianBreakout,
    S12_ConnorsRSI2,
    S13_PercentBReversion,
    S14_NR7Expansion,
    S15_VolumeSpikeContinuation,
    S16_EngulfingAtExtreme,
    S17_SessionMomentum,
    S18_DualTimeframePullback,
)
from strategies.base import LiveStrategy, OrderIntent, StrategyContext, size_qty
from utils.bar_recorder import MIN_TICKS_MEASURED_RANGE
from utils.logger import get_logger

log = get_logger("promoted")

# Registry of promotable research strategies. Absent ids (s4/s7/s8/s10) need
# feeds the desk does not have and are deliberately not promotable.
STRATEGY_CLASSES: Dict[str, type] = {
    "s1": S1_VWAPBandFade,
    "s2": S2_OpeningRange,
    "s3": S3_SqueezeBreakout,
    "s5": S5_SweepReclaim,
    "s6": S6_RibbonPullback,
    "s9": S9_FailedBreakFade,
    "s11": S11_DonchianBreakout,
    "s12": S12_ConnorsRSI2,
    "s13": S13_PercentBReversion,
    "s14": S14_NR7Expansion,
    "s15": S15_VolumeSpikeContinuation,
    "s16": S16_EngulfingAtExtreme,
    "s17": S17_SessionMomentum,
    "s18": S18_DualTimeframePullback,
}

# Strategies whose gates read `volume` — a tick count on recorded bars.
VOLUME_SENSITIVE = frozenset({"s1", "s2", "s15"})

_DESK_FAMILY = "promoted"


def _load_bars(db, symbol: str, warmup: int):
    """Finest recorded interval with >= warmup measured-range bars, as Bars.

    Returns (Bars, interval_minutes) or (None, 0). Never raises."""
    try:
        rows = db.conn.execute(
            """SELECT interval_m, COUNT(*) AS n FROM bars
                WHERE symbol = ? AND volume >= ?
             GROUP BY interval_m ORDER BY interval_m ASC""",
            (symbol, float(MIN_TICKS_MEASURED_RANGE)),
        ).fetchall()
    except Exception as exc:
        log.debug("promoted bar lookup failed for %s: %s", symbol, exc)
        return None, 0
    for row in rows:
        iv = int(row["interval_m"] if hasattr(row, "keys") else row[0])
        n = int(row["n"] if hasattr(row, "keys") else row[1])
        if n < warmup:
            continue
        try:
            data = db.conn.execute(
                """SELECT ts, open, high, low, close, volume FROM bars
                    WHERE symbol = ? AND interval_m = ? AND volume >= ?
                 ORDER BY ts""",
                (symbol, iv, float(MIN_TICKS_MEASURED_RANGE)),
            ).fetchall()
        except Exception as exc:
            log.debug("promoted bar read failed for %s: %s", symbol, exc)
            return None, 0
        if len(data) < warmup:
            continue
        arr = lambda k: np.array(
            [float(r[k] if hasattr(r, "keys") else r[{"ts": 0, "open": 1, "high": 2,
                                                     "low": 3, "close": 4, "volume": 5}[k]])
             for r in data], dtype=float)
        bars = Bars(ts=(arr("ts") * 1000).astype(np.int64), open=arr("open"),
                    high=arr("high"), low=arr("low"), close=arr("close"),
                    volume=arr("volume"), symbol=symbol, tf_minutes=iv)
        return bars, iv
    return None, 0


class BacktestStrategyAdapter:
    """A backtest Strategy running as a live desk (LiveStrategy protocol)."""

    desk_family = _DESK_FAMILY

    def __init__(self, strategy_id: str, db, strategy: Optional[Strategy] = None):
        sid = str(strategy_id or "").strip().lower()
        if sid not in STRATEGY_CLASSES:
            raise ValueError(f"unknown promotable strategy {strategy_id!r} "
                             f"(known: {sorted(STRATEGY_CLASSES)})")
        self.sid = sid
        self.strategy_id = f"promoted:{sid}"
        self.strategy = strategy or STRATEGY_CLASSES[sid]()
        self.db = db
        if sid in VOLUME_SENSITIVE:
            log.warning("promoted %s is volume-gated; on recorded bars volume is "
                        "a TICK COUNT, not traded size — promote only with evidence "
                        "produced on equivalent data", self.strategy_id)

    # ── position bookkeeping (state["positions"][symbol], marked) ──
    def _book(self, state: dict) -> dict:
        # Ordinary positions store, same as every other desk. Promoted legs
        # are marked strategy="promoted:<sid>" so desk routing, the
        # catastrophic-stop sweep, and P&L reporting treat them like any
        # other position instead of a parallel universe.
        return state.setdefault("positions", {})

    def _open_position(self, state: dict, symbol: str):
        pos = self._book(state).get(symbol)
        if isinstance(pos, dict) and pos.get("strategy") == self.strategy_id:
            return pos
        return None

    # ── LiveStrategy protocol ──
    def decide(self, ctx: StrategyContext) -> List[OrderIntent]:
        sym = ctx.symbol
        state = ctx.state or {}
        try:
            price = float(ctx.get_price(sym) or 0.0)
        except Exception:
            price = 0.0
        if not math.isfinite(price) or price <= 0:
            return []

        bars, iv = _load_bars(self.db, sym, self.strategy.warmup)
        if bars is None:
            return []                      # insufficient measured history: stand down
        t = len(bars) - 1
        try:
            ind = self.strategy.prepare(bars)
        except Exception as exc:
            log.warning("promoted %s prepare() failed on %s: %s", self.strategy_id, sym, exc)
            return []

        open_pos = self._open_position(state, sym)
        if open_pos is not None:
            return self._manage(sym, open_pos, bars, ind, t, price, state)

        if ctx.budget <= 0:
            return []                      # no budget → no new entries (exits n/a)
        try:
            setup = self.strategy.signal(t, bars, ind)
        except Exception as exc:
            log.warning("promoted %s signal() failed on %s: %s", self.strategy_id, sym, exc)
            return []
        if setup is None:
            return []
        return self._enter(sym, setup, bars, iv, price, ctx, state)

    # ── entries / exits ──
    def _enter(self, sym: str, setup: Setup, bars: Bars, iv: int, price: float,
               ctx: StrategyContext, state: dict) -> List[OrderIntent]:
        side = "buy" if setup.side > 0 else "sell"
        qty = size_qty(sym, ctx.budget, price, 0,
                       getattr(ctx, "extras", {}).get("allow_fractional", True))
        if qty <= 0:
            return []
        stop = float(setup.stop or 0.0)
        if setup.side > 0 and stop <= 0:
            # No stop on a long is not a trade, it is a hope. The backtest
            # engine would size this off risk_unit; live we refuse instead.
            log.warning("promoted %s %s signal without a stop — standing down",
                        self.strategy_id, sym)
            return []
        notional = qty * price
        return [OrderIntent(
            symbol=sym, strategy=self.strategy_id, kind="equity",
            purpose=f"promoted_{self.sid}_entry",
            reason=(f"{self.strategy_id} signal {setup.tag or 'setup'} @ {iv}m "
                    f"(tf {bars.tf_minutes}m, validated on 5m — see promotion evidence)"),
            side=side, qty=qty, est_notional=notional,
            risk_check=True,               # full RiskEngine + governor gating
            set_position={
                "strategy": self.strategy_id,
                "stage": "promoted_open",
                "shares": qty if setup.side > 0 else -qty,
                "cost_basis": price,
                "stop": stop,
                "targets": [[float(p), float(f)] for p, f in (setup.targets or [])],
                "entry_cycle": (ctx.state or {}).get("cycle", 0),
                "tf_minutes": iv,
                "tag": setup.tag or "",
            },
        )]

    def _manage(self, sym: str, pos: dict, bars: Bars, ind: dict, t: int,
                price: float, state: dict) -> List[OrderIntent]:
        shares = float(pos.get("shares", 0) or 0)
        if not shares:
            self._book(state).pop(sym, None)
            return []
        entry_px = float(pos.get("cost_basis", 0) or 0)
        stop = float(pos.get("stop", 0) or 0)
        bt_pos = BTPosition(
            side=1 if shares > 0 else -1, entry_px=entry_px, qty=abs(shares),
            qty_open=abs(shares), stop=stop,
            targets=[(float(p), float(f)) for p, f in (pos.get("targets") or [])],
            legs_done=0, entry_bar=int(pos.get("entry_bar", 0) or 0),
            risk_unit=abs(entry_px - stop) * abs(shares) if stop > 0 else 0.0,
            stop0=stop,
            setup=Setup(side=1 if shares > 0 else -1, stop=stop,
                        tag="promoted-live"),
        )
        reason = None
        try:
            reason = self.strategy.manage(t, bars, ind, bt_pos)
        except Exception as exc:
            log.warning("promoted %s manage() failed on %s: %s", self.strategy_id, sym, exc)
        if reason is None and stop > 0:
            # Strategy-level stop backstop, enforced live even if manage()
            # stays silent: longs stop on price <= stop, shorts on price >= stop.
            if (shares > 0 and price <= stop) or (shares < 0 and price >= stop):
                reason = "promoted_stop"
        if reason is None:
            return []
        side = "sell" if shares > 0 else "buy"
        pnl = (price - entry_px) * shares   # signed: +profit for longs AND shorts
        return [OrderIntent(
            symbol=sym, strategy=self.strategy_id, kind="equity",
            purpose=f"promoted_{self.sid}_exit",
            reason=f"{self.strategy_id} exit: {reason}",
            side=side, qty=abs(shares), est_notional=0.0,
            risk_check=False,              # exits flow during halts
            clear_position=True,
            realized_delta=pnl,
        )]


def enabled_strategy_ids(cfg) -> List[str]:
    """Promotable ids enabled by the double gate. Empty unless BOTH the global
    flag and per-strategy membership hold. Unknown ids are rejected loudly."""
    if not bool(getattr(cfg, "promoted_desks_enabled", False)):
        return []
    raw = getattr(cfg, "promoted_strategy_ids", []) or []
    out = []
    for sid in raw:
        s = str(sid or "").strip().lower()
        if s in STRATEGY_CLASSES:
            out.append(s)
        elif s:
            log.error("PROMOTED_STRATEGIES: unknown strategy id %r ignored", sid)
    return out
