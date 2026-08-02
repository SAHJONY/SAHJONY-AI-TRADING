from config import Config
from database import Database
from risk.risk_engine import RiskEngine
from strategies.base import OrderIntent
from workforce.workforce import ExecutionTrader


class Broker:
    mode = "paper"

    def __init__(self, status):
        self.status = status
        self.calls = []
        self.price_calls = 0

    def submit_equity_order(self, symbol, qty, side):
        self.calls.append((symbol, qty, side))
        result = {"status": self.status, "id": "broker-1"}
        if self.status == "filled":
            result["fill_price"] = 101.0
        return result

    def get_price(self, symbol):
        self.price_calls += 1
        return 100.0


class ReconcilingBroker(Broker):
    def __init__(self, statuses):
        super().__init__("submitted")
        self.statuses = iter(statuses)

    def get_order_status(self, order_id, symbol):
        result = next(self.statuses)
        return {"id": order_id, **result}


def intent():
    return OrderIntent(
        symbol="SPY", strategy="ladder", kind="equity", purpose="entry",
        side="buy", qty=1, est_notional=100, risk_check=True,
        set_position={"shares": 1, "entry": 101.0},
    )


def trader(tmp_path, broker):
    db = Database(str(tmp_path / "execution.db"))
    return ExecutionTrader(broker, RiskEngine(Config()), db, Config()), db


def test_submitted_order_does_not_mutate_portfolio_or_log_fill(tmp_path):
    broker = Broker("submitted")
    subject, db = trader(tmp_path, broker)
    state = {"positions": {}, "realized_pnl": 0.0}

    done, deployed = subject.execute(
        [intent()], state, cycle=1, equity=100_000, deployed=0,
        conviction=1.0,
    )

    assert done[0]["status"] == "submitted"
    assert state["positions"] == {}
    assert state["realized_pnl"] == 0.0
    assert state["pending_orders"]["SPY"]["broker_ref"] == "broker-1"
    assert deployed == 0
    assert broker.price_calls == 0
    assert db.recent_trades() == []
    db.close()


def test_pending_symbol_blocks_duplicate_submission_across_cycles(tmp_path):
    broker = Broker("submitted")
    subject, db = trader(tmp_path, broker)
    state = {"positions": {}}

    subject.execute([intent()], state, 1, 100_000, 0, 1.0)
    done, deployed = subject.execute([intent()], state, 2, 100_000, 0, 1.0)

    assert done == []
    assert deployed == 0
    assert len(broker.calls) == 1
    kinds = [row["kind"] for row in db.conn.execute(
        "SELECT kind FROM audit_ledger ORDER BY sequence"
    )]
    assert "pending_order_block" in kinds
    db.close()


def test_confirmed_fill_applies_state_and_logs_trade(tmp_path):
    broker = Broker("filled")
    subject, db = trader(tmp_path, broker)
    state = {"positions": {}}

    done, deployed = subject.execute(
        [intent()], state, cycle=1, equity=100_000, deployed=0,
        conviction=1.0,
    )

    assert done[0]["purpose"] == "entry"
    assert state["positions"]["SPY"]["shares"] == 1
    assert deployed == 100
    assert broker.price_calls == 0
    assert len(db.recent_trades()) == 1
    db.close()


def test_later_fill_reconciles_persisted_intent_exactly_once(tmp_path):
    broker = ReconcilingBroker([
        {"status": "filled", "fill_price": 102.0, "transaction_cost": 0.25},
    ])
    subject, db = trader(tmp_path, broker)
    state = {"positions": {}, "realized_pnl": 0.0}

    subject.execute([intent()], state, 1, 100_000, 0, 1.0)
    deployed = subject.reconcile_pending_orders(state, 2, 0)

    assert state["positions"]["SPY"]["shares"] == 1
    assert state["realized_pnl"] == -0.25
    assert state["pending_orders"] == {}
    assert deployed == 100
    assert len(db.recent_trades()) == 1
    # Same-cycle retries cannot apply the fill twice.
    assert subject.reconcile_pending_orders(state, 2, deployed) == deployed
    assert len(db.recent_trades()) == 1
    db.close()


def test_terminal_rejection_releases_symbol_without_state_change(tmp_path):
    broker = ReconcilingBroker([{"status": "rejected"}])
    subject, db = trader(tmp_path, broker)
    state = {"positions": {}}

    subject.execute([intent()], state, 1, 100_000, 0, 1.0)
    deployed = subject.reconcile_pending_orders(state, 2, 0)

    assert state["positions"] == {}
    assert state["pending_orders"] == {}
    assert deployed == 0
    row = db.conn.execute(
        "SELECT status FROM execution_intents"
    ).fetchone()
    assert row["status"] == "failed"
    db.close()


def test_status_error_keeps_pending_lock_fail_closed(tmp_path):
    class BrokenStatusBroker(Broker):
        def get_order_status(self, order_id, symbol):
            raise TimeoutError("broker unavailable")

    broker = BrokenStatusBroker("submitted")
    subject, db = trader(tmp_path, broker)
    state = {"positions": {}}

    subject.execute([intent()], state, 1, 100_000, 0, 1.0)
    deployed = subject.reconcile_pending_orders(state, 2, 0)

    assert "SPY" in state["pending_orders"]
    assert deployed == 0
    assert db.recent_trades() == []
    db.close()
