"""Unit checks for the intraday Day-Trading / Forex desk (pure decision engine)."""
from __future__ import annotations

import numpy as np

from config import load_config
from intelligence.agents import MarketSnapshot
from strategies.day_trading import DayTrading


def _snap(symbol, price, closes):
    closes = np.asarray(closes, dtype=float)
    vols = np.full(closes.size, 1e6)
    return MarketSnapshot(symbol, float(price), closes, vols, closes)


def _check(name, cond):
    print(("  ok " if cond else "  XX ") + name)
    assert cond, name


def run() -> int:
    cfg = load_config()
    dt = DayTrading(cfg)

    # 1) oversold mean-reversion bounce → intraday long entry on a FX pair
    closes = np.concatenate([np.linspace(110, 95, 56), np.full(4, 95.0)])
    snap = _snap("EUR/USD", 95.0, closes)
    intents = dt.decide("EUR/USD", snap, None, budget=10_000.0, today="2026-06-22")
    buys = [i for i in intents if i.purpose == "daytrade_entry" and i.side == "buy"]
    _check("oversold bounce opens an intraday long", len(buys) == 1)
    _check("entry is risk-checked + fractional FX qty", buys and buys[0].risk_check and buys[0].qty > 0)
    _check("entry sets daytrade position w/ stop + entry_day",
           buys and buys[0].set_position and buys[0].set_position["entry_day"] == "2026-06-22"
           and buys[0].set_position["stop"] < 95.0)

    flat = np.full(60, 100.0)
    base_pos = {"strategy": "daytrade", "shares": 100.0, "entry_price": 100.0,
                "cost_basis": 100.0, "peak_price": 100.0, "stop": 99.0, "entry_day": "2026-06-22"}

    # 2) profit target exit
    out = dt.decide("EUR/USD", _snap("EUR/USD", 102.0, flat), dict(base_pos), 0.0, "2026-06-22")
    _check("hits profit target → sell/clear", out and out[0].purpose == "daytrade_target"
           and out[0].side == "sell" and out[0].clear_position)

    # 3) protective stop exit
    out = dt.decide("EUR/USD", _snap("EUR/USD", 98.0, flat), dict(base_pos), 0.0, "2026-06-22")
    _check("breaches stop → sell/clear", out and out[0].purpose == "daytrade_stop" and out[0].clear_position)

    # 4) never holds overnight — flatten on a new calendar day
    out = dt.decide("EUR/USD", _snap("EUR/USD", 100.2, flat), dict(base_pos), 0.0, "2026-06-23")
    _check("new day → end-of-day flatten", out and out[0].purpose == "daytrade_eod" and out[0].clear_position)

    # 5) otherwise holds (state update, no order)
    out = dt.decide("EUR/USD", _snap("EUR/USD", 100.4, flat), dict(base_pos), 0.0, "2026-06-22")
    _check("in-band → holds (state only, no order)",
           out and out[0].kind == "state" and out[0].purpose == "daytrade_hold")

    # 6) realized P&L is booked on exit
    out = dt.decide("EUR/USD", _snap("EUR/USD", 102.0, flat), dict(base_pos), 0.0, "2026-06-22")
    _check("exit books realized P&L (+$200 on 100 units)", abs(out[0].realized_delta - 200.0) < 1e-6)

    print("ALL DAY-TRADING CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
