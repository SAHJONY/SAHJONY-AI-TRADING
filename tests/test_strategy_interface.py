"""Unified LiveStrategy interface tests (upgrade/world-class).

Verifies strategies/base.py's StrategyContext + LiveStrategy protocol:
- TrailingLadder natively implements decide(ctx).
- adapt_legacy_strategy() wraps legacy decide(*args) desks behind the protocol.
- The legacy shim (decide_legacy) still works for unmigrated call sites.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

from config import load_config
from strategies.base import (
    LiveStrategy,
    OrderIntent,
    StrategyContext,
    adapt_legacy_strategy,
)
from strategies.trailing_ladder import TrailingLadder


def _cfg():
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    return load_config()


def test_ladder_conforms_to_live_strategy_protocol():
    ladder = TrailingLadder(_cfg())
    assert isinstance(ladder, LiveStrategy), \
        "TrailingLadder must structurally conform to LiveStrategy"
    assert ladder.strategy_id == "ladder"
    print("✓ TrailingLadder conforms to LiveStrategy")


def test_ladder_decide_via_context():
    cfg = _cfg()
    ladder = TrailingLadder(cfg)
    snap = SimpleNamespace(price=100.0)
    council = SimpleNamespace(conviction=0.9, direction="long")
    ctx = StrategyContext(symbol="AAPL", snap=snap, position=None,
                          council=council, budget=5000.0)
    intents = ladder.decide(ctx)
    buys = [i for i in intents if i.side == "buy" and i.risk_check]
    assert len(buys) == 1, "protocol decide() must emit the entry intent"
    assert isinstance(intents[0], OrderIntent)
    print("✓ decide(ctx) emits entry intent")


def test_legacy_shim_matches_protocol():
    cfg = _cfg()
    ladder = TrailingLadder(cfg)
    snap = SimpleNamespace(price=100.0)
    council = SimpleNamespace(conviction=0.9, direction="long")
    via_ctx = ladder.decide(StrategyContext(
        symbol="AAPL", snap=snap, position=None, council=council, budget=5000.0))
    via_legacy = ladder.decide_legacy("AAPL", snap, None, council, 5000.0)
    assert len(via_ctx) == len(via_legacy) == 1
    assert via_ctx[0].qty == via_legacy[0].qty
    assert via_ctx[0].est_notional == via_legacy[0].est_notional
    print("✓ decide_legacy matches decide(ctx)")


def test_adapt_legacy_strategy_wraps_positional_desk():
    # Simulate a legacy desk with a positional decide(a, b, c).
    def legacy_decide(symbol, budget, flag):
        assert flag == "x"
        return [OrderIntent(symbol=symbol, strategy="demo", kind="state",
                            purpose="noop", reason="t",
                            est_notional=budget)]

    wrapped = adapt_legacy_strategy(
        "demo",
        legacy_decide,
        lambda ctx: (ctx.symbol, ctx.budget, ctx.extras["flag"]),
    )
    assert isinstance(wrapped, LiveStrategy)
    assert wrapped.strategy_id == "demo"
    out = wrapped.decide(StrategyContext(symbol="MSFT", budget=123.0,
                                         extras={"flag": "x"}))
    assert out[0].symbol == "MSFT" and out[0].est_notional == 123.0
    print("✓ adapt_legacy_strategy wraps positional desks")


if __name__ == "__main__":
    test_ladder_conforms_to_live_strategy_protocol()
    test_ladder_decide_via_context()
    test_legacy_shim_matches_protocol()
    test_adapt_legacy_strategy_wraps_positional_desk()
    print("ALL STRATEGY INTERFACE TESTS PASSED")
