from datetime import datetime, timezone

from intelligence.global_performance import global_performance


NOW = datetime(2026, 7, 14, 20, 0, tzinfo=timezone.utc)


def row(ts, equity, deployed=0):
    return {"ts": ts, "equity": equity, "deployed": deployed}


def test_global_metrics_from_equity_curve():
    rows = [
        row("2026-01-02T15:00:00+00:00", 100.0, 20.0),
        row("2026-07-01T15:00:00+00:00", 105.0, 30.0),
        row("2026-07-14T13:00:00+00:00", 100.0, 40.0),
        row("2026-07-14T16:00:00+00:00", 110.0, 55.0),
    ]
    metrics = global_performance(rows, now=NOW, periods_per_year=252)
    assert metrics["daily"]["pnl"] == 10.0
    assert metrics["monthly"]["pnl"] == 5.0
    assert metrics["ytd"]["pnl"] == 10.0
    assert metrics["sharpe"] is not None
    assert metrics["sortino"] is not None
    assert metrics["max_drawdown"] > 0
    assert metrics["profit_factor"] > 0
    assert metrics["kelly_fraction"] is not None
    assert metrics["exposure"] == 0.5
    assert metrics["return_observations"] == 3


def test_insufficient_evidence_is_explicit():
    metrics = global_performance([row("2026-07-14T16:00:00+00:00", 100.0)], now=NOW)
    assert metrics["daily"]["pnl"] is None
    assert metrics["sharpe"] is None
    assert metrics["sortino"] is None
    assert metrics["profit_factor"] is None
    assert metrics["kelly_fraction"] is None


def test_no_losses_does_not_invent_profit_factor_or_kelly():
    rows = [row("2026-07-14T12:00:00+00:00", 100.0),
            row("2026-07-14T13:00:00+00:00", 101.0),
            row("2026-07-14T14:00:00+00:00", 102.0)]
    metrics = global_performance(rows, now=NOW)
    assert metrics["profit_factor"] is None
    assert metrics["kelly_fraction"] is None
