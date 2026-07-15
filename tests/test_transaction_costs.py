import pytest

from execution.cost_model import estimate_equity_fill, option_contract_fee


def test_buy_and_sell_slippage_are_adverse():
    buy = estimate_equity_fill(100, 10, "buy", slippage_bps=5, commission_per_share=.005)
    sell = estimate_equity_fill(100, 10, "sell", slippage_bps=5, commission_per_share=.005)
    assert buy.fill_price == pytest.approx(100.05)
    assert sell.fill_price == pytest.approx(99.95)
    assert buy.transaction_cost == pytest.approx(0.55)
    assert sell.transaction_cost == pytest.approx(0.55)


def test_option_fee_scales_by_contract():
    assert option_contract_fee(3, fee_per_contract=.65) == pytest.approx(1.95)


def test_invalid_cost_inputs_are_rejected():
    with pytest.raises(ValueError):
        estimate_equity_fill(0, 1, "buy")
