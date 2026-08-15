"""Local Monte Carlo summarizer for challenger decisions.

The LLM never receives path-level simulations; only these aggregate statistics.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class MonteCarloSummary:
    paths: int
    horizon_steps: int
    expected_return: float
    median_return: float
    probability_profit: float
    var_95: float
    var_99: float
    cvar_95: float
    worst_return: float

    def to_dict(self) -> dict:
        return asdict(self)


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, int(q * (len(sorted_values) - 1))))
    return sorted_values[idx]


def simulate_returns(
    returns: Iterable[float],
    *,
    paths: int = 10_000,
    horizon_steps: int = 3,
    seed: int = 56,
) -> MonteCarloSummary:
    sample = [float(r) for r in returns if math.isfinite(float(r))]
    if len(sample) < 10:
        raise ValueError("at least 10 finite returns are required")
    paths = max(100, min(1_000_000, int(paths)))
    horizon_steps = max(1, min(1000, int(horizon_steps)))
    rng = random.Random(seed)
    outcomes: list[float] = []
    n = len(sample)
    for _ in range(paths):
        gross = 1.0
        for _step in range(horizon_steps):
            gross *= 1.0 + sample[rng.randrange(n)]
        outcomes.append(gross - 1.0)
    outcomes.sort()
    var95 = _quantile(outcomes, 0.05)
    var99 = _quantile(outcomes, 0.01)
    tail95 = [r for r in outcomes if r <= var95]
    return MonteCarloSummary(
        paths=paths,
        horizon_steps=horizon_steps,
        expected_return=statistics.fmean(outcomes),
        median_return=statistics.median(outcomes),
        probability_profit=sum(1 for r in outcomes if r > 0.0) / paths,
        var_95=var95,
        var_99=var99,
        cvar_95=statistics.fmean(tail95) if tail95 else var95,
        worst_return=outcomes[0],
    )
