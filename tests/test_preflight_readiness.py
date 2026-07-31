from main import readiness_states
from observability.reconciliation import reconcile_positions


def test_read_only_mcp_can_be_data_and_funding_ready_but_never_trading_ready():
    result = readiness_states(
        client_online=True,
        identity_verified=True,
        quote_coverage_complete=True,
        market_data_fresh=True,
        buying_power=19.99,
        equity=25.99,
        positions_reconciled=False,
        trading_armed=False,
        execution_authority=False,
    )
    assert result == {
        "data_ready": True,
        "funding_ready": True,
        "trading_ready": False,
    }


def test_read_only_healthy_data_is_data_ready():
    result = readiness_states(
        client_online=True, identity_verified=True,
        quote_coverage_complete=True, market_data_fresh=True,
        buying_power=0.0, equity=0.0, positions_reconciled=False,
        trading_armed=False, execution_authority=False,
    )
    assert result["data_ready"] is True


def test_read_only_funded_account_is_funding_ready():
    result = readiness_states(
        client_online=True, identity_verified=True,
        quote_coverage_complete=True, market_data_fresh=True,
        buying_power=19.99, equity=25.99, positions_reconciled=False,
        trading_armed=False, execution_authority=False,
    )
    assert result["funding_ready"] is True
    assert result["trading_ready"] is False


def test_expected_local_position_and_empty_broker_positions_do_not_reconcile():
    result = reconcile_positions(
        {"VTI": {"shares": 0.064807}},
        {},
    )
    assert result["reconciled"] is False
    assert result["execution_blocked"] is True
    assert result["differences"] == [{
        "symbol": "VTI", "internal_qty": 0.064807,
        "broker_qty": 0.0, "delta_qty": -0.064807,
    }]


def test_offline_simulation_is_not_data_ready_for_broker_certification():
    result = readiness_states(
        client_online=False, identity_verified=False,
        quote_coverage_complete=True, market_data_fresh=True,
        buying_power=100_000.0, equity=100_000.0, positions_reconciled=True,
        trading_armed=False, execution_authority=False,
    )
    assert result["data_ready"] is False
    assert result["funding_ready"] is True
    assert result["trading_ready"] is False


def test_simulated_balances_never_satisfy_live_trading_readiness():
    result = readiness_states(
        client_online=False, identity_verified=False,
        quote_coverage_complete=True, market_data_fresh=True,
        buying_power=1_000_000.0, equity=1_000_000.0, positions_reconciled=True,
        trading_armed=False, execution_authority=False,
    )
    assert result["trading_ready"] is False


def test_trading_ready_requires_every_gate():
    gates = {
        "client_online": True,
        "identity_verified": True,
        "quote_coverage_complete": True,
        "market_data_fresh": True,
        "buying_power": 100.0,
        "equity": 100.0,
        "positions_reconciled": True,
        "trading_armed": True,
        "execution_authority": True,
    }
    assert readiness_states(**gates)["trading_ready"] is True
    for gate in gates:
        blocked = dict(gates)
        blocked[gate] = 0.0 if gate in {"buying_power", "equity"} else False
        assert readiness_states(**blocked)["trading_ready"] is False
