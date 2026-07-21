import pytest

from observability.reconciliation import reconcile_positions


def test_matching_positions_reconcile():
    result = reconcile_positions(
        {"VTI": {"shares": 1.25}, "QQQ": {"shares": -0.5}},
        {"VTI": {"qty": 1.25}, "QQQ": {"qty": -0.5}},
    )
    assert result["status"] == "reconciled"
    assert result["reconciled"] is True
    assert result["execution_blocked"] is False


def test_missing_or_quantity_mismatch_fails_closed():
    result = reconcile_positions(
        {"VTI": {"shares": 1.0}, "MSFT": {"shares": 2.0}},
        {"VTI": {"qty": 0.75}},
    )
    assert result["status"] == "mismatch"
    assert result["execution_blocked"] is True
    assert {row["symbol"] for row in result["differences"]} == {"MSFT", "VTI"}


def test_invalid_numeric_snapshot_fails_closed():
    result = reconcile_positions({"VTI": {"shares": float("nan")}}, {})
    assert result["status"] == "error"
    assert result["reconciled"] is False
    assert result["execution_blocked"] is True


def test_equity_above_cash_without_visible_positions_does_not_reconcile():
    result = reconcile_positions(
        {}, {}, account_equity=25.94, account_cash=19.99, value_tolerance=1.0,
    )

    assert result["status"] == "mismatch"
    assert result["reconciled"] is False
    assert result["execution_blocked"] is True
    assert result["internal_position_count"] == 0
    assert result["broker_position_count"] == 0
    assert result["unexplained_value"] == pytest.approx(5.95)
    assert result["differences"] == [{
        "kind": "unexplained_account_value",
        "unexplained_value": pytest.approx(5.95),
    }]
    assert all("symbol" not in difference for difference in result["differences"])


@pytest.mark.parametrize("equity,cash", [(25.94, None), (None, 19.99)])
def test_partial_account_totals_fail_closed(equity, cash):
    result = reconcile_positions({}, {}, account_equity=equity, account_cash=cash)
    assert result["status"] == "error"
    assert result["reconciled"] is False
    assert result["execution_blocked"] is True
    assert "both account equity and cash" in result["error"]


def test_visible_position_without_market_value_is_not_assumed_zero():
    result = reconcile_positions(
        {"VTI": {"shares": 1}}, {"VTI": {"qty": 1}},
        account_equity=125, account_cash=25,
    )
    assert result["status"] == "error"
    assert result["reconciled"] is False
    assert result["execution_blocked"] is True
    assert "missing market_value" in result["error"]


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf"), -1])
def test_invalid_value_tolerance_fails_closed(tolerance):
    result = reconcile_positions(
        {}, {}, account_equity=25.94, account_cash=19.99, value_tolerance=tolerance,
    )
    assert result["status"] == "error"
    assert result["reconciled"] is False
    assert result["execution_blocked"] is True
