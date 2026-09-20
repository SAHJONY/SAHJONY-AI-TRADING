"""Deflated Sharpe Ratio (DSR) — advisory measurement only.

Bailey, D. H., & L\u00f3pez de Prado, M. (2014). "The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting and Non-Normality."
*Journal of Portfolio Management*, 40(5), 94-107.
SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

The DSR corrects an observed Sharpe ratio for BOTH:

1. **Selection bias (multiple testing).**  Picking the best of N tried
   strategies inflates the reported Sharpe even when every strategy is pure
   noise.  The DSR benchmarks the observed Sharpe against the Sharpe you
   would *expect* to see by luck alone after N trials (the expected maximum
   estimated Sharpe under the null), via the closed-form two-quantile
   approximation (paper eq. 16):

       E[max_N] = (1 - \u03b3_E)\u00b7\u03a6\u207b\u00b9(1 - 1/N) + \u03b3_E\u00b7\u03a6\u207b\u00b9(1 - 1/(N\u00b7e))

   with \u03b3_E \u2248 0.5772156649 (Euler-Mascheroni).  A per-period Sharpe estimate
   has variance 1/(T-1) under the iid null, so the expected best-of-N null
   Sharpe is

       SR_0 = E[max_N] / sqrt(T - 1)                          (per-period)

2. **Non-normal returns.**  Crypto returns are fat-tailed and skewed, and a
   plain Sharpe understates the estimation noise.  The DSR is the
   Probabilistic Sharpe Ratio (Bailey & L\u00f3pez de Prado 2012, "The Sharpe
   Ratio Efficient Frontier") of the observed Sharpe against that null
   benchmark, with the Mertens non-normality correction in the standard
   error:

       DSR = \u03a6( (SR_hat - SR_0)\u00b7sqrt(T-1)
                   / sqrt(1 - \u03b3_3\u00b7SR_hat + ((\u03b3_4 - 1)/4)\u00b7SR_hat\u00b2) )

   where SR_hat is the observed *per-period* Sharpe, \u03b3_3 is skewness and
   \u03b3_4 is raw (Pearson) kurtosis (\u03b3_4 = 3 for a normal distribution).
   Negative skew and excess kurtosis widen the denominator, lowering the DSR
   \u2014 exactly the penalty fat-tailed crypto return series deserve.

This makes the DSR strictly more informative than the crude Bonferroni Sharpe
hurdle in ``backtest/validation.py`` (which assumes an IID normal null and
ignores skew/kurtosis entirely).  The Bonferroni gate is left byte-identical;
the DSR is reported *alongside* it as an additive statistic.

HONESTY CONTRACT \u2014 read before relying on the number:

* The DSR needs a decent return history to estimate skew/kurtosis.  With
  fewer than ``MIN_OBSERVATIONS`` (30) observations the higher moments are
  too noisy and the module reports ``dsr=None`` / ``reliable=False``
  instead of a number.  Unknown is reported as unknown, never invented.
* It corrects for the trials you LOGGED (the count passed in), not for
  trials you ran and forgot to log.  Pair it with the research-hypothesis
  registry (``intel/research_registry.py``) for an honest trial count; an
  unlogged experiment is invisible to this statistic.
* With only a trial *count* (not the full distribution of trial Sharpes),
  the null benchmark uses the iid-null estimator variance 1/(T-1).  Under
  the null of zero true Sharpe the higher moments drop out of that variance,
  so this is the correct null scaling; the observed moments still enter
  through the PSR denominator.  Correlated trials would need an
  effective-trial adjustment this module cannot see \u2014 the count is an
  honest floor, never a ceiling.
* The DSR is a *probability* (in [0, 1]) that the true Sharpe is positive
  after both corrections \u2014 a better statistic, not a guarantee.  It never
  feeds a promotion gate, never emits orders, never touches credentials,
  and never changes the risk envelope ($10/order, 12%/position, 70%
  deployed, 10% daily-drawdown halt).

Keyless, offline, deterministic.  All Sharpe math is in per-period units;
annualization is a display transform only.
"""
from __future__ import annotations

import math
import os
from statistics import NormalDist
from typing import Optional, Sequence

import numpy as np

# Euler-Mascheroni constant from the Bailey-L\u00f3pez de Prado two-quantile
# approximation of E[max] over N iid standard normals (paper eq. 16).
EULER_MASCHERONI = 0.5772156649

# Below this many observations the skew/kurtosis estimates are too noisy to
# trust; the DSR degrades to None rather than a misleading number.
MIN_OBSERVATIONS = 30

_phi = NormalDist()


def deflated_sharpe_enabled() -> bool:
    """Kill-switch: DEFLATED_SHARPE_ENABLED (default True)."""
    return os.getenv("DEFLATED_SHARPE_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off")


def expected_sharpe_under_null(trials: int, n_obs: int) -> float:
    """Per-period Sharpe you would expect by luck alone after ``trials`` tries.

    Closed form (paper eq. 16): the two-quantile approximation of the expected
    maximum of N iid standard-normal Sharpe estimates, scaled by the
    per-period estimator's null standard deviation 1/sqrt(T-1).

    With fewer than 2 trials there is no selection, so the null benchmark is
    exactly 0 and the DSR reduces to a plain PSR against zero.
    """
    try:
        n = int(trials)
    except (TypeError, ValueError):
        n = 1
    t = max(2, int(n_obs))
    if n < 2:
        return 0.0
    e_max = ((1.0 - EULER_MASCHERONI) * _phi.inv_cdf(1.0 - 1.0 / n)
             + EULER_MASCHERONI * _phi.inv_cdf(1.0 - 1.0 / (n * math.e)))
    return float(e_max / math.sqrt(t - 1))


