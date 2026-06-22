"""Intraday Day-Trading desk — momentum + mean-reversion, used for the FOREX
majors universe (and any extra DAY_TRADE_SYMBOLS).

Pure decision engine (no I/O): reads a MarketSnapshot, emits OrderIntents. Unlike
the wheel/ladder (multi-day) desks, this one trades intraday and never holds
overnight — a position opened on one calendar day is flattened the next.

Signals (all from the public-domain indicators in intelligence/engines.py):
  • Momentum long  — price above the 20-bar SMA, fast SMA ≥ slow SMA, positive
    MACD histogram, RSI not yet overbought.
  • Mean-reversion long — RSI oversold (<30) and stabilising.
Exits: profit target, protective stop (trailed up with the peak), trend break
(price < 10-bar SMA with negative MACD), or the end-of-day flatten.

Runs on FX pairs (e.g. EUR/USD) which the simulator/IBKR price natively; on a
broker without FX (e.g. Alpaca) those orders simply fail-safe and are logged.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config import Config
from intelligence import engines
from intelligence.agents import MarketSnapshot
from strategies.base import OrderIntent, size_qty


class DayTrading:
    name = "Intraday / Forex Desk"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def decide(self, symbol: str, snap: MarketSnapshot, pos: Optional[Dict],
               budget: float, today: str) -> List[OrderIntent]:
        if snap.price <= 0:
            return []
        if pos and (pos.get("shares", 0) or 0) > 0:
            return self._manage(symbol, snap, pos, today)
        return self._enter(symbol, snap, budget, today)

    # ── signal ────────────────────────────────────────────────────────────────
    def _signal(self, snap: MarketSnapshot):
        closes = snap.closes
        if engines.to_array(closes).size < 30:
            return "flat", 0.0, {}
        r = engines.rsi(closes)
        m = engines.macd_hist(closes)
        sma_f, sma_s = snap.sma(5), snap.sma(20)
        px, mom = snap.price, snap.ret_over(3)
        info = {"rsi": round(r, 1), "macd": round(m, 4), "mom3": round(mom, 4)}
        if px > sma_s and sma_f >= sma_s and m > 0 and r < 72:        # momentum long
            return "long", min(0.9, 0.60 + min(0.30, abs(mom) * 3.0)), info
        if r < 30 and mom > -0.002:                                   # oversold bounce
            return "long", 0.60, info
        return "flat", 0.0, info

    def _enter(self, symbol, snap, budget, today) -> List[OrderIntent]:
        sig, strength, info = self._signal(snap)
        if sig != "long" or strength < self.cfg.day_trade_min_signal or budget <= 0:
            return []
        price = snap.price
        qty = size_qty(symbol, budget, price, self.cfg.day_trade_max_units)
        if qty <= 0:
            return []
        stop = price * (1 - self.cfg.day_trade_stop_pct)
        return [OrderIntent(
            symbol, "daytrade", "equity", "daytrade_entry", side="buy",
            reason=f"intraday long @ {price:.4f} (rsi {info.get('rsi')}, macd {info.get('macd')})",
            qty=qty, est_notional=qty * price, risk_check=True,
            set_position={"strategy": "daytrade", "shares": qty, "entry_price": price,
                          "cost_basis": price, "peak_price": price, "stop": stop,
                          "entry_day": today})]

    def _manage(self, symbol, snap, pos, today) -> List[OrderIntent]:
        price = snap.price
        shares = float(pos.get("shares", 0) or 0)
        entry = float(pos.get("entry_price", price))
        cost = float(pos.get("cost_basis", entry))
        peak = max(float(pos.get("peak_price", price)), price)
        stop = float(pos.get("stop", entry * (1 - self.cfg.day_trade_stop_pct)))
        entry_day = pos.get("entry_day")
        gain = price / entry - 1.0 if entry else 0.0

        def exit_intent(purpose, reason):
            realized = (price - cost) * shares
            return OrderIntent(symbol, "daytrade", "equity", purpose, side="sell",
                               reason=f"{reason}, realize ${realized:,.2f}", qty=shares,
                               est_notional=0.0, risk_check=False,
                               realized_delta=realized, clear_position=True)

        # never hold overnight
        if entry_day and today != entry_day:
            return [exit_intent("daytrade_eod", f"end-of-day flatten @ {price:.4f}")]
        # profit target
        if gain >= self.cfg.day_trade_target_pct:
            return [exit_intent("daytrade_target", f"target {gain:+.2%} @ {price:.4f}")]
        # trailed protective stop (ratchets up with the peak once in profit)
        if gain > self.cfg.day_trade_target_pct / 2:
            stop = max(stop, peak * (1 - self.cfg.day_trade_stop_pct))
        if price <= stop:
            return [exit_intent("daytrade_stop", f"stop {stop:.4f} hit")]
        # trend break
        if price < snap.sma(10) and engines.macd_hist(snap.closes) < 0:
            return [exit_intent("daytrade_trendbreak", f"trend break @ {price:.4f}")]
        # otherwise hold — persist peak/stop
        return [OrderIntent(symbol, "daytrade", "state", "daytrade_hold",
                            reason=f"hold {price:.4f} peak {peak:.4f} gain {gain:+.2%}",
                            merge_position={"peak_price": peak, "stop": stop})]
