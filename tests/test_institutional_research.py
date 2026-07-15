import numpy as np

from intelligence.agents import MarketSnapshot
from intelligence.institutional_research import InstitutionalResearchFabric


def snap(symbol, closes, volume=1_000_000):
    prices = np.asarray(closes, dtype=float)
    return MarketSnapshot(symbol, float(prices[-1]), prices,
                          np.full(prices.size, volume, dtype=float))


def test_research_fabric_emits_point_in_time_factor_and_regime_data():
    x = np.arange(260)
    report = InstitutionalResearchFabric().analyze([
        snap("UP", 100*np.exp(.001*x)),
        snap("FLAT", 100 + np.sin(x/8)),
        snap("DOWN", 120*np.exp(-.0007*x)),
    ], as_of="2026-07-15T00:00:00Z")
    assert report["point_in_time"] is True
    assert report["execution_authority"] is False
    assert report["provenance"]["future_data_used"] is False
    assert set(report["factors"]) == {"UP", "FLAT", "DOWN"}
    assert report["factors"]["UP"]["momentum_rank"] > report["factors"]["DOWN"]["momentum_rank"]
    assert abs(sum(report["market"]["regime_probabilities"].values()) - 1) < 1e-5
    assert .5 <= report["market"]["advisory_risk_multiplier"] <= 1


def test_stress_regime_only_reduces_risk():
    rng = np.random.default_rng(7)
    prices = [100*np.exp(np.cumsum(rng.normal(-.002, .06, 260))) for _ in range(4)]
    report = InstitutionalResearchFabric().analyze(
        [snap(f"S{i}", series) for i, series in enumerate(prices)])
    assert report["market"]["stress_score"] > 0
    assert report["market"]["advisory_risk_multiplier"] <= 1


def test_invalid_or_short_data_fails_to_unknown_and_half_risk():
    report = InstitutionalResearchFabric().analyze([snap("SHORT", [1, 2, 3])])
    assert report["market"]["regime"] == "unknown"
    assert report["market"]["advisory_risk_multiplier"] == .5
