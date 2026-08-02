import pytest

from config import Config
from database import Database
from risk.risk_engine import RiskEngine
from strategies.base import OrderIntent, validate_order_intent
from workforce.workforce import ExecutionTrader


@pytest.mark.parametrize("qty", [0, -1, float("nan"), float("inf")])
def test_all_orders_require_positive_finite_quantity(qty):
    intent = OrderIntent(
        symbol="SPY", strategy="ladder", kind="equity", purpose="exit",
        side="sell", qty=qty, risk_check=False,
    )

    assert validate_order_intent(intent) is not None


def test_equity_order_requires_known_side():
    intent = OrderIntent(
        symbol="SPY", strategy="ladder", kind="equity", purpose="exit",
        side="sell_to_close", qty=1,
    )

    assert validate_order_intent(intent) == "invalid equity side"


def test_option_order_requires_contract():
    intent = OrderIntent(
        symbol="SPY", strategy="wheel", kind="option", purpose="close",
        side="buy_to_close", qty=1,
    )

    assert validate_order_intent(intent) == "missing option contract"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("est_notional", float("nan")),
        ("est_notional", -1),
        ("strike", float("inf")),
        ("premium", -0.01),
    ],
)
def test_order_numeric_fields_must_be_finite_and_non_negative(field, value):
    values = {
        "symbol": "SPY",
        "strategy": "ladder",
        "kind": "equity",
        "purpose": "entry",
        "side": "buy",
        "qty": 1,
        field: value,
    }

    assert validate_order_intent(OrderIntent(**values)) is not None


def test_state_intents_remain_non_broker_mutations():
    intent = OrderIntent(
        symbol="SPY", strategy="wheel", kind="state", purpose="wait",
    )

    assert intent.is_order is False


class BrokerTripwire:
    mode = "offline-sim"

    def __init__(self):
        self.calls = []

    def submit_equity_order(self, *args):
        self.calls.append(args)
        raise AssertionError("malformed order reached broker")


def test_execution_trader_blocks_malformed_exit_before_broker(tmp_path):
    broker = BrokerTripwire()
    db = Database(str(tmp_path / "execution.db"))
    trader = ExecutionTrader(broker, RiskEngine(Config()), db, Config())
    intent = OrderIntent(
        symbol="SPY", strategy="ladder", kind="equity", purpose="exit",
        side="sell", qty=float("nan"), risk_check=False,
    )

    done, deployed = trader.execute(
        [intent], {"positions": {}}, cycle=1, equity=100_000,
        deployed=1_000, conviction=1.0, allow_new_risk=False,
    )

    assert done == []
    assert deployed == 1_000
    assert broker.calls == []
    audit = db.conn.execute(
        "SELECT kind FROM audit_ledger ORDER BY sequence"
    ).fetchall()
    assert [row[0] for row in audit] == ["invalid_intent_block"]
    db.close()
