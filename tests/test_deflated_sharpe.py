"""Offline checks for the Deflated Sharpe Ratio module (python -m tests.test_deflated_sharpe).

Covers Bailey & López de Prado (2014) "The Deflated Sharpe Ratio":
formula fidelity against hand-computed values, the selection-bias penalty,
the negative-skew penalty, the <30-observation unreliable cutoff, the
import-guarded research-registry trial-count wiring (present/absent), and
the additive-only integration into backtest/validation.py (existing
promotion gates must stay byte-identical).

Fully offline: synthetic return series only, no network, no credentials.
"""
from __future__ import annotations

import json
import math
import os
import sys
import types
from statistics import NormalDist

import numpy as np

from backtest.deflated_sharpe import (
    MIN_OBSERVATIONS,
    deflated_sharpe_enabled,
    deflated_sharpe_report,
    expected_sharpe_under_null,
    probabilistic_sharpe_ratio,
    sample_moments,
)
from backtest.validation import ValidationPolicy, validate_candidate

FAILURES = []


def _check(condition: bool, label: str) -> None:
    print(f"  {'✓' if condition else '✗'} {label}")
    if not condition:
        FAILURES.append(label)


def _rets(n: int = 400, seed: int = 11, mu: float = 0.0012,
          sigma: float = 0.02) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(mu, sigma, n)


def _hand_dsr(r: np.ndarray, trials: int):
    """Independent hand computation of the Bailey-López de Prado DSR.

    Written from the paper's formulas directly (eq. 16 + PSR eq. 17), not by
    calling the module under test, so this is a genuine cross-check.
    """
    n = int(r.size)
    mean = float(r.mean())
    sd = float(r.std(ddof=1))
    sr = mean / sd
    dev = r - mean
    m2 = float((dev ** 2).mean())
    skew = float((dev ** 3).mean()) / (m2 ** 1.5)
    kurt = float((dev ** 4).mean()) / (m2 ** 2)
    g_e = 0.5772156649
    phi = NormalDist()
    if trials < 2:
        sr0 = 0.0
    else:
        e_max = ((1.0 - g_e) * phi.inv_cdf(1.0 - 1.0 / trials)
                 + g_e * phi.inv_cdf(1.0 - 1.0 / (trials * math.e)))
        sr0 = e_max / math.sqrt(n - 1)
    z = ((sr - sr0) * math.sqrt(n - 1)
         / math.sqrt(1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr))
    return phi.cdf(z), sr0, sr, skew, kurt


def _set_env(name: str, value):
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    return old


