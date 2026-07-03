"""Regression tests for the 2026-07-03 accounting / risk audit.

    python -m tests.test_regressions

Each test pins one confirmed bug so it can't silently return. No pytest needed —
plain asserts, exits non-zero on the first failure so CI can gate on it. Runs
fully offline (broker credentials are scrubbed → deterministic offline-sim).
"""
from __future__ import annotations

import os
import sys

import numpy as np

os.environ.setdefault("LOG_LEVEL", "ERROR")

from config import load_config
from strategies.base import OrderIntent
from strategies.wheel_strategy import WheelStrategy
from strategies.trailing_ladder import TrailingLadder
from strategies.copy_trading import CopyTrader
from intelligence.agents import AgentVerdict, Council, MarketSnapshot, BridgewaterRisk

# Hermetic: config.py runs load_dotenv() at import, so scrub broker creds AFTER
# importing it — this guarantees offline-sim regardless of the developer's .env.
for _k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "IBKR_ACCOUNT",
           "CCXT_API_KEY", "CCXT_SECRET", "CCXT_PASSWORD",
           "ROBINHOOD_USERNAME", "ROBINHOOD_PASSWORD"):
    os.environ.pop(_k, None)


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


class _Snap:
    def __init__(self, price, vol=0.3):
        self.price = price
        self.vol = vol


def _apply(intent: OrderIntent, state: dict) -> None:
    """Mirror of ExecutionTrader._apply — the state-reconciliation contract."""
    positions = state.setdefault("positions", {})
    if intent.clear_position:
        positions.pop(intent.symbol, None)
    elif intent.set_position is not None:
        positions[intent.symbol] = intent.set_position
    elif intent.merge_position is not None:
        pos = positions.get(intent.symbol, {})
        pos.update(intent.merge_position)
        positions[intent.symbol] = pos
    state["premium_collected"] = state.get("premium_collected", 0.0) + intent.premium_delta
    state["realized_pnl"] = state.get("realized_pnl", 0.0) + intent.realized_delta


def test_premium_counted_once(cfg):
    """Bug #1: option premium must land in premium_collected exactly once, never
    also re-added to realized_pnl at expiry (which _sleeve would then sum twice)."""
    w = WheelStrategy(cfg)
    state = {"positions": {}, "premium_collected": 0.0, "realized_pnl": 0.0}
    _apply(OrderIntent("X", "wheel", "option", "open_csp", side="sell_to_open", qty=3,
                       premium=1.0, premium_delta=300.0,
                       set_position={"stage": "short_put", "shares": 0, "strike": 90.0,
                                     "contracts": 3, "premium_open": 300.0,
                                     "cycles_remaining": 1}), state)
    pos = state["positions"]["X"]
    for it in w._resolve_put("X", _Snap(95.0), pos):  # put expires worthless
        _apply(it, state)
    total = state["premium_collected"] + state["realized_pnl"]
    _check(abs(total - 300.0) < 1e-6,
           f"CSP premium counted once (got ${total:.0f}, must be $300 not $600)")


def test_called_away_excludes_premium(cfg):
    """Bug #1: called_away realizes only the equity gain — the call premium is
    already in premium_collected from open_cc."""
    w = WheelStrategy(cfg)
    pos = {"stage": "covered_call", "shares": 100, "cost_basis": 100.0, "strike": 110.0,
           "cycles_remaining": 1, "premium_open": 250.0}
    intents = w._resolve_call("X", _Snap(115.0), pos)  # 115 > 110 strike → called away
    realized = sum(i.realized_delta for i in intents)
    _check(abs(realized - 1000.0) < 1e-6,
           f"called_away realizes equity gain only ((110-100)*100=$1000), got ${realized:.0f}")


def test_ladder_no_phantom_shares_when_blocked(cfg):
    """Bug #3: a risk-BLOCKED ladder add must not leave phantom shares in state."""
    tl = TrailingLadder(cfg)
    base = {"strategy": "ladder", "shares": 10, "entry_price": 100.0, "cost_basis": 100.0,
            "peak_price": 100.0, "ratcheted": False, "trailing_floor": None,
            "hard_floor": 100.0 * (1 - cfg.ladder_catastrophic_pct), "rungs_hit": [False, False]}
    intents = tl.decide("X", _Snap(78.0), dict(base), None, budget=5000.0)  # -22% → rung 1
    state = {"positions": {"X": dict(base)}}
    for it in intents:
        if it.kind == "equity" and it.risk_check:
            continue  # simulate risk block: buy skipped, its merge must NOT apply
        _apply(it, state)
    _check(state["positions"]["X"]["shares"] == 10,
           "blocked ladder add leaves shares unchanged (no phantom shares)")
    _check(state["positions"]["X"]["rungs_hit"] == [False, False],
           "blocked ladder add does not consume the rung")


