"""Pairs / StatArb Desk tests — no pytest, no network.

    python -m tests.test_pairs

Asserts the market-neutral desk:
  • enters only on a COINTEGRATED pair with |z| ≥ entry threshold, emitting one
    risk-gated LONG (cheap leg) and one risk-gated SHORT (rich leg, negative
    shares) of ~equal notional,
  • stays out inside the band, when not cointegrated, or when another desk
    already owns a leg,
  • exits on reversion and books the combined realized P&L exactly once,
  • stops out on a spread blow-out and on the time stop,
  • closes an orphan leg immediately (never runs unhedged),
  • sim broker supports shorts: negative qty marked to market, equity sane.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-pairs-")

from config import load_config  # noqa: E402
from strategies.pairs_trading import PairsDesk  # noqa: E402


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _coint(z, ok=True):
    return {"hedge_ratio": 1.0, "spread_z": z, "adf": -3.0 if ok else 0.0,
            "cointegrated": 1.0 if ok else 0.0}


def main() -> int:
    cfg = load_config()
    desk = PairsDesk(cfg)
    A, B, PA, PB = "SPY", "QQQ", 500.0, 400.0

    # ── 1) entry: z > +2 → short A (rich), long B (cheap) ──
    intents = desk.decide(A, B, PA, PB, None, None, 40_000, _coint(2.5))
    _check(len(intents) == 2, "entry emits two legs")
    long_leg = next(i for i in intents if i.side == "buy")
    short_leg = next(i for i in intents if i.side == "sell")
    _check(short_leg.symbol == A and long_leg.symbol == B,
           "z>0 → SHORT the rich leg, LONG the cheap leg")
    _check(long_leg.risk_check and short_leg.risk_check, "both legs risk-gated")
    _check(short_leg.set_position["shares"] < 0, "short leg recorded as negative shares")
    _check(long_leg.set_position["shares"] == int(long_leg.qty), "long leg positive shares")
    notional_gap = abs(long_leg.est_notional - short_leg.est_notional)
    _check(notional_gap <= max(PA, PB), f"legs ~equal notional (gap ${notional_gap:,.0f})")
    _check(long_leg.set_position["pair"] == short_leg.set_position["pair"], "legs share the pair tag")

    # z < -2 flips direction
    flipped = desk.decide(A, B, PA, PB, None, None, 40_000, _coint(-2.5))
    _check(next(i for i in flipped if i.side == "buy").symbol == A,
           "z<0 flips: LONG the first leg instead")

    # ── 2) honest stand-downs ──
    _check(len(desk.decide(A, B, PA, PB, None, None, 40_000, _coint(1.0))) == 1
           and desk.decide(A, B, PA, PB, None, None, 40_000, _coint(1.0))[0].kind == "state",
           "inside the band → wait state, no orders")
    _check(desk.decide(A, B, PA, PB, None, None, 40_000, _coint(3.0, ok=False)) == [],
           "not cointegrated → no trade regardless of z")
    other = {"strategy": "ladder", "shares": 10, "cost_basis": 480.0}
    _check(desk.decide(A, B, PA, PB, other, None, 40_000, _coint(2.5)) == [],
           "never fights another desk for a symbol")
    tiny = desk.decide(A, B, PA, PB, None, None, 300, _coint(2.5))
    _check(len(tiny) == 1 and tiny[0].purpose == "pairs_skip", "tiny budget → skip")

    # ── 3) exit on reversion books the combined P&L exactly once ──
    pos_short_a = {"strategy": "pairs", "shares": -40, "cost_basis": 500.0,
                   "pair": "SPY|QQQ", "entry_z": 2.5, "cycles_held": 3}
    pos_long_b = {"strategy": "pairs", "shares": 50, "cost_basis": 400.0,
                  "pair": "SPY|QQQ", "entry_z": 2.5, "cycles_held": 3}
    # spread reverted: A fell to 490 (short +$400), B rose to 408 (long +$400)
    out = desk.decide(A, B, 490.0, 408.0, dict(pos_short_a), dict(pos_long_b), 0, _coint(0.2))
    _check(len(out) == 2 and all(i.purpose == "pairs_close" for i in out),
           "reversion closes both legs")
    _check(out[0].side == "buy" and out[0].qty == 40, "short leg bought back in full")
    _check(abs(sum(i.realized_delta for i in out) - 800.0) < 1e-6,
           f"combined P&L booked once (+$800, got {sum(i.realized_delta for i in out)})")
    _check(all(i.clear_position for i in out), "both legs cleared")

    # hold path: inside stop, above exit → merge cycles_held
    hold = desk.decide(A, B, 498.0, 401.0, dict(pos_short_a), dict(pos_long_b), 0, _coint(1.5))
    _check(hold[0].purpose == "pairs_hold" and hold[0].merge_position["cycles_held"] == 4,
           "open spread holds and ages inside the band")

    # ── 4) stops ──
    blow = desk.decide(A, B, 520.0, 395.0, dict(pos_short_a), dict(pos_long_b), 0, _coint(4.5))
    _check(all(i.purpose == "pairs_close" for i in blow), "z blow-out → stop, close both legs")
    aged_a = dict(pos_short_a, cycles_held=cfg.pairs_max_hold)
    aged = desk.decide(A, B, 498.0, 401.0, aged_a, dict(pos_long_b), 0, _coint(1.5))
    _check(all(i.purpose == "pairs_close" for i in aged), "time stop after PAIRS_MAX_HOLD cycles")

    # ── 5) orphan leg never runs unhedged ──
    orphan = desk.decide(A, B, 500.0, 400.0, dict(pos_short_a), None, 40_000, _coint(2.5))
    _check(len(orphan) == 1 and orphan[0].purpose == "pairs_close" and orphan[0].side == "buy",
           "orphan short leg closed immediately")

    # ── 6) sim broker shorts: negative qty, sane mark-to-market equity ──
    from utils.sim_broker import SimBroker
    sim = SimBroker(load_config())
    eq0 = sim.get_account()["equity"]
    r = sim.submit_equity_order("SPY", 10, "sell")           # open short from flat
    _check(r["status"] == "filled", "sim fills a short sale")
    _check(sim.get_broker_positions()["SPY"]["qty"] == -10, "sim books negative qty")
    eq1 = sim.get_account()["equity"]
    _check(abs(eq1 - eq0) < eq0 * 0.001,
           f"equity unchanged at short open (mark-to-market, was {eq0:,.0f} now {eq1:,.0f})")
    sim.submit_equity_order("SPY", 10, "buy")                # close it
    _check("SPY" not in sim.get_broker_positions(), "buy-back flattens the short")

    print("\nPAIRS DESK CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
