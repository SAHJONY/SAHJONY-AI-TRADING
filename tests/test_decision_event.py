import pytest

from telemetry.decision_event import ShadowDecisionEvent


def test_event_is_explicitly_non_executable():
    e = ShadowDecisionEvent(
        symbol="BTC/USD",
        strategy="momentum",
        champion_signal=0.4,
        champion_confidence=0.7,
        challenger_signal=0.6,
        challenger_confidence=0.8,
        reference_price=65000.0,
        features={"ofi": 0.2, "spread_bps": 1.5},
    )
    p = e.as_dict()
    assert p["execution_authority"] is False
    assert p["signal_delta"] == pytest.approx(0.2)
    assert p["confidence_delta"] == pytest.approx(0.1)


def test_signal_outside_range_fails_closed():
    with pytest.raises(ValueError):
        ShadowDecisionEvent(
            symbol="BTC/USD",
            strategy="momentum",
            champion_signal=1.2,
            champion_confidence=0.7,
            challenger_signal=0.2,
            challenger_confidence=0.7,
            reference_price=65000.0,
        )


def test_invalid_feature_fails_closed():
    with pytest.raises(ValueError):
        ShadowDecisionEvent(
            symbol="SPY",
            strategy="momentum",
            champion_signal=0.1,
            champion_confidence=0.6,
            challenger_signal=0.2,
            challenger_confidence=0.7,
            reference_price=500.0,
            features={"ofi": float("nan")},
        )
