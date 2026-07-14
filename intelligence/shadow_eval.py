"""Provider-neutral shadow evaluation for AI advisory overlays.

This module evaluates Claude, OpenAI, NVIDIA and a neutral baseline on the same
resolved market outcomes. It never places orders and never changes live weights.
Promotion decisions are evidence-based and fail closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ShadowObservation:
    ts: str
    provider: str
    symbol: str
    base_conviction: float
    adjustment: float
    risk_multiplier: float
    forward_return: float
    turnover_cost_bps: float = 0.0
    latency_ms: float = 0.0
    schema_valid: bool = True
    fallback_used: bool = False


@dataclass(frozen=True)
class ProviderScore:
    provider: str
    observations: int
    net_return: float
    annualized_sharpe: float
    max_drawdown: float
    hit_rate: float
    calibration_error: float
    average_turnover_cost_bps: float
    average_latency_ms: float
    schema_valid_rate: float
    fallback_rate: float
    promotion_eligible: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["blockers"] = list(self.blockers)
        return d


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _max_drawdown(returns: Sequence[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, equity / peak - 1.0)
    return abs(worst)


def _signal_return(obs: ShadowObservation) -> float:
    """Translate a bounded advisory overlay into a shadow P&L contribution.

    The evaluator intentionally uses the same deterministic council direction and
    only measures the incremental effect of the provider's bounded adjustment.
    """
    adj = _clamp(obs.adjustment, -0.15, 0.15)
    risk = _clamp(obs.risk_multiplier, 0.5, 1.2)
    gross = adj * risk * float(obs.forward_return)
    cost = abs(adj) * max(0.0, float(obs.turnover_cost_bps)) / 10_000.0
    return gross - cost


def score_provider(
    provider: str,
    observations: Iterable[ShadowObservation],
    *,
    periods_per_year: int = 252,
    min_observations: int = 100,
    min_schema_valid_rate: float = 0.99,
    max_drawdown: float = 0.10,
    min_sharpe: float = 0.25,
) -> ProviderScore:
    rows = [o for o in observations if o.provider == provider]
    returns = [_signal_return(o) for o in rows]
    n = len(rows)
    avg = mean(returns) if returns else 0.0
    vol = pstdev(returns) if len(returns) > 1 else 0.0
    sharpe = (avg / vol * sqrt(periods_per_year)) if vol > 0 else 0.0
    net = 1.0
    for r in returns:
        net *= 1.0 + r
    net -= 1.0
    hit = mean([1.0 if r > 0 else 0.0 for r in returns]) if returns else 0.0

    # Calibration: conviction should align with realized positive outcomes.
    calibration = mean([
        abs(_clamp(o.base_conviction + o.adjustment, 0.0, 1.0) - (1.0 if o.forward_return > 0 else 0.0))
        for o in rows
    ]) if rows else 1.0
    schema_rate = mean([1.0 if o.schema_valid else 0.0 for o in rows]) if rows else 0.0
    fallback_rate = mean([1.0 if o.fallback_used else 0.0 for o in rows]) if rows else 0.0
    dd = _max_drawdown(returns)

    blockers: list[str] = []
    if n < min_observations:
        blockers.append(f"requires at least {min_observations} observations")
    if schema_rate < min_schema_valid_rate:
        blockers.append("schema-valid rate below threshold")
    if dd > max_drawdown:
        blockers.append("shadow drawdown exceeds threshold")
    if sharpe < min_sharpe:
        blockers.append("incremental Sharpe below threshold")
    if net <= 0:
        blockers.append("net shadow contribution is non-positive")

    return ProviderScore(
        provider=provider,
        observations=n,
        net_return=round(net, 8),
        annualized_sharpe=round(sharpe, 4),
        max_drawdown=round(dd, 6),
        hit_rate=round(hit, 4),
        calibration_error=round(calibration, 4),
        average_turnover_cost_bps=round(mean([o.turnover_cost_bps for o in rows]), 3) if rows else 0.0,
        average_latency_ms=round(mean([o.latency_ms for o in rows]), 2) if rows else 0.0,
        schema_valid_rate=round(schema_rate, 4),
        fallback_rate=round(fallback_rate, 4),
        promotion_eligible=not blockers,
        blockers=tuple(blockers),
    )


def evaluate_all(
    observations: Iterable[ShadowObservation],
    *,
    providers: Sequence[str] = ("claude", "openai", "nvidia", "neutral"),
    **thresholds,
) -> dict:
    rows = list(observations)
    scores = [score_provider(p, rows, **thresholds) for p in providers]
    ranked = sorted(scores, key=lambda s: (s.promotion_eligible, s.annualized_sharpe, s.net_return), reverse=True)
    return {
        "mode": "shadow-only",
        "orders_enabled": False,
        "providers": [s.to_dict() for s in ranked],
        "recommended_provider": ranked[0].provider if ranked and ranked[0].promotion_eligible else None,
        "promotion_policy": "manual approval required; shadow evidence cannot arm live trading",
    }


def observations_from_dicts(rows: Iterable[Mapping]) -> list[ShadowObservation]:
    return [ShadowObservation(**dict(row)) for row in rows]
