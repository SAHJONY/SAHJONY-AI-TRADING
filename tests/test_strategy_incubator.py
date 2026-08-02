import numpy as np

from strategies.regime_momentum import RegimeMomentum
from strategies.statistical_mean_reversion import StatisticalMeanReversion
from strategies.volatility_breakout import VolatilityBreakout


def test_regime_momentum_emits_entry_on_sustained_uptrend():
    closes = np.linspace(50, 100, 120)
    out = RegimeMomentum().decide("VTI", closes, budget=100, state={}, fractional=True)
    assert out and out[0].purpose == "regime_momentum_entry"
    assert out[0].risk_check is True


def test_volatility_breakout_emits_entry_on_new_high():
    closes = np.concatenate([np.linspace(90, 100, 25), np.array([105.0])])
    out = VolatilityBreakout(lookback=20).decide("QQQ", closes, budget=100, state={}, fractional=True)
    assert out and out[0].purpose == "volatility_breakout_entry"


def test_mean_reversion_emits_entry_on_extreme_negative_zscore():
    closes = np.concatenate([np.full(29, 100.0), np.array([80.0])])
    out = StatisticalMeanReversion(lookback=30).decide("SPY", closes, budget=100, state={}, fractional=True)
    assert out and out[0].purpose == "mean_reversion_entry"


def test_mean_reversion_requires_history():
    assert StatisticalMeanReversion().decide("SPY", [100, 99], budget=100, state={}) == []
