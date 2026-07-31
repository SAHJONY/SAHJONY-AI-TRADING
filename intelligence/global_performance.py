"""Honest global performance metrics from the persisted equity curve."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any, Dict


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _window(rows: list[Dict[str, Any]], cutoff: datetime) -> Dict[str, Any]:
    selected = [row for row in rows if (_timestamp(row.get("ts")) or datetime.min.replace(
        tzinfo=timezone.utc)) >= cutoff]
    if len(selected) < 2:
        return {"pnl": None, "return_pct": None, "observations": len(selected)}
    start = float(selected[0].get("equity", 0.0) or 0.0)
    end = float(selected[-1].get("equity", 0.0) or 0.0)
    if start <= 0:
        return {"pnl": None, "return_pct": None, "observations": len(selected)}
    return {"pnl": round(end - start, 2), "return_pct": round(end / start - 1.0, 6),
            "observations": len(selected)}


def global_performance(rows: list[Dict[str, Any]], *, now: datetime | None = None,
                       periods_per_year: int = 252 * 26) -> Dict[str, Any]:
    clean = [row for row in rows if float(row.get("equity", 0.0) or 0.0) > 0]
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    daily_cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ytd_cutoff = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    returns = []
    for previous, current in zip(clean, clean[1:]):
        before = float(previous.get("equity", 0.0) or 0.0)
        after = float(current.get("equity", 0.0) or 0.0)
        if before > 0:
            value = after / before - 1.0
            if math.isfinite(value):
                returns.append(value)
    avg = mean(returns) if returns else 0.0
    volatility = pstdev(returns) if len(returns) > 1 else 0.0
    downside = [min(value, 0.0) for value in returns]
    downside_deviation = math.sqrt(mean([value * value for value in downside])) if downside else 0.0
    annualizer = math.sqrt(max(1, periods_per_year))
    sharpe = avg / volatility * annualizer if volatility > 1e-12 else None
    sortino = avg / downside_deviation * annualizer if downside_deviation > 1e-12 else None
    equity = peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
    gains = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    profit_factor = sum(gains) / abs(sum(losses)) if losses else None
    kelly = None
    if gains and losses:
        win_rate = len(gains) / len(returns)
        payoff = mean(gains) / abs(mean(losses))
        if payoff > 0:
            kelly = max(-1.0, min(1.0, win_rate - (1.0 - win_rate) / payoff))
    latest = clean[-1] if clean else {}
    latest_equity = float(latest.get("equity", 0.0) or 0.0)
    exposure = (float(latest.get("deployed", 0.0) or 0.0) / latest_equity
                if latest_equity > 0 else None)
    return {
        "daily": _window(clean, daily_cutoff),
        "weekly": _window(clean, now - timedelta(days=7)),
        "monthly": _window(clean, now - timedelta(days=30)),
        "ytd": _window(clean, ytd_cutoff),
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "sortino": round(sortino, 3) if sortino is not None else None,
        "max_drawdown": round(abs(max_drawdown), 6),
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "kelly_fraction": round(kelly, 4) if kelly is not None else None,
        "exposure": round(exposure, 6) if exposure is not None else None,
        "return_observations": len(returns),
    }
