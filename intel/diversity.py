"""Council + portfolio diversity diagnostics (advisory/measurement ONLY).

The key insight: intel/dispersion.py measures whether the 12 council personas
DISAGREE on this cycle — not whether they are INDEPENDENT bets. Twelve personas
reading the same momentum signal will agree with each other (no disagreement
haircut triggers) while still representing one crowded bet. This module diagnoses
that crowding; it never changes votes, weights, or gates.

What it computes per cycle:

1. Bias–variance–covariance decomposition of the 12 persona votes. For the
   council mean vote m_t = (1/M) * sum_i v_{i,t}, its variance decomposes as

       Var(m) = (1/M) * avg_i Var(v_i) + ((M-1)/M) * avg_{i!=j} Cov(v_i, v_j)

   The *covariance share* is the second term's fraction of the total. A share
   near 1 means the council is one crowded bet — the personas differ in name
   only. (This is the ambiguity/covariance decomposition of an ensemble mean.)

2. Effective Number of Bets on the portfolio book. Following Attilio Meucci's
   formulation ("Effective Number of Bets", Risk 22(9), 2009), the number of
   independent bets in the book is

       ENB = (sum_i w_i sigma_i)^2 / (w' Sigma w)

   where w are position weights, sigma_i are per-asset volatilities and Sigma
   is the covariance matrix. ENB = N when positions are uncorrelated, ENB -> 1
   when the book is fully correlated. This diagnoses crowding; it does not fix
   it, and it never flows into any gate (the Risk Officer may READ the number;
   nothing writes it back into risk logic).

3. A per-cycle diversity report: the decayed pairwise vote-correlation matrix
   of the 12 personas (exponential decay like council_calibration.py), the
   covariance-share ratio, effective bets vs nominal positions, and a
   plain-language flag when the council or the book is highly correlated.

Hard safety rules: advisory/measurement only — never emits orders, never
touches credentials, never promises profit, never alters any vote, weight, or
gate. Every public function is fault-isolated: unknown/invalid input degrades
to status "insufficient"/"error" with failures recorded in the report dict;
nothing raises.

Honest limits (read before acting on these numbers):
- Vote correlations are estimated from a SHORT, exponentially-decayed window
  (~30 cycles of history, weight 0.97/cycle). With few observations the
  matrix is noisy; the report always shows the effective observation count.
- Effective bets inherits the quality of the return-correlation estimate
  (asset returns, not votes). Few overlapping price bars => wide error bars;
  the report says "insufficient" rather than inventing a number.
- This diagnoses crowding. It does not fix it, predict returns, or imply any
  future profitability — diversified and concentrated books both lose money.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from utils.logger import get_logger

log = get_logger("diversity")

_DECAY = 0.97        # vote-history decay per cycle (matches council_calibration)
_MIN_OBS = 3        # cycles before a vote-correlation matrix is reported
_MAX_SYMBOLS = 40   # bound stored history
_MIN_W = 1e-3       # drop history entries decayed below this
_CROWD_COV_SHARE = 0.70   # covariance share at/above => crowded council
_CROWD_ENB_FRAC = 0.5     # effective bets <= this * nominal => crowded book
_HIGH_CORR = 0.80   # pairwise vote corr threshold for the plain-language flag


# ── small helpers ────────────────────────────────────────────────────────────
def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _arr(x: Any) -> np.ndarray:
    try:
        a = np.asarray(x, dtype=float).ravel()
    except (TypeError, ValueError):
        return np.array([])
    return a


def _names(verdicts: List[Any]) -> List[str]:
    return [str(getattr(v, "name", "?")) for v in verdicts or []]


# ── 1) decayed vote history ──────────────────────────────────────────────────
def record_votes(state: Dict[str, Any], symbol: str,
                 verdicts: List[Any], decay: float = _DECAY) -> int:
    """Append this cycle's 12 persona scores to the decayed vote history.

    Lives in state["diversity"]["votes"][symbol]: a list of {"scores": [..12..],
    "w": decayed_weight}. Old entries are decayed each cycle and pruned below
    _MIN_W. Fault-isolated: returns the number of stored entries (0 on failure).
    """
    try:
        scores = [_finite(getattr(v, "score", 0.0)) for v in (verdicts or [])]
        if not scores:
            return 0
        mem = state.setdefault("diversity", {})
        votes = mem.setdefault("votes", {})
        hist: List[Dict[str, Any]] = votes.setdefault(str(symbol), [])
        decay = _finite(decay, _DECAY)
        if not (0.0 < decay < 1.0):
            decay = _DECAY
        new_hist = []
        for h in hist:
            w = _finite((h or {}).get("w"), 1.0) * decay
            if w >= _MIN_W:
                s = _arr((h or {}).get("scores"))
                if s.size == len(scores):
                    new_hist.append({"scores": [float(x) for x in s], "w": w})
        new_hist.append({"scores": scores, "w": 1.0})
        # bound memory: keep the newest _MAX_SYMBOLS entries per symbol
        votes[str(symbol)] = new_hist[-_MAX_SYMBOLS:]
        return len(votes[str(symbol)])
    except Exception as exc:
        log.warning("diversity record_votes failed: %s", exc)
        return 0


def vote_correlation_matrix(state: Dict[str, Any], symbol: str,
                            decay: float = _DECAY
                            ) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """Decay-weighted pairwise Pearson correlation of persona votes.

    Returns (matrix, meta). meta carries "obs" (number of stored cycles),
    "weight" (sum of decayed weights), and "effective_obs" (~(1-decay^n)/(1-decay)
    normalized mass — how much history really informs the matrix).
    Returns (None, meta) with status insufficient when < _MIN_OBS cycles or the
    votes are degenerate (zero variance). Never raises.
    """
    meta: Dict[str, Any] = {"obs": 0, "weight": 0.0, "effective_obs": 0.0}
    try:
        hist = (((state or {}).get("diversity") or {}).get("votes") or {}).get(str(symbol)) or []
        meta["obs"] = len(hist)
        if len(hist) < _MIN_OBS:
            meta["status"] = "insufficient"
            return None, meta
        # note: weights were already decayed at record time; here they are
        # used as-is (a static snapshot of each cycle's relative importance).
        w = np.array([_finite(h.get("w"), 1.0) for h in hist])
        wsum = float(w.sum())
        meta["weight"] = round(wsum, 3)
        meta["effective_obs"] = round(wsum, 3)
        if wsum <= 0:
            meta["status"] = "insufficient"
            return None, meta
        v = np.array([h.get("scores") for h in hist], dtype=float)  # T x M
        if v.ndim != 2 or v.shape[0] < _MIN_OBS:
            meta["status"] = "insufficient"
            return None, meta
        mean = (v * w[:, None]).sum(axis=0) / wsum
        c = v - mean
        cov = (c * w[:, None]).T @ c / wsum
        var = np.diag(cov)
        denom = np.sqrt(np.outer(var, var))
        with np.errstate(invalid="ignore", divide="ignore"):
            corr = np.where(denom > 0, cov / denom, 0.0)
        corr = np.clip(corr, -1.0, 1.0)
        np.fill_diagonal(corr, 1.0)
        meta["status"] = "ok"
        return corr, meta
    except Exception as exc:
        log.warning("diversity vote_correlation_matrix failed: %s", exc)
        meta["status"] = "error"
        meta["error"] = str(exc)[:200]
        return None, meta


# ── 2) bias–variance–covariance decomposition ──────────────────────────────────
def covariance_share(corr: Optional[np.ndarray],
                     var: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Decompose the council-mean variance into individual-variance vs
    pairwise-covariance components.

    Given the M x M persona vote-correlation matrix (and optional per-persona
    variances, default unit), the variance of the council mean vote is

        Var(m) = (1/M) * avg_var + ((M-1)/M) * avg_pairwise_cov

    Returns {"covariance_share", "variance_share", "variance_component",
    "covariance_component", "n_agents"}. share in [0, 1]; ~1.0 => the council
    is one crowded bet. Returns all-None shares on degenerate input.
    Never raises.
    """
    blank = {"covariance_share": None, "variance_share": None,
             "variance_component": None, "covariance_component": None,
             "n_agents": 0}
    try:
        c = _arr(corr)
        if c.size == 0:
            return dict(blank)
        m = int(round(math.sqrt(c.size)))
        if m < 2 or m * m != c.size:
            return dict(blank)
        corr_m = np.clip(c.reshape(m, m), -1.0, 1.0)
        v = _arr(var) if var is not None else np.ones(m)
        if v.size != m or np.any(~np.isfinite(v)) or np.any(v < 0):
            v = np.ones(m)
        sd = np.sqrt(v)
        cov_m = corr_m * np.outer(sd, sd)
        avg_var = float(np.mean(np.diag(cov_m)))
        off = cov_m[~np.eye(m, dtype=bool)]
        avg_cov = float(np.mean(off)) if off.size else 0.0
        var_comp = avg_var / m
        cov_comp = ((m - 1) / m) * avg_cov
        total = var_comp + cov_comp
        if not (math.isfinite(total) and total > 1e-12):
            return dict(blank, n_agents=m)
        cov_share = max(0.0, min(1.0, cov_comp / total))
        return {"covariance_share": round(cov_share, 4),
                "variance_share": round(1.0 - cov_share, 4),
                "variance_component": round(var_comp, 6),
                "covariance_component": round(cov_comp, 6),
                "n_agents": m}
    except Exception as exc:
        log.warning("diversity covariance_share failed: %s", exc)
        return dict(blank)


# ── 3) effective number of bets (Meucci) ──────────────────────────────────────
def effective_bets(weights: Dict[str, float],
                   corr_matrix: Optional[np.ndarray],
                   vols: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Meucci's Effective Number of Bets for the portfolio book.

    ENB = (sum_i w_i sigma_i)^2 / (w' Sigma w), with Sigma = diag(sigma) @
    corr @ diag(sigma). w are normalized |position values|. When `vols` is
    omitted, unit volatilities are assumed (measures directional concentration,
    not vol concentration) — documented in the output as "vol_assumption":
    "unit".

    Returns {"effective_bets", "nominal", "concentration_index", ...}.
    ~N => independent bets; ~1 => the book is one bet. Never raises; returns
    effective_bets None with status insufficient when the inputs are unusable.
    """
    out: Dict[str, Any] = {"effective_bets": None, "nominal": 0,
                           "concentration_index": None, "status": "insufficient"}
    try:
        names = [n for n, w in (weights or {}).items() if _finite(w) > 0]
        n = len(names)
        out["nominal"] = n
        if n == 0:
            return out
        c = _arr(corr_matrix)
        if c.size != n * n:
            return out
        rho = np.clip(c.reshape(n, n), -1.0, 1.0)
        w = np.array([_finite(weights[nm]) for nm in names], dtype=float)
        wsum = float(w.sum())
        if wsum <= 0 or not math.isfinite(wsum):
            return out
        w = w / wsum
        if vols:
            sig = np.array([_finite((vols or {}).get(nm), 0.0) for nm in names])
            if np.any(~np.isfinite(sig)) or np.any(sig <= 0):
                sig = np.ones(n)
                out["vol_assumption"] = "unit (bad vols supplied)"
            else:
                out["vol_assumption"] = "realized"
        else:
            sig = np.ones(n)
            out["vol_assumption"] = "unit"
        sigma = np.diag(sig) @ rho @ np.diag(sig)
        port_var = float(w @ sigma @ w)
        num = float(np.sum(w * sig)) ** 2
        if not (math.isfinite(port_var) and port_var > 1e-15):
            return out
        enb = num / port_var
        enb = max(1.0, min(float(n), enb))
        out.update({"effective_bets": round(enb, 3),
                    "concentration_index": round(1.0 - enb / n, 3),
                    "status": "ok", "names": sorted(names)})
        return out
    except Exception as exc:
        log.warning("diversity effective_bets failed: %s", exc)
        out["status"] = "error"
        out["error"] = str(exc)[:200]
        return out


# ── 4) per-cycle diversity report ────────────────────────────────────────────
def diversity_report(state: Dict[str, Any],
                     research: List[Dict[str, Any]],
                     positions: Optional[Dict[str, Dict[str, Any]]] = None,
                     closes_by_symbol: Optional[Dict[str, Any]] = None,
                     prices: Optional[Dict[str, float]] = None,
                     enabled: bool = True) -> Dict[str, Any]:
    """Build the per-cycle diversity report. Advisory only — never raises.

    - Records this cycle's council votes per symbol (decayed history).
    - Per symbol: decayed vote-correlation matrix + covariance-share.
    - Portfolio: effective bets (Meucci) vs nominal positions from asset
      return correlations (computed locally from closes; see limits in the
      module docstring).
    - Plain-language flags when the council or the book is highly correlated.
    """
    rep: Dict[str, Any] = {"status": "ok", "symbols": {}, "flags": [],
                           "council": {}, "book": {}}
    try:
        if not enabled:
            rep["status"] = "disabled"
            return rep
        positions = positions or {}
        closes_by_symbol = closes_by_symbol or {}
        prices = prices or {}

        # ── council side: record votes, decayed vote correlations ──
        council_shares: List[float] = []
        for r in (research or []):
            sym = str(r.get("symbol") or "?")
            verdict = r.get("verdict")
            verdicts = list(getattr(verdict, "verdicts", []) or [])
            record_votes(state, sym, verdicts)
            corr, meta = vote_correlation_matrix(state, sym)
            names = _names(verdicts)
            sym_rep: Dict[str, Any] = {
                "status": meta.get("status", "insufficient"),
                "obs": meta.get("obs", 0),
                "agents": names,
            }
            if corr is not None:
                dec = covariance_share(corr)
                sym_rep["covariance_share"] = dec["covariance_share"]
                sym_rep["correlation_matrix"] = [[round(float(x), 3) for x in row]
                                                 for row in corr]
                share = dec["covariance_share"]
                if share is not None:
                    council_shares.append(share)
                    crowded = _crowded_persona_count(corr, names)
                    if share >= _CROWD_COV_SHARE:
                        sym_rep["crowded"] = True
                        rep["flags"].append(
                            f"{sym}: council crowded — {share:.0%} of the council's "
                            f"signal variance is shared covariance; {crowded} of "
                            f"{len(names)} personas are highly correlated variants "
                            f"on the same signal (dispersion.py will not catch "
                            f"this — they agree with each other).")
                    else:
                        sym_rep["crowded"] = False
            rep["symbols"][sym] = sym_rep

        if council_shares:
            rep["council"] = {
                "mean_covariance_share": round(float(np.mean(council_shares)), 4),
                "max_covariance_share": round(float(np.max(council_shares)), 4),
                "symbols_measured": len(council_shares),
            }
        else:
            rep["council"] = {"mean_covariance_share": None,
                              "max_covariance_share": None,
                              "symbols_measured": 0}

        # ── book side: effective bets from asset return correlations ──
        book = _book_effective_bets(positions, closes_by_symbol, prices)
        rep["book"] = book
        enb = book.get("effective_bets")
        nom = book.get("nominal", 0)
        if (book.get("status") == "ok" and enb is not None and nom > 1
                and enb <= _CROWD_ENB_FRAC * nom):
            rep["flags"].append(
                f"Portfolio crowded: {nom} positions behave as ~{enb:.1f} "
                f"independent bets — they move together, so diversification "
                f"benefit is far below the position count. This is a measurement, "
                f"not a trade signal; caps and gates are unchanged.")
        return rep
    except Exception as exc:  # advisory math never breaks the desk
        log.warning("diversity report failed: %s", exc)
        return {"status": "error", "symbols": {}, "flags": [],
                "council": {}, "book": {"status": "error"},
                "error": str(exc)[:200]}


def _crowded_persona_count(corr: np.ndarray, names: List[str]) -> int:
    """Count personas whose average off-diagonal correlation >= _HIGH_CORR —
    i.e. personas that move in lockstep with the rest of the council."""
    try:
        m = corr.shape[0]
        if m < 2:
            return 0
        cnt = 0
        for i in range(m):
            others = np.delete(corr[i], i)
            if float(np.mean(others)) >= _HIGH_CORR:
                cnt += 1
        return cnt
    except Exception:
        return 0


def _book_effective_bets(positions: Dict[str, Dict[str, Any]],
                         closes_by_symbol: Dict[str, Any],
                         prices: Dict[str, float]) -> Dict[str, Any]:
    """Position weights + asset return-correlation matrix -> Meucci ENB."""
    out: Dict[str, Any] = {"status": "insufficient", "effective_bets": None,
                           "nominal": 0, "avg_pairwise_corr": None, "names": []}
    try:
        weights: Dict[str, float] = {}
        rets: Dict[str, np.ndarray] = {}
        for s, p in (positions or {}).items():
            if abs(_finite((p or {}).get("shares", 0))) <= 0:
                continue
            px = _finite(prices.get(s) or (p or {}).get("cost_basis") or 0)
            if not (math.isfinite(px) and px > 0):
                continue
            val = abs(_finite((p or {}).get("shares", 0))) * px
            if val <= 0:
                continue
            c = _arr((closes_by_symbol or {}).get(s))
            if c.size < 30 or np.any(c <= 0):
                continue  # no usable history -> excluded (never invented)
            rets[s] = np.diff(np.log(c[-60:]))
            weights[s] = val
        out["nominal"] = len(weights)
        if len(weights) < 2:
            return out
        names = sorted(weights)
        n = min(len(r) for r in rets.values())
        mat = np.column_stack([rets[s][-n:] for s in names])
        vols = np.std(mat, axis=0)
        corr = np.corrcoef(mat, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0, posinf=1.0, neginf=-1.0)
        off = corr[~np.eye(len(names), dtype=bool)]
        out["avg_pairwise_corr"] = (round(float(np.mean(off)), 3)
                                    if off.size else None)
        enb = effective_bets(
            {s: weights[s] for s in names}, corr,
            vols={s: float(vols[i]) for i, s in enumerate(names)})
        out.update({k: enb.get(k) for k in
                    ("effective_bets", "concentration_index", "status")})
        out["names"] = sorted(names)
        out["vol_assumption"] = enb.get("vol_assumption")
        return out
    except Exception as exc:
        log.warning("diversity book effective bets failed: %s", exc)
        out["status"] = "error"
        out["error"] = str(exc)[:200]
        return out


def risk_officer_read(state: Dict[str, Any]) -> Dict[str, Any]:
    """READ-ONLY accessor for the Risk Officer: the last computed effective-bets
    number. Measurement only — the caller must never write it into any gate,
    cap, or weight. Never raises."""
    try:
        rep = ((state or {}).get("_diversity_last") or {})
        book = (rep or {}).get("book") or {}
        return {"effective_bets": book.get("effective_bets"),
                "nominal_positions": book.get("nominal"),
                "concentration_index": book.get("concentration_index"),
                "cycle": rep.get("cycle")}
    except Exception:
        return {"effective_bets": None, "nominal_positions": None,
                "concentration_index": None, "cycle": None}