def probabilistic_sharpe_ratio(sr_per_period: float, benchmark: float,
                               n_obs: int, skew: float,
                               kurtosis_raw: float) -> Optional[float]:
    """P(true Sharpe > ``benchmark``) with the non-normality correction.

    ``sr_per_period`` must be in per-period (un-annualized) units; ``skew``
    and ``kurtosis_raw`` are the return series' skewness and raw (Pearson)
    kurtosis (\u03b3_4 = 3 for normal).  Returns None (never raises) when the
    inputs are degenerate \u2014 e.g. the Mertens denominator goes non-positive.
    """
    try:
        sr = float(sr_per_period)
        b = float(benchmark)
        g3 = float(skew)
        g4 = float(kurtosis_raw)
        t = int(n_obs)
    except (TypeError, ValueError):
        return None
    if t < 2 or not all(math.isfinite(v) for v in (sr, b, g3, g4)):
        return None
    denom_sq = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr * sr
    if not math.isfinite(denom_sq) or denom_sq <= 0.0:
        return None
    z = (sr - b) * math.sqrt(t - 1) / math.sqrt(denom_sq)
    if not math.isfinite(z):
        return None
    return float(_phi.cdf(z))


def sample_moments(returns: Sequence[float]) -> Optional[dict]:
    """Honest sample moments of a return series.  None when degenerate.

    Skewness/kurtosis are population-moment estimators
    (\u03b3_3 = m_3/m_2^1.5, \u03b3_4 = m_4/m_2^2), the convention the DSR paper's
    formulas assume asymptotically.  Non-finite entries are dropped; an empty
    or zero-variance series yields None (unknown, never invented).
    """
    try:
        r = np.asarray(returns, dtype=float)
    except (TypeError, ValueError):
        return None
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n < 2:
        return None
    sd = float(r.std(ddof=1))
    if not math.isfinite(sd) or sd <= 1e-12:
        return None
    mean = float(r.mean())
    dev = r - mean
    m2 = float((dev ** 2).mean())
    if not math.isfinite(m2) or m2 <= 0.0:
        return None
    m3 = float((dev ** 3).mean())
    m4 = float((dev ** 4).mean())
    skew = m3 / (m2 ** 1.5)
    kurt = m4 / (m2 ** 2)
    if not (math.isfinite(skew) and math.isfinite(kurt)):
        return None
    return {"n": n, "mean": mean, "sd": sd,
            "sharpe_per_period": mean / sd,
            "skew": skew, "kurtosis_raw": kurt}


def deflated_sharpe_report(returns: Sequence[float], trials: int,
                           periods_per_year: int = 365,
                           min_observations: int = MIN_OBSERVATIONS) -> dict:
    """Full DSR report for one return series.  Never raises.

    Returns a dict with ``dsr`` (probability in [0, 1], or None when
    unreliable), the null benchmark ``expected_sharpe_null`` (per-period and
    annualized), the trial count used, the observed moments, and a
    ``reliable`` flag with a ``reason`` when False.  Degenerate input
    (too few observations, zero variance, disabled flag) degrades to a
    marked-down report \u2014 never an invented number, never an exception.
    """
    report = {
        "dsr": None,
        "reliable": False,
        "reason": None,
        "expected_sharpe_null": None,
        "expected_sharpe_null_annualized": None,
        "sharpe_per_period": None,
        "sharpe_annualized": None,
        "skew": None,
        "kurtosis_raw": None,
        "n_obs": 0,
        "trials": max(1, int(trials)) if trials is not None else 1,
        "enabled": deflated_sharpe_enabled(),
    }
    try:
        if not report["enabled"]:
            report["reason"] = "disabled via DEFLATED_SHARPE_ENABLED=0"
            return report
        moments = sample_moments(returns)
        if moments is None:
            report["reason"] = "degenerate return series (empty/zero-variance)"
            return report
        report["n_obs"] = moments["n"]
        report["sharpe_per_period"] = moments["sharpe_per_period"]
        report["sharpe_annualized"] = (moments["sharpe_per_period"]
                                       * math.sqrt(periods_per_year))
        report["skew"] = moments["skew"]
        report["kurtosis_raw"] = moments["kurtosis_raw"]
        if moments["n"] < max(2, int(min_observations)):
            report["reason"] = (
                f"only {moments['n']} observations "
                f"(< {min_observations}); skew/kurtosis estimates unreliable")
            return report
        sr0 = expected_sharpe_under_null(report["trials"], moments["n"])
        report["expected_sharpe_null"] = sr0
        report["expected_sharpe_null_annualized"] = sr0 * math.sqrt(periods_per_year)
        dsr = probabilistic_sharpe_ratio(
            moments["sharpe_per_period"], sr0, moments["n"],
            moments["skew"], moments["kurtosis_raw"])
        if dsr is None:
            report["reason"] = "degenerate PSR inputs (non-positive variance term)"
            return report
        report["dsr"] = dsr
        report["reliable"] = True
        return report
    except Exception as exc:  # fault-isolated: degrade, never raise
        report["reason"] = f"computation failed ({type(exc).__name__})"
        report["dsr"] = None
        report["reliable"] = False
        return report