def test_ladder_no_liquidation_on_zero_price(cfg):
    """Bug #4: a 0 / invalid quote must never trigger a catastrophic exit."""
    tl = TrailingLadder(cfg)
    pos = {"strategy": "ladder", "shares": 10, "entry_price": 100.0, "cost_basis": 100.0,
           "peak_price": 100.0, "ratcheted": False, "trailing_floor": None,
           "hard_floor": 80.0, "rungs_hit": [False, False]}
    intents = tl.decide("X", _Snap(0.0), pos, None, budget=5000.0)
    sells = [i for i in intents if i.side == "sell"]
    _check(not sells, "price==0 produces no sell/liquidation intent")


def test_copy_buy_weighted_cost_basis(cfg):
    """Bug #6: mirroring a buy onto an existing position weighted-averages the
    basis rather than overwriting it with the new fill price."""
    c = CopyTrader(cfg)
    state = {"positions": {"AAA": {"strategy": "copy", "shares": 10, "cost_basis": 100.0,
                                   "entry_price": 100.0}}}
    signals = [{"symbol": "AAA", "side": "buy", "weight": 1.0, "source": "test"}]
    intents = c.decide(signals, state, equity=100000.0, get_price=lambda s: 120.0)
    buys = [i for i in intents if i.purpose == "copy_buy" and i.set_position]
    _check(bool(buys), "copy_buy intent produced")
    sp = buys[0].set_position
    added = sp["shares"] - 10
    expected = (100.0 * 10 + 120.0 * added) / sp["shares"]
    _check(abs(sp["cost_basis"] - expected) < 1e-6,
           f"copy_buy weighted basis {sp['cost_basis']:.4f} == expected {expected:.4f} "
           f"(not the raw fill 120.0)")


def test_clamp_neutralizes_nonfinite(cfg):
    """Bug #intel-1: a non-finite score/confidence must clamp to NEUTRAL (0/0),
    not to +1.0 — min(1.0, nan) returns 1.0 in Python, which would fabricate a
    max-conviction LONG out of a bad price tick."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        v = AgentVerdict("t", "t", bad, bad, "").clamp()
        _check(v.score == 0.0 and v.confidence == 0.0,
               f"clamp({bad}) → score 0.0 / confidence 0.0 (not +1.0)")


def test_council_nan_price_stays_neutral(cfg):
    """Bug #intel-1 (integration): a NaN spot price with valid history must not
    drive the council to a high-conviction long."""
    closes = np.array([100.0] * 300)
    snap = MarketSnapshot("X", float("nan"), closes, np.array([1e6] * 300), closes)
    cv = Council().deliberate(snap)
    pinned = [a.name for a in cv.verdicts if a.score >= 0.999 and a.confidence >= 0.999]
    _check(cv.conviction <= 0.55 and not pinned,
           f"NaN price → neutral council (conviction {cv.conviction:.3f}, no pinned agents)")


def test_bridgewater_zero_vol_full_size(cfg):
    """Bug #intel-2: a flat / zero-vol market must map to full (capped) size, not
    the minimum — the vol-targeting limit as vol→0 is 1.0."""
    flat = np.array([50.0] * 120)
    v = BridgewaterRisk().evaluate(MarketSnapshot("X", 50.0, flat, np.array([1e6] * 120))).clamp()
    _check(v.metrics["risk_scale"] == 1.0,
           f"zero-vol risk_scale is 1.0 (full size), got {v.metrics['risk_scale']}")


def main() -> int:
    cfg = load_config()
    _check(cfg.mode == "offline-sim", "hermetic: runs in offline-sim")
    test_premium_counted_once(cfg)
    test_called_away_excludes_premium(cfg)
    test_ladder_no_phantom_shares_when_blocked(cfg)
    test_ladder_no_liquidation_on_zero_price(cfg)
    test_copy_buy_weighted_cost_basis(cfg)
    test_clamp_neutralizes_nonfinite(cfg)
    test_council_nan_price_stays_neutral(cfg)
    test_bridgewater_zero_vol_full_size(cfg)
    print("\nALL REGRESSION TESTS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
