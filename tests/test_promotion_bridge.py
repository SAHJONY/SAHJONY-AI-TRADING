"""Promotion-bridge tests (upgrade/autonomous-profit).

Research→live path for validated backtest strategies (S1–S18):
- Unknown strategy ids are rejected loudly.
- Double-gated: PROMOTED_DESKS_ENABLED + PROMOTED_STRATEGIES, both default OFF.
- The adapter satisfies the LiveStrategy protocol.
- signal() → risk-gated entry intent; manage() → halt-proof exit intent.
- Insufficient measured bars → stands down (no signal, no trade).
- A signal without a stop is refused (no stop = no trade).
"""
from __future__ import annotations

import os
from dataclasses import replace

import numpy as np
import pytest

from backtest.data import Bars
from backtest.engine import Setup, Strategy
from config import load_config
from database.db import Database
from strategies.base import LiveStrategy, StrategyContext
from strategies.promoted import (
    STRATEGY_CLASSES,
    BacktestStrategyAdapter,
    enabled_strategy_ids,
)
from utils.bar_recorder import BarRecorder, MIN_TICKS_MEASURED_RANGE


class StubStrategy(Strategy):
    """Deterministic stand-in: signals once, then exits on the next bar."""
    id = "stub"
    warmup = 5
    PARAMS = {}

    def __init__(self, with_stop=True):
        super().__init__()
        self._with_stop = with_stop
        self.signaled = False

    def prepare(self, bars: Bars):
        return {}

    def signal(self, t, bars, ind):
        if self.signaled:
            return None
        self.signaled = True
        px = float(bars.close[t])
        return Setup(side=1, stop=px * 0.95 if self._with_stop else 0.0,
                     tag="stub_long")

    def manage(self, t, bars, ind, pos):
        return "stub_time_exit"


class NoSignalStrategy(StubStrategy):
    id = "stubflat"

    def signal(self, t, bars, ind):
        return None


def _db_with_bars(tmp_path, name, symbol="BTC/USD", n=12, ticks_per_bar=3,
                  price=50000.0):
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    db = Database(str(tmp_path / f"{name}.db"))
    rec = BarRecorder(db, [15], source="test")
    # record() folds one quote per call into the current bucket; to get
    # multi-tick bars we write rows directly.
    import time
    now = int(time.time())
    step = 15 * 60
    base = now // step * step - n * step
    for i in range(n):
        ts = base + i * step
        drift = price * (1 + 0.001 * i)
        db.conn.execute(
            """INSERT INTO bars (symbol, ts, interval_m, open, high, low, close,
                                 volume, source)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(symbol, ts, interval_m) DO NOTHING""",
            (symbol, ts, 15, drift, drift * 1.002, drift * 0.998, drift,
             ticks_per_bar, "test"))
    db.conn.commit()
    return db


def _ctx(symbol="BTC/USD", budget=1000.0, state=None, price=50500.0):
    return StrategyContext(symbol=symbol, budget=budget, state=state or {},
                           get_price=lambda s: price,
                           extras={"allow_fractional": True})


def test_unknown_strategy_rejected():
    with pytest.raises(ValueError):
        BacktestStrategyAdapter("s4", db=None)   # s4 needs order-book data: absent
    with pytest.raises(ValueError):
        BacktestStrategyAdapter("nope", db=None)
    print("✓ unknown ids rejected")


def test_double_gate_defaults_off(tmp_path):
    cfg = load_config()
    assert enabled_strategy_ids(cfg) == [], "global flag defaults off"
    cfg2 = replace(cfg, promoted_desks_enabled=True)
    assert enabled_strategy_ids(cfg2) == [], "no ids → nothing enabled"
    cfg3 = replace(cfg, promoted_desks_enabled=True,
                   promoted_strategy_ids=["s1", "bogus"])
    assert enabled_strategy_ids(cfg3) == ["s1"], "unknown ids filtered"
    print("✓ double-gated, default off, unknown ids filtered")


