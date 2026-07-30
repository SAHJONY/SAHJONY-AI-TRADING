"""Regression checks for the institutional strategy-promotion gates.

Run with ``python -m tests.test_strategy_validation``.
"""
from __future__ import annotations

import sys
import json
import os
import tempfile
from pathlib import Path

import numpy as np

from backtest.validation import (
    ValidationPolicy,
    multiple_testing_sharpe_hurdle,
    validate_candidate,
    walk_forward_folds,
)
from scripts import strategy_search
from research.market_data import (
    CoinGeckoHistory,
    MarketDataError,
    _canonical_payload,
    _checksum,
    validate_snapshot,
)

FAILURES = []


def _check(condition: bool, label: str) -> None:
    print(f"  {'✓' if condition else '✗'} {label}")
    if not condition:
        FAILURES.append(label)


def _policy(**overrides):
    values = dict(periods_per_year=252, min_train=120, test_size=40, step=45,
                  purge=5, embargo=5, holdout_fraction=0.20, min_folds=3,
                  min_observations=30, min_positive_fold_fraction=0.67,
                  min_holdout_sharpe=0.50, max_holdout_drawdown=0.15,
                  min_stressed_sharpe=0.0, max_trials=200_000,
                  familywise_alpha=0.05)
    values.update(overrides)
    return ValidationPolicy(**values)


def main() -> int:
    print("\n── reproducible market-data integrity ──")
    timestamps = [1_700_000_000_000 + i * 86_400_000 for i in range(40)]
    rows = [[ts, 100.0 + i] for i, ts in enumerate(timestamps)]
    payload = _canonical_payload("BTC", "bitcoin", 40, rows)
    snapshot = {**payload, "fetched_at": "2026-07-30T00:00:00+00:00",
                "sha256": _checksum(payload)}
    _check(validate_snapshot(snapshot, expected_symbol="BTC",
                             expected_days=40) == rows,
           "valid content-addressed history passes")
    tampered = {**snapshot, "prices": [*rows[:-1], [rows[-1][0], 999.0]]}
    rejected = False
    try:
        validate_snapshot(tampered, expected_symbol="BTC", expected_days=40)
    except MarketDataError:
        rejected = True
    _check(rejected, "checksum mismatch fails closed")
    duplicate = {**snapshot, "prices": [*rows[:-1], rows[-2]]}
    duplicate_payload = _canonical_payload("BTC", "bitcoin", 40,
                                           duplicate["prices"])
    duplicate["sha256"] = _checksum(duplicate_payload)
    rejected = False
    try:
        validate_snapshot(duplicate)
    except MarketDataError:
        rejected = True
    _check(rejected, "duplicate timestamps fail closed")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"coingecko-btc-40d-{snapshot['sha256'][:16]}.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        loaded, meta = CoinGeckoHistory(tmp).load(
            "BTC", "bitcoin", 40, offline=True
        )
        _check(loaded == rows and meta["source"] == "cache",
               "offline replay uses a verified immutable snapshot")
        no_data_rejected = False
        try:
            CoinGeckoHistory(tmp).load("ETH", "ethereum", 40, offline=True)
        except MarketDataError:
            no_data_rejected = True
        _check(no_data_rejected, "missing offline data fails closed")
        saved_demo = os.environ.pop("COINGECKO_API_KEY", None)
        saved_pro = os.environ.pop("COINGECKO_PRO_API_KEY", None)
        no_key_rejected = False
        try:
            CoinGeckoHistory(tmp, api_key=None).load(
                "ETH", "ethereum", 40, offline=False
            )
        except MarketDataError:
            no_key_rejected = True
        finally:
            if saved_demo is not None:
                os.environ["COINGECKO_API_KEY"] = saved_demo
            if saved_pro is not None:
                os.environ["COINGECKO_PRO_API_KEY"] = saved_pro
        _check(no_key_rejected,
               "online download without authentication fails closed")

    print("\n── purged walk-forward construction ──")
    p = _policy()
    folds = walk_forward_folds(500, p)
    _check(len(folds) >= 3, "enough expanding-window folds are produced")
    _check(all(f.test_start - f.train_end == p.purge for f in folds),
           "every fold has the declared purge gap")
    _check(all(a.test_end + p.embargo <= b.test_start
               for a, b in zip(folds, folds[1:])),
           "test windows respect the post-test embargo")
    _check(all(f.test_end <= 400 for f in folds),
           "the final 20% remains untouched")

    print("\n── multiple-testing control ──")
    one = multiple_testing_sharpe_hurdle(1, 100, 252)
    many = multiple_testing_sharpe_hurdle(200_000, 100, 252)
    _check(many > one > 0.0,
           "the Sharpe hurdle rises with the number of searched variants")

    rng = np.random.default_rng(20260730)
    returns = rng.normal(0.0, 0.01, 500)
    verdict = validate_candidate(returns, returns - 0.0005, _policy(),
                                 trials=200_000)
    _check(verdict["research_only"] is True,
           "validation output is permanently marked research-only")
    _check(verdict["promoted"] is False,
           "noise selected from many trials is rejected")
    _check("multiple_testing_adjusted_sharpe" in verdict["failed_checks"],
           "noise fails the adjusted Sharpe gate")

    print("\n── promotion and fail-closed behavior ──")
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0035, 0.004, 500)
    stressed = returns - 0.0002
    benchmark = np.full(500, 0.0001)
    verdict = validate_candidate(
        returns, stressed, _policy(min_holdout_sharpe=0.25),
        trials=10, benchmark_returns=benchmark,
    )
    _check(verdict["promoted"] is True and not verdict["failed_checks"],
           "a stable candidate can pass every declared gate")

    rng = np.random.default_rng(11)
    returns = rng.normal(0.002, 0.004, 500)
    stressed = returns - 0.003
    verdict = validate_candidate(returns, stressed, _policy(), trials=2)
    _check(verdict["promoted"] is False and
           verdict["checks"]["cost_stress"] is False,
           "a candidate that breaks under cost stress is rejected")

    mismatch_rejected = False
    try:
        validate_candidate(np.zeros(500), np.zeros(499), _policy())
    except ValueError:
        mismatch_rejected = True
    _check(mismatch_rejected, "shape mismatch fails closed")

    print("\n── strategy-search integration ──")
    prices = np.linspace(100.0, 250.0, 500)
    strategy_search._init({"BTC": prices})
    cfg = ("mom", 10, False, "BTC", 0.001, False)
    returns = strategy_search.strategy_returns(cfg)
    train, selection_test, selection_end = strategy_search.selection_slices(
        len(returns)
    )
    _check(train.stop == selection_test.start,
           "selection train/test slices are contiguous")
    _check(selection_test.stop == selection_end < len(returns),
           "ranking slices cannot access the final holdout")

    rows = [(cfg, strategy_search.evaluate(cfg))]
    candidates = strategy_search.validate_shortlist(rows, trials=200_000)
    _check(len(candidates) == 1 and candidates[0]["research_only"] is True,
           "search results are permanently research-only")
    _check("eligible_for_shadow" in candidates[0],
           "passing a gate grants shadow eligibility only")
    forbidden = ("broker", "order", "submit", "execute")
    imports = set(strategy_search.__dict__)
    _check(not any(name in imports for name in forbidden),
           "strategy search exposes no broker or order-routing authority")

    print()
    if FAILURES:
        print(f"STRATEGY VALIDATION CHECKS FAILED ✗ ({len(FAILURES)})")
        return 1
    print("STRATEGY VALIDATION CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
