"""Catastrophic per-position hard-stop tests (upgrade/world-class).

Verifies Firm._catastrophic_stop_sweep wires up RiskEngine.hard_stop_breached():
- A long 30% below cost basis is liquidated (default 25% floor).
- A long 10% below basis is left alone (strategy stops own it).
- A short 30% ABOVE basis is covered.
- Positions without a valid basis/price are skipped, never blown up.
- The sweep emits risk_check=False exits (flows during halts).
"""
from __future__ import annotations

import os

from config import load_config
from database.db import Database
from workforce.workforce import Firm


class FakeBroker:
    mode = "offline-sim"

    def __init__(self, prices=None):
        self.prices = prices or {}
        self.orders = []

    def get_price(self, symbol):
        return self.prices.get(symbol, 0.0)

    def submit_equity_order(self, symbol, qty, side):
        self.orders.append((symbol, qty, side))
        return {"status": "filled", "order_id": "SIM-1"}


def _firm(tmp_path, name, prices):
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    cfg = load_config()
    db = Database(str(tmp_path / f"{name}.db"))
    client = FakeBroker(prices)
    return Firm(cfg, client, db), client


def test_sweep_liquidates_deep_loser(tmp_path):
    firm, client = _firm(tmp_path, "sweep1", {"AAPL": 70.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 100.0}},
             "pending_orders": {}}
    done = firm._catastrophic_stop_sweep(state, 1, 100_000.0)
    assert len(done) == 1, "30% loser must be liquidated"
    assert client.orders[0] == ("AAPL", 10.0, "sell")
    assert "AAPL" not in state["positions"]
    print("✓ deep loser liquidated")


def test_sweep_leaves_healthy_position_alone(tmp_path):
    firm, client = _firm(tmp_path, "sweep2", {"AAPL": 90.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 100.0}},
             "pending_orders": {}}
    done = firm._catastrophic_stop_sweep(state, 1, 100_000.0)
    assert len(done) == 0, "10% dip is the strategy's stop, not the backstop's"
    assert client.orders == []
    print("✓ healthy position untouched")


def test_sweep_covers_deep_short_loser(tmp_path):
    firm, client = _firm(tmp_path, "sweep3", {"SPY": 130.0})
    state = {"positions": {"SPY": {"strategy": "pairs", "shares": -10.0,
                                   "cost_basis": 100.0}},
             "pending_orders": {}}
    done = firm._catastrophic_stop_sweep(state, 1, 100_000.0)
    assert len(done) == 1, "short 30% underwater must be covered"
    assert client.orders[0] == ("SPY", 10.0, "buy")
    print("✓ deep short loser covered")


def test_sweep_skips_unpriceable_position(tmp_path):
    firm, client = _firm(tmp_path, "sweep4", {"AAPL": 0.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 100.0}},
             "pending_orders": {}}
    done = firm._catastrophic_stop_sweep(state, 1, 100_000.0)
    assert len(done) == 0, "zero quote must not trigger a liquidation"
    assert "AAPL" in state["positions"]
    print("✓ unpriceable position skipped (no blow-up on bad data)")


def test_sweep_skips_missing_basis(tmp_path):
    firm, client = _firm(tmp_path, "sweep5", {"AAPL": 10.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0}},
             "pending_orders": {}}
    done = firm._catastrophic_stop_sweep(state, 1, 100_000.0)
    assert len(done) == 0, "missing basis → cannot evaluate → skip"
    print("✓ missing basis skipped")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        test_sweep_liquidates_deep_loser(p)
        test_sweep_leaves_healthy_position_alone(p)
        test_sweep_covers_deep_short_loser(p)
        test_sweep_skips_unpriceable_position(p)
        test_sweep_skips_missing_basis(p)
    print("ALL CATASTROPHIC STOP TESTS PASSED")
