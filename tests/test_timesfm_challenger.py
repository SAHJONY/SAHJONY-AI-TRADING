import pytest

from forecasting.timesfm_challenger import build_timesfm_challenger


def test_timesfm_challenger_normalizes_forecast():
    history = [100.0 + i * 0.1 for i in range(80)]

    def predictor(values, horizon):
        assert horizon == 6
        return 109.0, 107.0, 111.0

    out = build_timesfm_challenger(
        symbol="btc/usd",
        history=history,
        horizon_steps=6,
        predictor=predictor,
    )
    assert out.symbol == "BTC/USD"
    assert out.execution_authority is False
    assert out.lower <= out.point_forecast <= out.upper
    assert 0.0 <= out.confidence <= 1.0


def test_timesfm_challenger_rejects_short_context():
    with pytest.raises(ValueError):
        build_timesfm_challenger(
            symbol="BTC/USD",
            history=[100.0] * 10,
            horizon_steps=3,
            predictor=lambda values, horizon: (101.0, 99.0, 103.0),
        )


def test_timesfm_challenger_rejects_bad_interval():
    history = [100.0] * 80
    with pytest.raises(ValueError):
        build_timesfm_challenger(
            symbol="BTC/USD",
            history=history,
            horizon_steps=3,
            predictor=lambda values, horizon: (101.0, 102.0, 103.0),
        )


def test_timesfm_challenger_expected_return_uses_last_observation():
    history = [100.0] * 79 + [110.0]
    out = build_timesfm_challenger(
        symbol="BTC/USD",
        history=history,
        horizon_steps=1,
        predictor=lambda values, horizon: (121.0, 118.0, 124.0),
    )
    assert out.expected_return == pytest.approx(0.10)
