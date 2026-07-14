"""Credit Spread Desk tests — no pytest, no network.

    python -m tests.test_credit_spreads

Asserts the defined-risk options desk:
  • opens a bull put spread only when the council is long + conviction ≥ floor
    + IV favorable, emitting BOTH legs (risk-gated short + ungated hedge),
  • risk-gates on the TRUE max loss (width − credit), not the strike collateral,
  • skips honestly when the budget can't fund one contract,
  • counts down and settles all three expiry regimes correctly:
    above short strike (keep credit) / below long strike (max loss) / in between,
  • never opens on crypto-style symbols with no chain.
"""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-spread-")

from config import load_config  # noqa: E402
from strategies.credit_spreads import CreditSpreads, SIM_OPT_CYCLES  # noqa: E402


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _snap(price):
    return SimpleNamespace(symbol="TEST", price=price, vol=0.3)


def _council(direction="long", conviction=0.8, fav=0.7):
    return SimpleNamespace(direction=direction, conviction=conviction,
                           options_favorability=fav)


def _chain(spot):
    """Synthetic put chain like the sim's: strikes 80%–120% of spot, sane mids."""
    out = []
    for mult in (0.80, 0.85, 0.90, 0.95, 1.00, 1.05):
        strike = round(spot * mult, 2)
        # puts get cheaper the further below spot the strike sits
        mid = round(max(0.05, (mult - 0.78) * spot * 0.10), 2)
        out.append({"contract": f"TEST-P{strike}", "strike": strike, "expiry": "+21d",
                    "dte": 21, "type": "put", "mid": mid, "bid": mid - 0.02, "ask": mid + 0.02})
    return out


def main() -> int:
    cfg = load_config()
    desk = CreditSpreads(cfg)
    spot = 100.0

    # ── 1) entry emits both legs with honest risk numbers ──
    intents = desk.decide("TEST", _snap(spot), None, _council(), 50_000, _chain(spot))
    _check(len(intents) == 2, "spread entry emits two legs")
    short, hedge = intents
    _check(short.side == "sell_to_open" and short.risk_check, "short leg is risk-gated")
    _check(hedge.side == "buy_to_open" and not hedge.risk_check, "hedge leg reduces risk (ungated)")
    _check(short.strike > hedge.strike, "hedge strikes below the short put")
    pos = short.set_position
    width = pos["short_strike"] - pos["long_strike"]
    credit_ps = pos["net_credit"] / (100 * pos["contracts"])
    _check(abs(short.est_notional - (width - credit_ps) * 100 * pos["contracts"]) < 1e-6,
           "risk-gated on TRUE max loss (width − credit), not strike collateral")
    _check(short.est_notional < pos["short_strike"] * 100 * pos["contracts"],
           "capital at risk far below CSP collateral (defined risk)")
    _check(pos["cycles_remaining"] == SIM_OPT_CYCLES, "expiry countdown armed")
    _check(abs((short.premium_delta + hedge.premium_delta) - pos["net_credit"]) < 1e-6,
           "net premium booked equals the recorded credit")

    # ── 2) honest skips ──
    _check(desk.decide("TEST", _snap(spot), None, _council(direction="flat"), 50_000, _chain(spot)) == [],
           "no spread when council is not long")
    low_iv = desk.decide("TEST", _snap(spot), None, _council(fav=0.2), 50_000, _chain(spot))
    _check(len(low_iv) == 1 and low_iv[0].kind == "state", "low IV → wait, no order")
    tiny = desk.decide("TEST", _snap(spot), None, _council(), 10, _chain(spot))
    _check(len(tiny) == 1 and tiny[0].purpose == "spread_skip", "tiny budget → skip, no order")
    _check(len(desk.decide("TEST", _snap(spot), None, _council(), 50_000, [])) == 1,
           "empty chain → wait state, never an order")

    # ── 3) countdown then settle: all three regimes ──
    def _pos():
        return dict(strategy="spread", stage="put_spread", contracts=2,
                    short_strike=95.0, long_strike=90.0, net_credit=300.0,
                    cycles_remaining=2)
    hold = desk.decide("TEST", _snap(100), _pos(), _council(), 0, [])
    _check(hold[0].purpose == "spread_hold" and hold[0].merge_position["cycles_remaining"] == 1,
           "open spread counts down to expiry")

    ripe = _pos(); ripe["cycles_remaining"] = 1
    win = desk.decide("TEST", _snap(100), dict(ripe), _council(), 0, [])
    _check(win[0].purpose == "spread_settle" and win[0].realized_delta == 300.0 and win[0].clear_position,
           "spot ≥ short strike → keep full credit")
    lose = desk.decide("TEST", _snap(80), dict(ripe), _council(), 0, [])
    _check(lose[0].realized_delta == 300.0 - 5.0 * 100 * 2,
           f"spot ≤ long strike → exact max loss (got {lose[0].realized_delta})")
    mid = desk.decide("TEST", _snap(93), dict(ripe), _council(), 0, [])
    _check(abs(mid[0].realized_delta - (300.0 - 2.0 * 100 * 2)) < 1e-6,
           f"in-between → linear settlement (got {mid[0].realized_delta})")
    _check(lose[0].realized_delta >= 300.0 - 5.0 * 100 * 2 - 1e-9,
           "loss can never exceed the defined max")

    print("\nCREDIT SPREAD CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
