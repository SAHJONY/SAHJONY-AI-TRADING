"""Fail-closed institutional readiness and promotion gates.

This module never grants execution authority. It evaluates whether runtime,
broker reconciliation, portfolio risk, and out-of-sample evidence are strong
enough to *request* a separately controlled live-arming decision.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class InstitutionalPolicy:
    max_broker_drift_pct: float = 0.0025
    max_daily_drawdown_pct: float = 0.02
    hard_daily_drawdown_pct: float = 0.05
    max_portfolio_drawdown_pct: float = 0.10
    max_gross_exposure_multiple: float = 1.0
    max_position_exposure_pct: float = 0.05
    min_oos_observations: int = 1000
    min_oos_days: int = 30
    min_profit_factor: float = 1.20
    min_net_expectancy: float = 0.0
    runtime_max_age_seconds: int = 600
    evidence_max_age_seconds: int = 900


DEFAULT_POLICY = InstitutionalPolicy()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _position_map(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    for row in rows or []:
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        out[symbol] = (_num(row.get("qty")), _num(row.get("market_value")))
    return out


def _relative_drift(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom


def reconcile_runtime_and_evidence(
    runtime: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    policy: InstitutionalPolicy = DEFAULT_POLICY,
) -> Dict[str, Any]:
    """Reconcile hosted runtime totals with broker evidence.

    Returns a fail-closed report. No caller should infer live execution authority
    from this function; `execution_authority` is always False by design.
    """
    blockers: List[str] = []
    checks: Dict[str, bool] = {}

    if not runtime:
        blockers.append("runtime evidence missing")
        runtime = {}
    if not evidence:
        blockers.append("broker evidence missing")
        evidence = {}

    runtime_fresh = bool(runtime.get("fresh")) and _num(runtime.get("age_seconds"), 1e9) <= policy.runtime_max_age_seconds
    evidence_fresh = bool(evidence.get("fresh")) and _num(evidence.get("age_seconds"), 1e9) <= policy.evidence_max_age_seconds
    checks["runtime_fresh"] = runtime_fresh
    checks["broker_evidence_fresh"] = evidence_fresh
    if not runtime_fresh:
        blockers.append("runtime evidence stale or unavailable")
    if not evidence_fresh:
        blockers.append("broker evidence stale or unavailable")

    checks["runtime_read_only"] = runtime.get("read_only") is True and runtime.get("execution_authority") is False
    checks["evidence_fail_closed"] = (
        evidence.get("execution_authority") is False
        and evidence.get("trading_armed") is False
        and evidence.get("trading_ready") is False
    )
    if not checks["runtime_read_only"]:
        blockers.append("runtime safety declaration invalid")
    if not checks["evidence_fail_closed"]:
        blockers.append("broker evidence safety declaration invalid")

    checks["reconciliation_verdict"] = evidence.get("verdict") == "RECONCILED"
    checks["no_source_conflict"] = evidence.get("conflict_status") in (None, "NONE")
    if not checks["reconciliation_verdict"]:
        blockers.append(f"broker verdict is {evidence.get('verdict', 'UNKNOWN')}")
    if not checks["no_source_conflict"]:
        blockers.append("broker evidence source conflict")

    mcp = evidence.get("mcp") if isinstance(evidence.get("mcp"), Mapping) else {}
    account = mcp.get("account") if isinstance(mcp.get("account"), Mapping) else {}

    pairs = {
        "equity": (_num(runtime.get("equity_value")), _num(account.get("equity"))),
        "cash": (_num(runtime.get("cash")), _num(account.get("cash"))),
        "buying_power": (_num(runtime.get("buying_power")), _num(account.get("buying_power"))),
    }
    drifts = {name: _relative_drift(a, b) for name, (a, b) in pairs.items()}

    runtime_positions = _position_map(runtime.get("positions") or [])
    evidence_positions = _position_map(mcp.get("positions") or [])
    all_symbols = sorted(set(runtime_positions) | set(evidence_positions))
    position_drifts: Dict[str, float] = {}
    for symbol in all_symbols:
        rq, rv = runtime_positions.get(symbol, (0.0, 0.0))
        eq, ev = evidence_positions.get(symbol, (0.0, 0.0))
        position_drifts[symbol] = max(_relative_drift(rq, eq), _relative_drift(rv, ev))

    max_account_drift = max(drifts.values(), default=1.0)
    max_position_drift = max(position_drifts.values(), default=0.0)
    max_drift = max(max_account_drift, max_position_drift)
    checks["broker_drift_within_limit"] = max_drift <= policy.max_broker_drift_pct
    if not checks["broker_drift_within_limit"]:
        blockers.append(
            f"broker reconciliation drift {max_drift:.4%} exceeds {policy.max_broker_drift_pct:.4%}"
        )

    return {
        "reconciled": all(checks.values()) and not blockers,
        "checks": checks,
        "drift": {
            "account": drifts,
            "positions": position_drifts,
            "max_pct": max_drift,
            "limit_pct": policy.max_broker_drift_pct,
        },
        "blockers": sorted(set(blockers)),
        "execution_authority": False,
    }


def evaluate_portfolio_risk(
    *,
    nav: float,
    gross_exposure: float,
    largest_position_value: float,
    daily_drawdown_pct: float,
    portfolio_drawdown_pct: float,
    policy: InstitutionalPolicy = DEFAULT_POLICY,
) -> Dict[str, Any]:
    nav = max(_num(nav), 0.0)
    gross = abs(_num(gross_exposure))
    largest = abs(_num(largest_position_value))
    daily_dd = max(_num(daily_drawdown_pct), 0.0)
    portfolio_dd = max(_num(portfolio_drawdown_pct), 0.0)

    gross_multiple = gross / nav if nav > 0 else float("inf")
    position_pct = largest / nav if nav > 0 else float("inf")

    checks = {
        "nav_positive": nav > 0,
        "gross_exposure": gross_multiple <= policy.max_gross_exposure_multiple,
        "position_concentration": position_pct <= policy.max_position_exposure_pct,
        "daily_drawdown": daily_dd <= policy.max_daily_drawdown_pct,
        "hard_daily_drawdown": daily_dd <= policy.hard_daily_drawdown_pct,
        "portfolio_drawdown": portfolio_dd <= policy.max_portfolio_drawdown_pct,
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "gross_exposure_multiple": gross_multiple,
            "largest_position_pct": position_pct,
            "daily_drawdown_pct": daily_dd,
            "portfolio_drawdown_pct": portfolio_dd,
        },
        "blockers": blockers,
        "execution_authority": False,
    }


def strategy_promotion_gate(
    metrics: Mapping[str, Any] | None,
    policy: InstitutionalPolicy = DEFAULT_POLICY,
) -> Dict[str, Any]:
    metrics = metrics or {}
    observations = int(_num(metrics.get("oos_observations")))
    days = int(_num(metrics.get("oos_days")))
    profit_factor = _num(metrics.get("profit_factor"))
    expectancy = _num(metrics.get("net_expectancy"), -1.0)
    max_dd = max(_num(metrics.get("max_drawdown_pct")), 0.0)
    costs_included = metrics.get("costs_included") is True
    walk_forward = metrics.get("walk_forward_passed") is True

    checks = {
        "minimum_observations": observations >= policy.min_oos_observations,
        "minimum_days": days >= policy.min_oos_days,
        "profit_factor": profit_factor >= policy.min_profit_factor,
        "positive_net_expectancy": expectancy > policy.min_net_expectancy,
        "drawdown": max_dd <= policy.max_portfolio_drawdown_pct,
        "costs_included": costs_included,
        "walk_forward": walk_forward,
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "promotion_ready": all(checks.values()),
        "checks": checks,
        "blockers": blockers,
        "execution_authority": False,
    }


def readiness_report(
    *,
    runtime: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    portfolio: Mapping[str, Any] | None = None,
    strategy_metrics: Mapping[str, Any] | None = None,
    policy: InstitutionalPolicy = DEFAULT_POLICY,
) -> Dict[str, Any]:
    reconciliation = reconcile_runtime_and_evidence(runtime, evidence, policy)
    portfolio = portfolio or {}
    risk = evaluate_portfolio_risk(
        nav=_num(portfolio.get("nav")),
        gross_exposure=_num(portfolio.get("gross_exposure")),
        largest_position_value=_num(portfolio.get("largest_position_value")),
        daily_drawdown_pct=_num(portfolio.get("daily_drawdown_pct")),
        portfolio_drawdown_pct=_num(portfolio.get("portfolio_drawdown_pct")),
        policy=policy,
    )
    promotion = strategy_promotion_gate(strategy_metrics, policy)

    gates = {
        "broker_reconciliation": reconciliation["reconciled"],
        "portfolio_risk": risk["passed"],
        "strategy_validation": promotion["promotion_ready"],
    }
    score = round(100.0 * sum(1 for ok in gates.values() if ok) / len(gates), 1)
    blockers = sorted(
        set(reconciliation["blockers"] + risk["blockers"] + promotion["blockers"])
    )
    return {
        "institutional_10_10": all(gates.values()),
        "score": score,
        "gates": gates,
        "blockers": blockers,
        "reconciliation": reconciliation,
        "risk": risk,
        "promotion": promotion,
        "policy": asdict(policy),
        "execution_authority": False,
    }
