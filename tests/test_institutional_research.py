import numpy as np
from datetime import datetime, timedelta, timezone

from intelligence.agents import MarketSnapshot
from intelligence.institutional_research import (
    InstitutionalResearchFabric,
    applied_multiplier,
    multiplier_enabled,
)


def snap(symbol, closes, volume=1_000_000, timestamps=None):
    prices = np.asarray(closes, dtype=float)
    return MarketSnapshot(symbol, float(prices[-1]), prices,
                          np.full(prices.size, volume, dtype=float),
                          bar_timestamps=np.asarray(timestamps or [], dtype=object))


def test_research_fabric_emits_point_in_time_factor_and_regime_data():
    x = np.arange(260)
    dates = [datetime(2025, 10, 28, tzinfo=timezone.utc) + timedelta(days=i)
             for i in range(260)]
    report = InstitutionalResearchFabric().analyze([
        snap("UP", 100*np.exp(.001*x), timestamps=dates),
        snap("FLAT", 100 + np.sin(x/8), timestamps=dates),
        snap("DOWN", 120*np.exp(-.0007*x), timestamps=dates),
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


def test_multiplier_requires_feature_flag_and_canary_promotion():
    assert multiplier_enabled("canary", True) is True
    assert multiplier_enabled("production", True) is True
    assert multiplier_enabled("shadow", True) is False
    assert multiplier_enabled("canary", False) is False
    assert multiplier_enabled("CANARY", True) is True
    assert multiplier_enabled("unknown", True) is False
    assert applied_multiplier(.6, "shadow", True) == 1.0
    assert applied_multiplier(.6, "canary", False) == 1.0
    assert applied_multiplier(.6, "canary", True) == .6
    assert applied_multiplier(float("nan"), "production", True) == 1.0


def test_cross_asset_correlation_uses_only_synchronized_dates():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    crypto_dates = [start + timedelta(days=i) for i in range(80)]
    equity_dates = [stamp for stamp in crypto_dates if stamp.weekday() < 5]
    crypto_prices = 100 * np.exp(np.cumsum(np.sin(np.arange(80)) * .01))
    equity_prices = 100 * np.exp(np.cumsum(np.cos(np.arange(len(equity_dates))) * .01))
    report = InstitutionalResearchFabric().analyze([
        snap("BTC/USD", crypto_prices, timestamps=crypto_dates),
        snap("SPY", equity_prices, timestamps=equity_dates),
    ], as_of="2026-03-22T00:00:00Z")
    assert report["market"]["correlation_pairs"] == 1
    assert report["market"]["minimum_pair_overlap"] == len(equity_dates) - 1


def test_stale_data_rejected_and_coverage_uses_requested_universe():
    old = [datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(30)]
    report = InstitutionalResearchFabric().analyze(
        [snap("STALE", np.arange(30) + 100, timestamps=old)],
        as_of="2026-01-01T00:00:00Z", requested_symbols=["STALE", "MISSING"],
        max_age_seconds=3600, require_timestamps=True,
    )
    assert report["configured_symbols"] == 2
    assert report["successful_symbols"] == 0
    assert report["coverage"] == 0.0
    assert report["rejected_symbols"]["STALE"] == "stale_history"
    assert report["rejected_symbols"]["MISSING"] == "research_unavailable"


def test_malformed_history_is_rejected():
    dates = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(30)]
    prices = np.arange(30, dtype=float) + 100
    prices[10] = np.nan
    report = InstitutionalResearchFabric().analyze(
        [snap("BROKEN", prices, timestamps=dates)], requested_symbols=["BROKEN"])
    assert report["successful_symbols"] == 0
    assert report["rejected_symbols"]["BROKEN"] == "invalid_or_short_history"
