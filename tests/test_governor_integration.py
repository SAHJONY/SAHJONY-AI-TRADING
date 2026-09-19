"""Portfolio-governor live-integration tests (upgrade/world-class).

Verifies risk/portfolio_governor.py is wired into the actual execution path:
- Firm constructs the governor (unless PORTFOLIO_GOVERNOR=false) and injects
  it into ExecutionTrader.
- ExecutionTrader._governor_decision vetoes new risk on the hard-drawdown
  stop and on gross-exposure cap breach, while exits (risk_check=False)
  still flow.
- Firm._governor_cycle_gate throttles budgets smoothly in the soft-drawdown
  band and zeroes them on the hard stop.
- With the governor disabled, the gate is a neutral pass-through.

Paper/sim only: fake broker, temp DB, no network.
"""
from __future__ import annotations

import os

from config import load_config
from database.db import Database
from risk.portfolio_governor import PortfolioRiskGovernor
from risk.risk_engine import RiskEngine
from strategies.base import OrderIntent
from workforce.workforce import ExecutionTrader, Firm


class FakeBroker:
    mode = "offline-sim"

    def __init__(self, price: float = 100.0):
        self.price = price
        self.orders = []

    def get_price(self, symbol):
        return self.price

    def submit_equity_order(self, symbol, qty, side):
        self.orders.append((symbol, qty, side))
        return {"status": "filled", "order_id": "SIM-1"}


def _firm(tmp_path, name="gov", **env):
    for k, v in env.items():
        os.environ[k] = v
    try:
        cfg = load_config()
    finally:
        for k in env:
            os.environ.pop(k, None)
    db = Database(str(tmp_path / f"{name}.db"))
    client = FakeBroker()
    firm = Firm(cfg, client, db)
    return firm, cfg, db, client


def _entry_intent(notional: float = 1_000.0) -> OrderIntent:
    return OrderIntent(
        symbol="AAPL", strategy="ladder", kind="equity", purpose="ladder_entry",
        reason="test", side="buy", qty=notional / 100.0, est_notional=notional,
        risk_check=True,
        set_position={"strategy": "ladder", "shares": notional / 100.0,
                      "entry_price": 100.0, "cost_basis": 100.0},
    )


def _exit_intent() -> OrderIntent:
    return OrderIntent(
        symbol="AAPL", strategy="ladder", kind="equity", purpose="ladder_exit",
        reason="test", side="sell", qty=10.0, est_notional=0.0,
        risk_check=False, clear_position=True,
    )


def test_governor_wired_into_firm_and_trader(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'wired')
    assert firm.governor is not None, "Firm must construct the governor by default"
    assert isinstance(firm.governor, PortfolioRiskGovernor)
    assert firm.execution.governor is firm.governor, \
        "ExecutionTrader must receive the Firm's governor"
    print("✓ governor wired Firm → ExecutionTrader")


def test_governor_disabled_is_neutral(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'disabled', PORTFOLIO_GOVERNOR="false")
    assert firm.governor is None
    assert firm.execution.governor is None
    trader = ExecutionTrader(client, RiskEngine(cfg), db, cfg, governor=None)
    state = {"positions": {}, "pending_orders": {}}
    done, _ = trader.execute([_entry_intent()], state, 1, 100_000.0, 0.0, 0.80, True)
    assert len(done) == 1, "with no governor the entry must flow"
    print("✓ governor disabled → neutral pass-through")


def test_governor_passes_in_normal_conditions(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'normal')
    state = {"positions": {}, "pending_orders": {}, "equity_peak": 100_000.0}
    done, _ = firm.execution.execute([_entry_intent()], state, 1, 100_000.0, 0.0, 0.80, True)
    assert len(done) == 1, "healthy book: entry must clear both gates"
    print("✓ normal conditions: entry flows through governor")


def test_governor_veto_on_hard_drawdown_blocks_entry_but_not_exit(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'harddd')
    # 12% drawdown — past the 10% hard stop.
    state = {"positions": {}, "pending_orders": {}, "equity_peak": 100_000.0}
    done, _ = firm.execution.execute([_entry_intent()], state, 1, 88_000.0, 0.0, 0.80, True)
    assert len(done) == 0, "hard-drawdown stop must veto the entry"
    # The veto must be audited in the state history.
    history = state.get("history", [])
    assert any(e.get("kind") == "governor_block" for e in history), \
        "governor veto must record a governor_block event"
    # Exits still flow during the hard stop — the desk can always reduce risk.
    state2 = {"positions": {"AAPL": {"shares": 10.0, "cost_basis": 100.0}},
              "pending_orders": {}, "equity_peak": 100_000.0}
    done2, _ = firm.execution.execute([_exit_intent()], state2, 1, 88_000.0, 1_000.0, 0.80, True)
    assert len(done2) == 1, "exits must flow even under the governor hard stop"
    assert "AAPL" not in state2["positions"], "exit must clear the position"
    print("✓ hard drawdown: entry vetoed, exit flows")


def test_governor_veto_on_gross_exposure_breach(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'gross')
    # Book already at 79% gross; a 10%-of-equity new position would breach 80%.
    state = {"positions": {"AAPL": {"shares": 790.0, "cost_basis": 100.0}},
             "pending_orders": {}, "equity_peak": 100_000.0}
    done, _ = firm.execution.execute([_entry_intent(10_000.0)], state, 1,
                                     100_000.0, 79_000.0, 0.80, True)
    assert len(done) == 0, "gross-exposure cap breach must veto the entry"
    print("✓ gross-exposure cap: breaching entry vetoed")


def test_governor_cycle_gate_throttles_in_soft_band(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'gate')
    state = {"positions": {}, "equity_peak": 100_000.0}
    # 7% drawdown — inside the 5%→10% soft band: throttle, don't block.
    scale, blocked, reasons = firm._governor_cycle_gate(93_000.0, state)
    assert not blocked
    assert 0.25 <= scale < 1.0, f"expected throttled scale, got {scale}"
    print(f"✓ soft band (7% dd): budgets ×{scale:.2f}")
    # Past the hard stop: scale 0 + blocked.
    scale2, blocked2, _ = firm._governor_cycle_gate(89_000.0, state)
    assert blocked2 and scale2 == 0.0
    print("✓ hard stop (11% dd): budgets zeroed")
    # Healthy: full scale.
    scale3, blocked3, _ = firm._governor_cycle_gate(100_000.0, {"positions": {}})
    assert not blocked3 and scale3 == 1.0
    print("✓ healthy: budgets ×1.00")


def test_governor_cycle_gate_fail_closed_on_bad_equity(tmp_path):
    firm, cfg, db, client = _firm(tmp_path, 'failclosed')
    scale, blocked, _ = firm._governor_cycle_gate(float("nan"), {"positions": {}})
    assert blocked and scale == 0.0, "non-finite equity must fail closed"
    print("✓ fail-closed on non-finite equity")


if __name__ == "__main__":
    import tempfile
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        p = Path(tmp)
        test_governor_wired_into_firm_and_trader(p)
        test_governor_disabled_is_neutral(p)
        test_governor_passes_in_normal_conditions(p)
        test_governor_veto_on_hard_drawdown_blocks_entry_but_not_exit(p)
        test_governor_veto_on_gross_exposure_breach(p)
        test_governor_cycle_gate_throttles_in_soft_band(p)
        test_governor_cycle_gate_fail_closed_on_bad_equity(p)
    print("ALL GOVERNOR INTEGRATION TESTS PASSED")
