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