def main() -> int:
    print("\n── DSR formula vs hand-computed values ──")
    r = _rets(200, seed=7)
    trials = 250
    hand, hand_sr0, hand_sr, hand_skew, hand_kurt = _hand_dsr(r, trials)
    rep = deflated_sharpe_report(r, trials=trials)
    _check(rep["reliable"] is True, "200-observation series is reliable")
    _check(abs(rep["dsr"] - hand) < 1e-12,
           f"dsr matches hand computation ({rep['dsr']:.6f} vs {hand:.6f})")
    _check(abs(rep["expected_sharpe_null"] - hand_sr0) < 1e-12,
           "expected null Sharpe matches hand computation")
    _check(abs(rep["sharpe_per_period"] - hand_sr) < 1e-12,
           "per-period Sharpe matches hand computation")
    _check(abs(rep["skew"] - hand_skew) < 1e-12, "skew matches hand computation")
    _check(abs(rep["kurtosis_raw"] - hand_kurt) < 1e-12,
           "raw kurtosis matches hand computation")
    _check(abs(rep["expected_sharpe_null_annualized"]
               - hand_sr0 * math.sqrt(365)) < 1e-9,
           "annualized null Sharpe is a pure display transform")

    print("\n── selection-bias penalty (more trials → lower DSR) ──")
    r = _rets(300, seed=21)
    d1 = deflated_sharpe_report(r, trials=1)["dsr"]
    d50 = deflated_sharpe_report(r, trials=50)["dsr"]
    d5000 = deflated_sharpe_report(r, trials=5000)["dsr"]
    _check(d1 is not None and d50 is not None and d5000 is not None,
           "dsr defined across trial counts")
    _check(d1 > d50 > d5000, "DSR strictly decreases as trial count rises")
    s1 = expected_sharpe_under_null(1, 300)
    s50 = expected_sharpe_under_null(50, 300)
    s5000 = expected_sharpe_under_null(5000, 300)
    _check(s1 == 0.0, "no selection (N=1) → null benchmark exactly 0")
    _check(0.0 < s50 < s5000, "null benchmark rises with trial count")
    _check(expected_sharpe_under_null(0, 300) == 0.0,
           "degenerate trial count degrades to 0, not garbage")

    print("\n── negative-skew penalty ──")
    # Same Sharpe by construction (matched mean and sample-std), different skew.
    # Sharpe is set ABOVE the null benchmark: for a below-benchmark strategy,
    # wider standard errors push the probability toward 0.5 (correctly); the
    # skew penalty bites when the strategy clears the luck baseline.
    z = np.random.default_rng(42).standard_normal(1000)
    zn = (z - z.mean()) / z.std(ddof=1)
    sym = 0.004 + 0.02 * zn
    w = z - 0.6 * (z ** 2 - 1.0)          # inject negative skew
    wn = (w - w.mean()) / w.std(ddof=1)
    left = 0.004 + 0.02 * wn
    ms, ml = sample_moments(sym), sample_moments(left)
    _check(abs(ms["sharpe_per_period"] - ml["sharpe_per_period"]) < 1e-9,
           "matched series share the same Sharpe")
    _check(ml["skew"] < -0.2 < ms["skew"] and abs(ms["skew"]) < 0.2,
           f"skew differs (sym={ms['skew']:.3f}, left={ml['skew']:.3f})")
    ds, dl = (deflated_sharpe_report(sym, trials=100)["dsr"],
              deflated_sharpe_report(left, trials=100)["dsr"])
    _check(dl < ds, "left-tailed series gets a lower DSR at equal Sharpe")
    # Unit-level: PSR falls as skew turns negative, all else fixed.
    p0 = probabilistic_sharpe_ratio(0.05, 0.0, 200, 0.0, 3.0)
    pneg = probabilistic_sharpe_ratio(0.05, 0.0, 200, -1.5, 3.0)
    _check(p0 is not None and pneg is not None and pneg < p0,
           "PSR penalizes negative skew directly")
    _check(probabilistic_sharpe_ratio(0.0, 0.0, 100, 0.0, 3.0) == 0.5,
           "PSR at the benchmark is exactly 0.5")

    print("\n── insufficient / degenerate observations ──")
    rep20 = deflated_sharpe_report(_rets(20, seed=3), trials=10)
    rep29 = deflated_sharpe_report(_rets(29, seed=3), trials=10)
    rep30 = deflated_sharpe_report(_rets(30, seed=3), trials=10)
    _check(rep20["dsr"] is None and rep20["reliable"] is False,
           "20 observations → dsr None, unreliable")
    _check(rep29["dsr"] is None and rep29["reliable"] is False,
           "29 observations → dsr None, unreliable")
    _check(rep30["dsr"] is not None and rep30["reliable"] is True,
           "30 observations → dsr reported, reliable")
    _check("observations" in (rep20["reason"] or ""),
           "unreliable reason names the observation shortfall")
    flat = deflated_sharpe_report(np.full(100, 0.001), trials=10)
    _check(flat["dsr"] is None and flat["reliable"] is False,
           "zero-variance series → None, never a number")
    empty = deflated_sharpe_report(np.array([]), trials=10)
    _check(empty["dsr"] is None, "empty series → None")
    nan = deflated_sharpe_report(np.full(100, np.nan), trials=10)
    _check(nan["dsr"] is None, "all-NaN series → None, never raises")
    _check(sample_moments(np.full(50, 0.5)) is None,
           "sample_moments returns None on zero variance")

    print("\n── DSR bounded and sane ──")
    strong = deflated_sharpe_report(_rets(500, seed=5, mu=0.004), trials=50)
    weak = deflated_sharpe_report(_rets(500, seed=5, mu=-0.004), trials=50)
    _check(strong["dsr"] is not None and 0.0 <= strong["dsr"] <= 1.0,
           "dsr is a probability in [0, 1]")
    _check(strong["dsr"] > 0.9, "strong positive edge → high DSR")
    _check(weak["dsr"] < 0.1, "negative edge → low DSR")

    print("\n── registry present → honest registry count ──")
    fake = types.ModuleType("intel.research_registry")

    class _FakeRegistry:
        def get_trial_count(self, hid):
            return 777 if hid == "H1" else None

    fake.default_registry = lambda: _FakeRegistry()
    sys.modules["intel.research_registry"] = fake
    try:
        rets = _rets(400, seed=9)
        res = validate_candidate(rets, rets - 0.0005, trials=5,
                                 hypothesis_id="H1")
        _check(res["dsr_trials_used"] == 777,
               "registry count (777) wins over hand-passed 5")
        _check(res["dsr_trials_source"] == "research_registry",
               "source reported as research_registry")
        res_unknown = validate_candidate(rets, rets - 0.0005, trials=5,
                                         hypothesis_id="NOPE")
        _check(res_unknown["dsr_trials_used"] == 5
               and res_unknown["dsr_trials_source"] == "declared",
               "unknown hypothesis id → falls back to declared number")
    finally:
        del sys.modules["intel.research_registry"]

    print("\n── registry absent → hand-passed fallback, never crashes ──")
    sys.modules["intel.research_registry"] = None  # forces ImportError
    try:
        rets = _rets(400, seed=9)
        res = validate_candidate(rets, rets - 0.0005, trials=5,
                                 hypothesis_id="H1")
        _check(res["dsr_trials_used"] == 5,
               "registry missing → hand-passed trials used exactly")
        _check(res["dsr_trials_source"] == "declared",
               "source reported as declared")
        _check(res["dsr"] is not None, "dsr still computed on fallback")
    finally:
        del sys.modules["intel.research_registry"]

    print("\n── additive-only: existing validation outputs unchanged ──")
    # Integration baseline: feat/research-registry merged before this branch,
    # so its six additive keys are part of "old" for the DSR additive check.
    old_keys = {"promoted", "research_only", "policy", "trials_declared",
                "folds", "fold_results", "positive_fold_fraction",
                "holdout_start", "holdout", "stressed_holdout",
                "benchmark_holdout", "adjusted_sharpe_hurdle", "checks",
                "failed_checks",
                "budget_overrun", "hypothesis_id", "trials_consumed",
                "trials_effective", "trials_source", "unregistered_run"}
    new_keys = {"dsr", "dsr_reliable", "dsr_expected_sharpe_null",
                "dsr_expected_sharpe_null_annualized", "dsr_trials_used",
                "dsr_trials_source"}
    rets = _rets(400, seed=13)
    stressed = rets - 0.0005
    market = np.diff(np.concatenate([[100.0], 100.0 * np.cumprod(1 + rets)]))
    market = market / 100.0
    res = validate_candidate(rets, stressed, ValidationPolicy(),
                             trials=12, benchmark_returns=market)
    _check(set(res.keys()) == old_keys | new_keys,
           "result keys = old keys + exactly the six new DSR keys")
    _check(set(res["checks"].keys()) == {
        "enough_folds", "enough_holdout_observations", "fold_stability",
        "holdout_sharpe", "multiple_testing_adjusted_sharpe",
        "holdout_drawdown", "cost_stress", "benchmark"},
        "checks dict untouched: same eight gates, no DSR gate")
    _check(res["promoted"] == all(res["checks"].values()),
           "promoted still derives only from the original checks")
    # Byte-identical behavior under the kill-switch: every pre-existing key
    # must be identical whether DSR computation is on or off.
    old_flag = _set_env("DEFLATED_SHARPE_ENABLED", "1")
    try:
        on = validate_candidate(rets, stressed, ValidationPolicy(), trials=12,
                                benchmark_returns=market)
    finally:
        _set_env("DEFLATED_SHARPE_ENABLED", old_flag)
    old_flag = _set_env("DEFLATED_SHARPE_ENABLED", "0")
    try:
        off = validate_candidate(rets, stressed, ValidationPolicy(), trials=12,
                                 benchmark_returns=market)
        _check(off["dsr"] is None and off["dsr_reliable"] is False,
               "flag off → dsr None, marked unreliable")
    finally:
        _set_env("DEFLATED_SHARPE_ENABLED", old_flag)
    dump = lambda d: json.dumps({k: d[k] for k in sorted(old_keys)},
                                default=str, sort_keys=True)
    _check(dump(on) == dump(off),
           "all pre-existing outputs byte-identical with DSR on vs off")
    _check(dump(res) == dump(on),
           "default-env run matches explicit flag-on run")

    print("\n── config flag wiring ──")
    _check(deflated_sharpe_enabled() is True, "DEFLATED_SHARPE_ENABLED defaults on")
    old_flag = _set_env("DEFLATED_SHARPE_ENABLED", "0")
    try:
        _check(deflated_sharpe_enabled() is False, "env override switches it off")
        rep_off = deflated_sharpe_report(_rets(100, seed=2), trials=10)
        _check(rep_off["dsr"] is None and rep_off["enabled"] is False,
               "report degrades cleanly when disabled")
    finally:
        _set_env("DEFLATED_SHARPE_ENABLED", old_flag)
    from config import load_config
    cfg = load_config()
    _check(cfg.deflated_sharpe_enabled is True, "config.py default True")
    old_flag = _set_env("DEFLATED_SHARPE_ENABLED", "false")
    try:
        _check(load_config().deflated_sharpe_enabled is False,
               "config.py honors env override")
    finally:
        _set_env("DEFLATED_SHARPE_ENABLED", old_flag)

    print("\n── reporter block is fault-isolated ──")
    from workforce.reporter import _deflated_sharpe_block
    block = _deflated_sharpe_block()
    _check(block.get("available") is True, "DSR block available")
    _check(block.get("registry_wired") is True,
           "registry merged → honestly reports wired")
    _check(block.get("trials_source") == "research_registry",
           "dashboard shows registry trial source now that it is merged")

    print()
    if FAILURES:
        print(f"DEFLATED SHARPE CHECKS FAILED ✗ ({len(FAILURES)})")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("DEFLATED SHARPE CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
