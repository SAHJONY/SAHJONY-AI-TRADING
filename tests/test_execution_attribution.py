import pytest

from execution.attribution import ExecutionAttribution


def test_buy_slippage_and_net_pnl():
    item = ExecutionAttribution(
        side="buy",
        quantity=100,
        reference_price=10.00,
        fill_price=10.05,
        gross_pnl=100.0,
        fees=1.0,
        spread_cost=2.0,
        adverse_selection_cost=3.0,
    )
    assert item.slippage_cost == pytest.approx(5.0)
    assert item.execution_cost == pytest.approx(11.0)
    assert item.net_pnl == pytest.approx(89.0)
    assert item.implementation_shortfall_bps == pytest.approx(110.0)


def test_sell_slippage_is_direction_aware():
    item = ExecutionAttribution(
        side="sell",
        quantity=50,
        reference_price=20.0,
        fill_price=19.8,
        gross_pnl=40.0,
    )
    assert item.slippage_cost == pytest.approx(10.0)
    assert item.net_pnl == pytest.approx(30.0)


def test_price_improvement_is_not_negative_cost():
    item = ExecutionAttribution(
        side="buy",
        quantity=10,
        reference_price=100.0,
        fill_price=99.5,
        gross_pnl=20.0,
    )
    assert item.slippage_cost == 0.0
    assert item.execution_cost == 0.0


def test_invalid_side_fails_closed():
    with pytest.raises(ValueError):
        ExecutionAttribution(
            side="hold",
            quantity=1,
            reference_price=100,
            fill_price=100,
            gross_pnl=0,
        )
