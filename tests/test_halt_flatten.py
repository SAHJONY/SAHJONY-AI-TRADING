"""Halt-flatten tests (upgrade/autonomous-profit).

A halt that only blocks new risk while a bleeding book stays open protects
nothing. Verifies Firm._halt_flatten_step / _flatten_all_positions:
- Kill-switch/breaker halt liquidates longs and covers shorts (once).
- Edge-triggered: no re-flatten while the halt stays latched.
- Marker re-arms when the halt clears.
- Option legs are NEVER auto-closed (reported for manual handling).
- Flatten exits are risk_check=False — they flow during a halt.
- flatten_on_halt=False restores the old freeze-only behavior.
"""
from __future__ import annotations

import os
from dataclasses import replace

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


def _firm(tmp_path, name, prices, **cfg_over):
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    cfg = load_config()
    for k, v in cfg_over.items():
        cfg = replace(cfg, **{k: v})
    db = Database(str(tmp_path / f"{name}.db"))
    client = FakeBroker(prices)
    firm = Firm(cfg, client, db)
    firm._cycle_risk_events = []
    return firm, client


def _halt(reason="kill switch (TRADING_HALT / HALT file)"):
    return {"halted": True, "reason": reason, "day_return": -0.06,
            "day_start": 100000.0, "limit_pct": 0.05}


def test_flatten_liquidates_book_on_halt(tmp_path):
    firm, client = _firm(tmp_path, "fl1", {"AAPL": 150.0, "SPY": 500.0})
    state = {"positions": {
        "AAPL": {"strategy": "ladder", "shares": 10.0, "cost_basis": 145.0},
        "SPY": {"strategy": "pairs", "shares": -5.0, "cost_basis": 510.0},
    }, "pending_orders": {}}
    done = firm._halt_flatten_step(state, 1, 100_000.0, _halt())
    assert len(done) == 2, "both positions must flatten on halt"
    assert ("AAPL", 10.0, "sell") in client.orders
    assert ("SPY", 5.0, "buy") in client.orders      # short covered
    assert state["positions"] == {}, "book must be flat"
    assert state["halt_flattened"]["reason"].startswith("kill switch")
    assert len(firm._cycle_risk_events) == 1, "flatten must page"
    print("✓ halt flattens longs and covers shorts")


def test_flatten_fires_once_per_halt_episode(tmp_path):
    firm, client = _firm(tmp_path, "fl2", {"AAPL": 150.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 145.0}},
             "pending_orders": {}}
    firm._halt_flatten_step(state, 1, 100_000.0, _halt())
    assert len(client.orders) == 1
    # Second cycle, halt still latched, new position somehow present:
    # must NOT re-flatten (edge-triggered).
    state["positions"]["MSFT"] = {"strategy": "ladder", "shares": 5.0,
                                  "cost_basis": 300.0}
    done = firm._halt_flatten_step(state, 2, 100_000.0, _halt())
    assert done == [] and len(client.orders) == 1, "no re-flatten while latched"
    print("✓ edge-triggered: fires once per halt episode")


def test_flatten_rearms_when_halt_clears(tmp_path):
    firm, client = _firm(tmp_path, "fl3", {"AAPL": 150.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 145.0}},
             "pending_orders": {}}
    firm._halt_flatten_step(state, 1, 100_000.0, _halt())
    firm._halt_flatten_step(state, 2, 100_000.0,
                            {"halted": False, "reason": ""})
    assert "halt_flattened" not in state, "marker must clear with the halt"
    print("✓ re-arms when the halt clears")


def test_flatten_never_closes_option_legs(tmp_path):
    firm, client = _firm(tmp_path, "fl4", {"AAPL": 150.0})
    state = {"positions": {
        "AAPL": {"strategy": "ladder", "shares": 10.0, "cost_basis": 145.0},
        "AAPL_PUT": {"strategy": "wheel_option", "stage": "short_put",
                     "contracts": 2, "strike": 140.0,
                     "contract": "AAPL240119P00140000"},
    }, "pending_orders": {}}
    done = firm._halt_flatten_step(state, 1, 100_000.0, _halt())
    assert len(done) == 1, "only the equity leg flattens"
    assert client.orders == [("AAPL", 10.0, "sell")]
    assert "AAPL_PUT" in state["positions"], "option leg must survive"
    assert len(state["halt_flattened"]["open_options"]) == 1
    assert "NOT auto-closed" in firm._cycle_risk_events[0][1]
    print("✓ option legs never auto-closed; paged for manual handling")


def test_flatten_exits_flow_during_halt(tmp_path):
    # risk_check=False exits must clear ExecutionTrader even with
    # allow_new_risk=False (the halt condition).
    firm, client = _firm(tmp_path, "fl5", {"AAPL": 150.0})
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 145.0}},
             "pending_orders": {}}
    intents_done, _ = firm._flatten_all_positions(state, 1, 100_000.0, "test")
    assert intents_done, "flatten must produce exits"
    print("✓ flatten exits produced (risk_check=False, halt-proof)")


def test_flatten_disabled_restores_freeze_only(tmp_path):
    firm, client = _firm(tmp_path, "fl6", {"AAPL": 150.0}, flatten_on_halt=False)
    state = {"positions": {"AAPL": {"strategy": "ladder", "shares": 10.0,
                                   "cost_basis": 145.0}},
             "pending_orders": {}}
    done = firm._halt_flatten_step(state, 1, 100_000.0, _halt())
    assert done == [] and client.orders == []
    assert "AAPL" in state["positions"]
    print("✓ FLATTEN_ON_HALT=false restores freeze-only behavior")


def test_flatten_never_sells_adopted_positions(tmp_path):
    # ADOPT-BUT-DON'T-SELL policy: pre-existing broker holdings adopted by
    # _reconcile_broker (pos["adopted"] is True) must NEVER be auto-liquidated
    # by a halt flatten — selling into reconciliation uncertainty is the
    # riskiest action. Bot-opened positions still flatten normally.
    firm, client = _firm(tmp_path, "fl7", {"AAPL": 150.0, "BTC": 81000.0})
    state = {"positions": {
        "AAPL": {"strategy": "ladder", "shares": 10.0, "cost_basis": 145.0},
        "BTC": {"strategy": "ladder", "shares": 0.001, "cost_basis": 80000.0,
                "adopted": True},
    }, "pending_orders": {}}
    done = firm._halt_flatten_step(state, 1, 100_000.0,
                                  _halt("broker position reconciliation failed"))
    assert len(done) == 1, "only the bot-opened position flattens"
    assert ("AAPL", 10.0, "sell") in client.orders
    assert not any(o[0] == "BTC" for o in client.orders), \
        "adopted position must never be auto-sold"
    assert "BTC" in state["positions"], "adopted position stays in the book"
    print("✓ halt flatten never sells adopted (pre-existing) positions")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        test_flatten_liquidates_book_on_halt(p)
        test_flatten_fires_once_per_halt_episode(p)
        test_flatten_rearms_when_halt_clears(p)
        test_flatten_never_closes_option_legs(p)
        test_flatten_exits_flow_during_halt(p)
        test_flatten_disabled_restores_freeze_only(p)
        test_flatten_never_sells_adopted_positions(p)
    print("ALL HALT FLATTEN TESTS PASSED")
