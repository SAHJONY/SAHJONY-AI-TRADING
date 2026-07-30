"""Institutional strategy-validation primitives.

This module is deliberately isolated from execution and broker packages.  It
turns the promotion policy in ``docs/STRATEGY_PROMOTION_GATES.md`` into
deterministic, testable decisions:

* expanding-window walk-forward folds;
* a purge gap and post-test embargo to reduce temporal leakage;
* a final untouched holdout that is never part of model selection;
* cost-stress, fold-stability and drawdown gates;
* a multiple-testing-adjusted Sharpe hurdle.

The functions consume return arrays only.  They cannot submit orders and do not
change live strategy weights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import NormalDist
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class Fold:
    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass(frozen=True)
class ValidationPolicy:
    periods_per_year: int = 365
    min_train: int = 180
    test_size: int = 60
    step: int = 60
    purge: int = 5
    embargo: int = 5
    holdout_fraction: float = 0.20
    min_folds: int = 3
    min_observations: int = 30
    min_positive_fold_fraction: float = 0.67
    min_holdout_sharpe: float = 0.50
    max_holdout_drawdown: float = 0.15
    min_stressed_sharpe: float = 0.0
    max_trials: int = 200_000
    familywise_alpha: float = 0.05


def walk_forward_folds(n: int, policy: ValidationPolicy) -> list[Fold]:
    """Return expanding-window folds before the untouched final holdout.

    ``train_end``/``test_end`` are exclusive.  The purge sits between train and
    test.  The embargo is skipped after each test before the next test window.
    """
    if n <= 0 or not 0.0 < policy.holdout_fraction < 0.5:
        return []
    selection_end = int(n * (1.0 - policy.holdout_fraction))
    folds: list[Fold] = []
    test_start = policy.min_train + policy.purge
    while test_start + policy.test_size <= selection_end:
        folds.append(Fold(0, test_start - policy.purge,
                          test_start, test_start + policy.test_size))
        test_start += max(policy.step, policy.test_size + policy.embargo)
    return folds


def performance(returns: Sequence[float], periods_per_year: int = 365) -> dict:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return {"n": 0, "return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    dd = float(np.min(equity / peak - 1.0))
    sd = float(r.std(ddof=1)) if r.size > 1 else 0.0
    sharpe = float(r.mean() / sd * sqrt(periods_per_year)) if sd > 1e-12 else 0.0
    return {"n": int(r.size), "return": float(equity[-1] - 1.0),
            "sharpe": sharpe, "max_drawdown": dd}


def multiple_testing_sharpe_hurdle(
    trials: int, observations: int, periods_per_year: int = 365,
    familywise_alpha: float = 0.05,
) -> float:
    """Annualized Sharpe hurdle using a conservative Bonferroni correction.

    This is intentionally stricter than an unadjusted Sharpe > 0 rule.  It
    controls the probability of at least one false winner across the declared
    number of trials under an IID normal null.
    """
    trials = max(1, int(trials))
    observations = max(2, int(observations))
    alpha_per_trial = familywise_alpha / trials
    z = NormalDist().inv_cdf(1.0 - alpha_per_trial)
    return float(z * sqrt(periods_per_year / observations))


def validate_candidate(
    returns: Sequence[float],
    stressed_returns: Sequence[float],
    policy: ValidationPolicy | None = None,
    trials: int = 1,
    benchmark_returns: Sequence[float] | None = None,
) -> dict:
    """Evaluate already-frozen candidate returns and return an auditable verdict.

    Model fitting belongs outside this function.  The caller must supply returns
    produced without look-ahead.  The final holdout is evaluated once and is not
    used to select parameters.
    """
    p = policy or ValidationPolicy()
    r = np.asarray(returns, dtype=float)
    sr = np.asarray(stressed_returns, dtype=float)
    if r.shape != sr.shape:
        raise ValueError("returns and stressed_returns must have the same shape")
    if benchmark_returns is not None and np.asarray(benchmark_returns).shape != r.shape:
        raise ValueError("benchmark_returns must have the same shape as returns")

    folds = walk_forward_folds(len(r), p)
    fold_stats = [performance(r[f.test_start:f.test_end], p.periods_per_year)
                  for f in folds]
    holdout_start = int(len(r) * (1.0 - p.holdout_fraction))
    holdout = performance(r[holdout_start:], p.periods_per_year)
    stressed = performance(sr[holdout_start:], p.periods_per_year)
    benchmark = (performance(np.asarray(benchmark_returns)[holdout_start:],
                             p.periods_per_year)
                 if benchmark_returns is not None else None)
    positive_fraction = (sum(x["return"] > 0.0 for x in fold_stats) / len(fold_stats)
                         if fold_stats else 0.0)
    hurdle = multiple_testing_sharpe_hurdle(
        min(max(1, trials), p.max_trials), holdout["n"], p.periods_per_year,
        p.familywise_alpha,
    )

    checks = {
        "enough_folds": len(folds) >= p.min_folds,
        "enough_holdout_observations": holdout["n"] >= p.min_observations,
        "fold_stability": positive_fraction >= p.min_positive_fold_fraction,
        "holdout_sharpe": holdout["sharpe"] >= p.min_holdout_sharpe,
        "multiple_testing_adjusted_sharpe": holdout["sharpe"] >= hurdle,
        "holdout_drawdown": holdout["max_drawdown"] >= -p.max_holdout_drawdown,
        "cost_stress": stressed["sharpe"] >= p.min_stressed_sharpe,
        "benchmark": (benchmark is None or
                      holdout["return"] > benchmark["return"]),
    }
    return {
        "promoted": all(checks.values()),
        "research_only": True,
        "policy": asdict(p),
        "trials_declared": int(trials),
        "folds": [asdict(f) for f in folds],
        "fold_results": fold_stats,
        "positive_fold_fraction": positive_fraction,
        "holdout_start": holdout_start,
        "holdout": holdout,
        "stressed_holdout": stressed,
        "benchmark_holdout": benchmark,
        "adjusted_sharpe_hurdle": hurdle,
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }
