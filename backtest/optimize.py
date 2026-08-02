"""Self-improvement layer: parameter search with the controls that make it honest.

Automated search over strategy parameters is trivial to write and almost always
produces a beautiful, worthless equity curve. Everything expensive in this module
exists to make the search *refuse* results rather than to find them:

  • **Walk-forward** — parameters are chosen on a training window and scored only
    on the window after it. In-sample performance is never reported as a result.
  • **PBO (probability of backtest overfitting)** via combinatorially symmetric
    cross-validation, after Bailey, Borwein, López de Prado & Zhu. Answers: if I
    pick the best parameters in-sample, how often do they land below median
    out-of-sample? A PBO near 0.5 means the search learned noise.
  • **Deflated Sharpe Ratio** — a Sharpe of 2.0 found after 500 trials is not the
    same evidence as a Sharpe of 2.0 from one. DSR discounts for the number of
    trials, and for skew and kurtosis of the return distribution.
  • **Parameter stability** — an optimum surrounded by bad neighbours is a spike
    in a noise surface. A real edge is a plateau, so neighbours are checked.
  • **Minimum trade count** — enforced as a hard floor, not a preference.

The promotion gate defaults to FAIL and requires every check to pass. Nothing
here writes to a live configuration: it emits a reviewable JSON proposal. A
trading system that silently re-tunes itself in production is not a
self-improving system, it is an unsupervised one.
"""
from __future__ import annotations

import itertools
import json
import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from backtest.data import Bars
from backtest.engine import Backtester, CostModel, RiskConfig, Strategy


# ── normal distribution helpers (no scipy dependency) ─────────────────────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Acklam's rational approximation to the inverse normal CDF."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# ── search space ──────────────────────────────────────────────────────────────
def build_grid(space: Dict[str, Sequence], max_combos: int = 400,
               seed: int = 0) -> List[Dict]:
    """Full factorial, randomly subsampled if it would be larger than max_combos.

    Subsampling is not a shortcut — every extra trial inflates the best observed
    Sharpe under the null, and `deflated_sharpe` charges for all of them.
    """
    keys = sorted(space)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(space[k] for k in keys))]
    if len(combos) > max_combos:
        random.Random(seed).shuffle(combos)
        combos = combos[:max_combos]
    return combos


# ── objective ─────────────────────────────────────────────────────────────────
@dataclass
class Objective:
    """Scores a run. t-statistic of per-trade R, with a hard trade-count floor.

    Total return is deliberately not the objective: it rewards a single lucky
    trade. The t-stat rewards consistency and is what the significance tests
    downstream actually operate on.
    """
    min_trades: int = 30
    metric: str = "tstat"          # tstat | expectancy | sharpe

    def __call__(self, trades) -> float:
        n = len(trades)
        if n < self.min_trades:
            return -math.inf
        r = np.array([t.r for t in trades], dtype=float)
        sd = r.std(ddof=1) if n > 1 else 0.0
        if sd <= 0:
            return -math.inf
        if self.metric == "expectancy":
            return float(r.mean())
        if self.metric == "sharpe":
            return float(r.mean() / sd)
        return float(r.mean() / sd * math.sqrt(n))


# ── running one parameter set ─────────────────────────────────────────────────
def run_params(bars: Bars, cls, params: Dict, costs: CostModel,
               risk: RiskConfig, entry_mode: str = "spec"):
    strat: Strategy = cls(**params)
    return Backtester(bars, costs, risk, entry_mode=entry_mode).run(strat)


# ── walk-forward ──────────────────────────────────────────────────────────────
@dataclass
class Fold:
    train: Tuple[int, int]
    test: Tuple[int, int]
    best_params: Dict = field(default_factory=dict)
    is_score: float = 0.0
    oos_trades: int = 0
    oos_expectancy_r: float = 0.0
    oos_total_r: float = 0.0


def walk_forward(bars: Bars, cls, space: Dict[str, Sequence], *,
                 folds: int = 4, mode: str = "anchored",
                 costs: Optional[CostModel] = None, risk: Optional[RiskConfig] = None,
                 objective: Optional[Objective] = None, max_combos: int = 400,
                 entry_mode: str = "spec", seed: int = 0) -> Dict:
    """Fit on each training window, score only on the window that follows it.

    `mode`: "anchored" (expanding train) or "rolling" (fixed-length train).
    Returns per-fold detail plus the concatenated out-of-sample trade record —
    which is the only performance number in this module worth reading.
    """
    costs = costs or CostModel()
    risk = risk or RiskConfig()
    objective = objective or Objective()
    combos = build_grid(space, max_combos=max_combos, seed=seed)
    n = len(bars)
    warm = cls.warmup
    seg = n // (folds + 1)
    if seg <= warm * 2:
        raise ValueError(
            f"{cls.id}: {n} bars over {folds} folds leaves {seg} per window, but "
            f"warmup is {warm}. Use more data or fewer folds.")

    out_folds: List[Fold] = []
    oos_trades = []
    for k in range(folds):
        tr_start = 0 if mode == "anchored" else k * seg
        tr_end = (k + 1) * seg
        te_start, te_end = tr_end, min((k + 2) * seg, n)
        train = bars.slice(tr_start, tr_end)
        test = bars.slice(te_start, te_end)

        best, best_score = None, -math.inf
        for params in combos:
            res = run_params(train, cls, params, costs, risk, entry_mode)
            sc = objective(res["trades"])
            if sc > best_score:
                best, best_score = params, sc
        f = Fold(train=(tr_start, tr_end), test=(te_start, te_end),
                 best_params=dict(best or {}), is_score=float(best_score))
        if best is not None and math.isfinite(best_score):
            res = run_params(test, cls, best, costs, risk, entry_mode)
            tr = res["trades"]
            oos_trades.extend(tr)
            f.oos_trades = len(tr)
            if tr:
                rs = np.array([t.r for t in tr])
                f.oos_expectancy_r = round(float(rs.mean()), 4)
                f.oos_total_r = round(float(rs.sum()), 3)
        out_folds.append(f)

    return {"strategy": cls.id, "mode": mode, "folds": out_folds,
            "combos_tried": len(combos), "oos_trades": oos_trades,
            "param_drift": _param_drift(out_folds)}


def _param_drift(folds: List[Fold]) -> Dict[str, float]:
    """How much the chosen parameters move between folds.

    A parameter that lands somewhere different every fold is being fitted to
    noise, whatever the out-of-sample number says.
    """
    keys = sorted({k for f in folds for k in f.best_params})
    drift = {}
    for k in keys:
        vals = [f.best_params.get(k) for f in folds if k in f.best_params]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if len(nums) > 1 and max(abs(v) for v in nums) > 0:
            drift[k] = round(float(np.std(nums) / (abs(np.mean(nums)) + 1e-12)), 4)
        else:
            drift[k] = 0.0 if len(set(map(str, vals))) == 1 else 1.0
    return drift


# ── CSCV / probability of backtest overfitting ────────────────────────────────
def block_performance(bars: Bars, cls, combos: List[Dict], *, blocks: int = 8,
                      costs: Optional[CostModel] = None,
                      risk: Optional[RiskConfig] = None,
                      entry_mode: str = "spec") -> Tuple[np.ndarray, np.ndarray]:
    """Per-parameter-set × per-time-block mean R. The input matrix for CSCV."""
    costs = costs or CostModel()
    risk = risk or RiskConfig()
    n = len(bars)
    edges = [int(round(i * n / blocks)) for i in range(blocks + 1)]
    M = np.zeros((len(combos), blocks))
    counts = np.zeros((len(combos), blocks))
    for i, params in enumerate(combos):
        res = run_params(bars, cls, params, costs, risk, entry_mode)
        ts = np.array([t.entry_ts for t in res["trades"]])
        rs = np.array([t.r for t in res["trades"]])
        if ts.size == 0:
            continue
        pos = np.searchsorted(bars.ts, ts)
        for j in range(blocks):
            m = (pos >= edges[j]) & (pos < edges[j + 1])
            counts[i, j] = m.sum()
            M[i, j] = rs[m].mean() if m.any() else 0.0
    return M, counts


def pbo(M: np.ndarray, max_splits: int = 200, seed: int = 0) -> Dict:
    """Combinatorially symmetric cross-validation → probability of overfitting.

    For every way of splitting the time blocks into an in-sample half and an
    out-of-sample half, take the parameter set that won in-sample and record
    where it ranks out-of-sample. If winners are genuinely better, they rank
    high; if the search fitted noise, they land around the middle.
    """
    n_combos, S = M.shape
    if n_combos < 2 or S < 4 or S % 2:
        return {"pbo": None, "note": "need >=2 parameter sets and an even S>=4"}
    halves = list(itertools.combinations(range(S), S // 2))
    if len(halves) > max_splits:
        halves = random.Random(seed).sample(halves, max_splits)
    logits, below = [], 0
    for h in halves:
        is_cols = list(h)
        oos_cols = [c for c in range(S) if c not in h]
        is_perf = M[:, is_cols].mean(axis=1)
        oos_perf = M[:, oos_cols].mean(axis=1)
        star = int(np.argmax(is_perf))
        # relative rank of the in-sample winner within the OOS distribution
        rank = float((oos_perf <= oos_perf[star]).sum()) / n_combos
        rank = min(max(rank, 1.0 / (n_combos + 1)), 1 - 1.0 / (n_combos + 1))
        logits.append(math.log(rank / (1 - rank)))
        below += 1 if rank <= 0.5 else 0
    return {"pbo": round(below / len(halves), 4),
            "median_logit": round(float(np.median(logits)), 4),
            "splits": len(halves)}


# ── deflated Sharpe ───────────────────────────────────────────────────────────
def deflated_sharpe(returns: np.ndarray, n_trials: int,
                    trial_sr_std: Optional[float] = None) -> Dict:
    """Probability the observed Sharpe would not arise from `n_trials` of luck.

    Reported as a probability in [0, 1]; the promotion gate wants ≥ 0.95.
    """
    n = returns.size
    if n < 20:
        return {"dsr": None, "note": f"only {n} observations"}
    sd = returns.std(ddof=1)
    if sd <= 0:
        return {"dsr": None, "note": "zero variance"}
    sr = returns.mean() / sd
    g1 = float(((returns - returns.mean()) ** 3).mean() / sd ** 3)          # skew
    g2 = float(((returns - returns.mean()) ** 4).mean() / sd ** 4)          # kurtosis
    if trial_sr_std is None or not np.isfinite(trial_sr_std) or trial_sr_std <= 0:
        trial_sr_std = abs(sr) / math.sqrt(max(n, 2)) or 1e-6
    e = math.e
    N = max(n_trials, 2)
    sr0 = trial_sr_std * ((1 - np.euler_gamma) * _norm_ppf(1 - 1.0 / N)
                          + np.euler_gamma * _norm_ppf(1 - 1.0 / (N * e)))
    denom = math.sqrt(max(1e-12, 1 - g1 * sr + (g2 - 1) / 4.0 * sr ** 2))
    z = (sr - sr0) * math.sqrt(max(n - 1, 1)) / denom
    return {"dsr": round(_norm_cdf(z), 4), "sharpe_per_trade": round(float(sr), 4),
            "sr0_threshold": round(float(sr0), 4), "skew": round(g1, 3),
            "kurtosis": round(g2, 3), "n_trials": N, "n_obs": int(n)}


# ── parameter stability ───────────────────────────────────────────────────────
def stability(space: Dict[str, Sequence], scores: Dict[str, float],
              best: Dict) -> Dict:
    """Is the optimum a plateau or a spike?

    Compares the winner against grid neighbours that differ in exactly one
    parameter by one step. A real edge degrades gracefully.
    """
    keys = sorted(space)
    best_key = json.dumps(best, sort_keys=True, default=str)
    best_score = scores.get(best_key)
    if best_score is None or not math.isfinite(best_score):
        return {"stability": None, "note": "winner has no finite score"}
    neighbours = []
    for k in keys:
        vals = list(space[k])
        if best.get(k) not in vals:
            continue
        i = vals.index(best[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                cand = dict(best)
                cand[k] = vals[j]
                sc = scores.get(json.dumps(cand, sort_keys=True, default=str))
                if sc is not None and math.isfinite(sc):
                    neighbours.append(sc)
    if not neighbours:
        return {"stability": None, "note": "no evaluated neighbours"}
    ratio = float(np.mean(neighbours) / best_score) if best_score > 0 else 0.0
    return {"stability": round(ratio, 4), "neighbours": len(neighbours),
            "best_score": round(best_score, 4),
            "mean_neighbour_score": round(float(np.mean(neighbours)), 4)}


# ── promotion gate ────────────────────────────────────────────────────────────
@dataclass
class PromotionCriteria:
    min_oos_trades: int = 300          # the playbook's own floor
    min_oos_expectancy_r: float = 0.0
    max_pbo: float = 0.35
    min_dsr: float = 0.95
    min_stability: float = 0.60        # neighbours ≥ 60% of the winner's score
    max_param_drift: float = 0.50      # cross-fold CV of each chosen parameter
    min_positive_folds: float = 0.60   # fraction of folds with OOS expectancy > 0


def promote(wf: Dict, pbo_res: Dict, dsr_res: Dict, stab: Dict,
            crit: Optional[PromotionCriteria] = None) -> Dict:
    """Decide whether a parameter set has earned live size. Defaults to FAIL.

    Returns every check with its verdict, so a rejection explains itself.
    """
    crit = crit or PromotionCriteria()
    tr = wf.get("oos_trades", [])
    r = np.array([t.r for t in tr], dtype=float) if tr else np.array([])
    exp_r = float(r.mean()) if r.size else 0.0
    folds = wf.get("folds", [])
    pos_folds = (sum(1 for f in folds if f.oos_expectancy_r > 0) / len(folds)
                 if folds else 0.0)
    drift = wf.get("param_drift", {})
    worst_drift = max(drift.values()) if drift else 0.0

    checks = [
        ("oos_trades", len(tr), f">= {crit.min_oos_trades}",
         len(tr) >= crit.min_oos_trades),
        ("oos_expectancy_r", round(exp_r, 4), f"> {crit.min_oos_expectancy_r}",
         exp_r > crit.min_oos_expectancy_r),
        ("pbo", pbo_res.get("pbo"), f"<= {crit.max_pbo}",
         pbo_res.get("pbo") is not None and pbo_res["pbo"] <= crit.max_pbo),
        ("deflated_sharpe", dsr_res.get("dsr"), f">= {crit.min_dsr}",
         dsr_res.get("dsr") is not None and dsr_res["dsr"] >= crit.min_dsr),
        ("param_stability", stab.get("stability"), f">= {crit.min_stability}",
         stab.get("stability") is not None and stab["stability"] >= crit.min_stability),
        ("param_drift", round(worst_drift, 4), f"<= {crit.max_param_drift}",
         worst_drift <= crit.max_param_drift),
        ("positive_folds", round(pos_folds, 3), f">= {crit.min_positive_folds}",
         pos_folds >= crit.min_positive_folds),
    ]
    failed = [c[0] for c in checks if not c[3]]
    return {
        "strategy": wf.get("strategy"),
        "promoted": not failed,
        "failed_checks": failed,
        "checks": [{"name": n, "value": v, "requirement": req, "pass": ok}
                   for n, v, req, ok in checks],
        "proposed_params": folds[-1].best_params if folds else {},
        "note": ("PROPOSAL ONLY — not applied to any live configuration. "
                 "Requires human review before use."),
    }
