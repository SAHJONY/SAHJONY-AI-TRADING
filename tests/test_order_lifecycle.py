"""Order lifecycle regressions: acknowledgement is never booked as a fill."""
from __future__ import annotations

import os
import tempfile

from config import load_config
from database.db import Database
from risk.risk_engine import RiskEngine
from strategies.base import OrderIntent
from workforce.workforce import ExecutionTrader


def _check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("✓", message)


class PendingBroker:
    mode = "LIVE"

    def __init__(self):
        self.lifecycle = {"status": "pending", "order_id": "RH-1"}

    def submit_equity_order(self, symbol, qty, side):
        return {"status": "submitted", "order_id": "RH-1",
                "client_order_id": "CLIENT-1", "submitted_at": "2026-07-29T00:00:00Z",
                "simulated": False}

    def get_order(self, order_id):
        return dict(self.lifecycle)

    def get_price(self, symbol):
        return 100.0


def main() -> int:
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    cfg = load_config()
    broker = PendingBroker()
    with tempfile.TemporaryDirectory() as td:
        db = Database(os.path.join(td, "orders.db"))
        trader = ExecutionTrader(broker, RiskEngine(cfg), db, cfg)
        state = {"positions": {}, "realized_pnl": 0.0}
        intent = OrderIntent(
            "ETH/USD", "ladder", "equity", "ladder_entry", side="buy",
            qty=0.01, est_notional=1.0, risk_check=False,
            set_position={"strategy": "ladder", "shares": 0.01, "cost_basis": 100.0},
        )

        done, deployed = trader.execute([intent], state, 7, 100.0, 0.0, 0.8)
        _check(done[0]["status"] == "submitted", "broker acknowledgement is recorded as submitted")
        _check("ETH/USD" not in state["positions"], "submitted order does not mutate positions")
        _check(deployed == 0.0, "submitted order does not consume filled-position budget")
        _check(db.recent_trades() == [], "submitted order is not written to the fills ledger")

        again, _ = trader.execute([intent], state, 8, 100.0, 0.0, 0.8)
        _check(again == [], "unresolved order blocks a duplicate order for the same symbol")

        broker.lifecycle = {
            "status": "filled", "order_id": "RH-1", "client_order_id": "CLIENT-1",
            "fill_price": 101.25, "filled_qty": 0.01,
            "filled_at": "2026-07-29T00:00:03Z",
        }
        resolved = trader.reconcile_pending(state, 9)
        _check(resolved == [{"symbol": "ETH/USD", "status": "filled"}],
               "confirmed broker fill resolves the pending order")
        _check(state["positions"]["ETH/USD"]["shares"] == 0.01,
               "position mutates only after confirmed fill")
        trade = db.recent_trades()[0]
        _check(trade["price"] == 101.25 and trade["order_id"] == "RH-1",
               "ledger stores actual fill price and broker attribution")
        _check(trade["client_order_id"] == "CLIENT-1" and trade["order_status"] == "filled",
               "ledger stores client order id and terminal status")
        db.close()

    print("\nORDER LIFECYCLE TESTS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
