from institutional_validation import (
    DEFAULT_POLICY,
    evaluate_portfolio_risk,
    readiness_report,
    reconcile_runtime_and_evidence,
    strategy_promotion_gate,
)


def _runtime(**overrides):
    payload = {
        "fresh": True,
        "age_seconds": 5,
        "read_only": True,
        "execution_authority": False,
        "equity_value": 10000.0,
        "cash": 2500.0,
        "buying_power": 5000.0,
        "positions": [{"symbol": "BTC/USD", "qty": 0.1, "market_value": 7500.0}],
    }
    payload.update(overrides)
    return payload


def _evidence(**overrides):
    payload = {
        "fresh": True,
        "age_seconds": 5,
        "verdict": "RECONCILED",
        "conflict_status": "NONE",
        "execution_authority": False,
        "trading_armed": False,
        "trading_ready": False,
        "mcp": {
            "account": {"equity": 10000.0, "cash": 2500.0, "buying_power": 5000.0},
            "positions": [{"symbol": "BTC/USD", "qty": 0.1, "market_value": 7500.0}],
        },
    }
    payload.update(overrides)
    return payload


def test_missing_runtime_fails_closed():
    report = reconcile_runtime_and_evidence(None, _evidence())
    assert report["reconciled"] is False
    assert report["execution_authority"] is False
    assert "runtime evidence missing" in report["blockers"]


def test_stale_runtime_blocks_reconciliation():
    report = reconcile_runtime_and_evidence(
        _runtime(fresh=False, age_seconds=DEFAULT_POLICY.runtime_max_age_seconds + 1),
        _evidence(),
    )
    assert report["reconciled"] is False
    assert report["checks"]["runtime_fresh"] is False


def test_drift_over_quarter_percent_blocks_reconciliation():
    report = reconcile_runtime_and_evidence(
        _runtime(equity_value=10000.0),
        _evidence(mcp={
            "account": {"equity": 9900.0, "cash": 2500.0, "buying_power": 5000.0},
            "positions": [{"symbol": "BTC/USD", "qty": 0.1, "market_value": 7500.0}],
        }),
    )
    assert report["reconciled"] is False
    assert report["drift"]["max_pct"] > 0.0025


def test_exact_reconciliation_passes_but_never_grants_authority():
    report = reconcile_runtime_and_evidence(_runtime(), _evidence())
    assert report["reconciled"] is True
    assert report["execution_authority"] is False


def test_portfolio_risk_blocks_leverage_and_concentration():
    report = evaluate_portfolio_risk(
        nav=10000,
        gross_exposure=12000,
        largest_position_value=600,
        daily_drawdown_pct=0.01,
        portfolio_drawdown_pct=0.05,
    )
    assert report["passed"] is False
    assert report["checks"]["gross_exposure"] is False
    assert report["checks"]["position_concentration"] is False


def test_strategy_promotion_requires_meaningful_oos_evidence():
    report = strategy_promotion_gate({
        "oos_observations": 999,
        "oos_days": 29,
        "profit_factor": 1.5,
        "net_expectancy": 1.0,
        "max_drawdown_pct": 0.05,
        "costs_included": True,
        "walk_forward_passed": True,
    })
    assert report["promotion_ready"] is False
    assert "minimum_observations" in report["blockers"]
    assert "minimum_days" in report["blockers"]


def test_full_readiness_can_be_true_without_execution_authority():
    report = readiness_report(
        runtime=_runtime(),
        evidence=_evidence(),
        portfolio={
            "nav": 10000,
            "gross_exposure": 8000,
            "largest_position_value": 400,
            "daily_drawdown_pct": 0.01,
            "portfolio_drawdown_pct": 0.05,
        },
        strategy_metrics={
            "oos_observations": 1500,
            "oos_days": 45,
            "profit_factor": 1.3,
            "net_expectancy": 0.25,
            "max_drawdown_pct": 0.07,
            "costs_included": True,
            "walk_forward_passed": True,
        },
    )
    assert report["institutional_10_10"] is True
    assert report["score"] == 100.0
    assert report["execution_authority"] is False