def test_adapter_satisfies_live_protocol(tmp_path):
    db = _db_with_bars(tmp_path, "proto")
    adapter = BacktestStrategyAdapter("s1", db, strategy=StubStrategy())
    assert isinstance(adapter, LiveStrategy)
    assert adapter.desk_family == "promoted"
    print("✓ adapter satisfies the LiveStrategy protocol")


def test_signal_becomes_risk_gated_entry(tmp_path):
    db = _db_with_bars(tmp_path, "entry")
    adapter = BacktestStrategyAdapter("s3", db, strategy=StubStrategy())
    state = {}
    intents = adapter.decide(_ctx(state=state))
    assert len(intents) == 1
    intent = intents[0]
    assert intent.side == "buy" and intent.qty > 0
    assert intent.risk_check is True, "entries go through the RiskEngine"
    assert not intent.clear_position
    assert intent.set_position["strategy"] == "promoted:s3"
    assert intent.set_position["stop"] > 0
    print("✓ signal → risk-gated entry intent with tracked stop")


def test_manage_becomes_halt_proof_exit(tmp_path):
    db = _db_with_bars(tmp_path, "exit")
    adapter = BacktestStrategyAdapter("s3", db, strategy=StubStrategy())
    state = {"positions": {
        "BTC/USD": {"strategy": "promoted:s3", "shares": 0.02,
                    "cost_basis": 50000.0, "stop": 47500.0,
                    "targets": [], "entry_bar": 0}}}
    intents = adapter.decide(_ctx(state=state, budget=0.0))
    assert len(intents) == 1, "exits must flow even with zero budget"
    intent = intents[0]
    assert intent.side == "sell" and intent.clear_position is True
    assert intent.risk_check is False, "exits flow during halts"
    assert intent.realized_delta != 0
    print("✓ manage() → halt-proof exit intent with realized P&L")


def test_insufficient_bars_stands_down(tmp_path):
    db = _db_with_bars(tmp_path, "thin", n=3)   # warmup is 5
    adapter = BacktestStrategyAdapter("s3", db, strategy=StubStrategy())
    assert adapter.decide(_ctx(state={})) == []
    print("✓ fewer bars than warmup → no signal, no trade")


def test_single_tick_bars_excluded(tmp_path):
    # All bars single-tick → no measured range → stand down.
    db = _db_with_bars(tmp_path, "single", n=12, ticks_per_bar=1)
    adapter = BacktestStrategyAdapter("s3", db, strategy=StubStrategy())
    assert adapter.decide(_ctx(state={})) == []
    print("✓ fabricated (single-tick) bars never reach the strategy")


def test_stop_is_mandatory(tmp_path):
    db = _db_with_bars(tmp_path, "nostop")
    adapter = BacktestStrategyAdapter("s3", db, strategy=StubStrategy(with_stop=False))
    assert adapter.decide(_ctx(state={})) == [], "a stop-less long is refused"
    print("✓ signal without a stop is refused")


def test_registry_covers_expected_ids():
    for sid in ["s1", "s2", "s3", "s5", "s6", "s9", "s11", "s12", "s13",
                "s14", "s15", "s16", "s17", "s18"]:
        assert sid in STRATEGY_CLASSES, sid
    assert "s4" not in STRATEGY_CLASSES, "s4 needs L2 data — not promotable"
    print("✓ registry covers the promotable S-ids (14)")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        test_unknown_strategy_rejected()
        test_double_gate_defaults_off(p)
        test_adapter_satisfies_live_protocol(p)
        test_signal_becomes_risk_gated_entry(p)
        test_manage_becomes_halt_proof_exit(p)
        test_insufficient_bars_stands_down(p)
        test_single_tick_bars_excluded(p)
        test_stop_is_mandatory(p)
        test_registry_covers_expected_ids()
    print("ALL PROMOTION BRIDGE TESTS PASSED")
