from intelligence.shadow_eval import ShadowObservation, evaluate_all, score_provider


def obs(provider, ret, adj=0.1, schema=True, latency=100):
    return ShadowObservation(
        ts="2026-07-14T00:00:00Z",
        provider=provider,
        symbol="SPY",
        base_conviction=0.6,
        adjustment=adj,
        risk_multiplier=1.0,
        forward_return=ret,
        turnover_cost_bps=1.0,
        latency_ms=latency,
        schema_valid=schema,
        fallback_used=False,
    )


def test_shadow_report_never_enables_orders():
    rows = [obs("claude", 0.01) for _ in range(120)]
    report = evaluate_all(rows, min_observations=100, min_sharpe=0.0)
    assert report["mode"] == "shadow-only"
    assert report["orders_enabled"] is False
    assert "manual approval" in report["promotion_policy"]


def test_provider_is_blocked_for_insufficient_sample():
    score = score_provider("openai", [obs("openai", 0.01)], min_observations=100)
    assert score.promotion_eligible is False
    assert any("observations" in blocker for blocker in score.blockers)


def test_schema_failures_block_promotion():
    rows = [obs("nvidia", 0.01, schema=(i > 5)) for i in range(120)]
    score = score_provider("nvidia", rows, min_observations=100, min_sharpe=0.0)
    assert score.schema_valid_rate < 0.99
    assert score.promotion_eligible is False
    assert "schema-valid rate below threshold" in score.blockers


def test_adjustments_are_clamped_for_shadow_pnl():
    normal = score_provider("claude", [obs("claude", 0.01, adj=0.15) for _ in range(120)], min_sharpe=0.0)
    extreme = score_provider("openai", [obs("openai", 0.01, adj=99.0) for _ in range(120)], min_sharpe=0.0)
    assert abs(normal.net_return - extreme.net_return) < 1e-12
