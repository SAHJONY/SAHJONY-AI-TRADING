"""Point-in-time, public-domain institutional market-intelligence fabric.

Implements transparent price/volume analytics commonly documented in academic
and practitioner research. It is not any firm's proprietary model and has no
execution authority. The global risk multiplier can only de-risk (<= 1.0).
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Sequence

import numpy as np

from intelligence import engines
from intelligence.agents import MarketSnapshot

VERSION = "institutional-research-v1"


def _finite(value: float, default: float = 0.0) -> float:
    return float(value) if math.isfinite(float(value)) else default


def _rank_scores(values: dict[str, float], *, higher_is_better: bool = True) -> dict[str, float]:
    ordered = sorted(values, key=lambda symbol: (values[symbol], symbol))
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0]: 0.0}
    scores = {symbol: 2.0 * index / (len(ordered) - 1) - 1.0
              for index, symbol in enumerate(ordered)}
    return scores if higher_is_better else {symbol: -score for symbol, score in scores.items()}


def _expected_shortfall(returns: np.ndarray, quantile: float = 0.05) -> float:
    clean = returns[np.isfinite(returns)]
    if clean.size < 20:
        return 0.0
    threshold = np.quantile(clean, quantile)
    tail = clean[clean <= threshold]
    return float(np.mean(tail)) if tail.size else 0.0


def _max_drawdown(closes: np.ndarray) -> float:
    if closes.size < 2:
        return 0.0
    peaks = np.maximum.accumulate(closes)
    return float(np.min(closes / np.maximum(peaks, 1e-12) - 1.0))


def _amihud(snapshot: MarketSnapshot) -> float:
    closes = engines.to_array(snapshot.closes)
    volumes = engines.to_array(snapshot.volumes)
    n = min(closes.size, volumes.size)
    if n < 21:
        return 0.0
    closes, volumes = closes[-n:], volumes[-n:]
    returns = np.abs(np.diff(np.log(np.maximum(closes, 1e-12))))
    dollar_volume = np.maximum(closes[1:] * volumes[1:], 1.0)
    return float(np.median(returns[-60:] / dollar_volume[-60:]) * 1e9)


def _softmax(values: Sequence[float]) -> list[float]:
    array = np.asarray(values, dtype=float)
    array -= np.max(array)
    exp = np.exp(array)
    return (exp / np.sum(exp)).tolist()


class InstitutionalResearchFabric:
    def analyze(self, snapshots: Sequence[MarketSnapshot], *,
                as_of: str | None = None) -> dict[str, Any]:
        valid = [snapshot for snapshot in snapshots
                 if snapshot.price > 0 and engines.to_array(snapshot.closes).size >= 20]
        generated_at = as_of or datetime.now(timezone.utc).isoformat()
        if not valid:
            return self._empty(generated_at, len(snapshots))

        raw: dict[str, dict[str, float]] = {}
        for snapshot in valid:
            closes = engines.to_array(snapshot.closes)
            returns = engines.log_returns(closes)
            recent_vol = float(np.std(returns[-20:], ddof=1) * np.sqrt(252)) if returns.size >= 20 else 0.0
            prior = returns[-80:-20]
            prior_vol = float(np.std(prior, ddof=1) * np.sqrt(252)) if prior.size >= 20 else recent_vol
            raw[snapshot.symbol] = {
                "momentum_1m": snapshot.ret_over(21),
                "momentum_3m": snapshot.ret_over(63),
                "momentum_6m": snapshot.ret_over(126),
                "volatility": engines.annualized_vol(closes),
                "volatility_change": recent_vol / max(prior_vol, 1e-9) - 1.0,
                "expected_shortfall_95": _expected_shortfall(returns),
                "max_drawdown": _max_drawdown(closes),
                "amihud_illiquidity": _amihud(snapshot),
                "above_sma20": float(snapshot.price > snapshot.sma(20)),
                "above_sma50": float(snapshot.price > snapshot.sma(50)),
                "above_sma200": float(snapshot.price > snapshot.sma(200)) if closes.size >= 200 else 0.0,
            }

        momentum = {s: .2*v["momentum_1m"] + .3*v["momentum_3m"] + .5*v["momentum_6m"]
                    for s, v in raw.items()}
        low_vol = _rank_scores({s: v["volatility"] for s, v in raw.items()}, higher_is_better=False)
        liquidity = _rank_scores({s: v["amihud_illiquidity"] for s, v in raw.items()},
                                 higher_is_better=False)
        momentum_rank = _rank_scores(momentum)
        drawdown_rank = _rank_scores({s: v["max_drawdown"] for s, v in raw.items()})
        factors = {}
        for symbol in sorted(raw):
            composite = (.45 * momentum_rank[symbol] + .25 * low_vol[symbol]
                         + .20 * liquidity[symbol] + .10 * drawdown_rank[symbol])
            factors[symbol] = {**{k: round(_finite(v), 8) for k, v in raw[symbol].items()},
                               "momentum_rank": round(momentum_rank[symbol], 6),
                               "low_vol_rank": round(low_vol[symbol], 6),
                               "liquidity_rank": round(liquidity[symbol], 6),
                               "composite_factor_score": round(composite, 6)}

        aligned = [engines.log_returns(snapshot.closes)[-60:] for snapshot in valid]
        min_length = min((series.size for series in aligned), default=0)
        correlation = 0.0
        if len(aligned) >= 2 and min_length >= 20:
            matrix = np.corrcoef(np.vstack([series[-min_length:] for series in aligned]))
            upper = matrix[np.triu_indices(len(aligned), 1)]
            finite = upper[np.isfinite(upper)]
            correlation = float(np.median(finite)) if finite.size else 0.0

        breadth20 = float(np.mean([v["above_sma20"] for v in raw.values()]))
        breadth50 = float(np.mean([v["above_sma50"] for v in raw.values()]))
        breadth200 = float(np.mean([v["above_sma200"] for v in raw.values()]))
        avg_vol = float(np.mean([v["volatility"] for v in raw.values()]))
        vol_change = float(np.mean([v["volatility_change"] for v in raw.values()]))
        avg_tail = float(np.mean([v["expected_shortfall_95"] for v in raw.values()]))
        dispersion = float(np.std(list(momentum.values()))) if len(momentum) > 1 else 0.0
        stress_score = float(np.clip(
            .30 * max(0.0, (avg_vol - .18) / .25)
            + .20 * max(0.0, vol_change)
            + .20 * max(0.0, correlation)
            + .20 * (1.0 - breadth50)
            + .10 * max(0.0, -avg_tail / .03), 0.0, 1.5))
        trend_score = float(np.clip((breadth20 + breadth50 + breadth200) / 3.0, 0.0, 1.0))
        probs = _softmax([2.2 * trend_score - stress_score,
                          1.0 - abs(trend_score - .5) - .4 * stress_score,
                          2.4 * stress_score - trend_score])
        regimes = dict(zip(("risk_on", "transition", "stress"), (round(p, 6) for p in probs)))
        regime = max(regimes, key=regimes.get)
        return {
            "version": VERSION, "as_of": generated_at,
            "point_in_time": True, "execution_authority": False,
            "universe": sorted(raw), "coverage": len(valid) / max(1, len(snapshots)),
            "market": {"regime": regime, "regime_probabilities": regimes,
                       "breadth_20d": round(breadth20, 6), "breadth_50d": round(breadth50, 6),
                       "breadth_200d": round(breadth200, 6),
                       "median_correlation_60d": round(correlation, 6),
                       "cross_sectional_dispersion": round(dispersion, 8),
                       "average_volatility": round(avg_vol, 6),
                       "volatility_change": round(vol_change, 6),
                       "expected_shortfall_95": round(avg_tail, 8),
                       "stress_score": round(stress_score, 6),
                       "advisory_risk_multiplier": round(max(.5, min(1.0, 1.0 - .5*stress_score)), 6)},
            "factors": factors,
            "provenance": {"inputs": ["adjusted_close", "volume"],
                           "method": "transparent_public_domain_estimators",
                           "future_data_used": False},
        }

    @staticmethod
    def _empty(as_of: str, requested: int) -> dict[str, Any]:
        return {"version": VERSION, "as_of": as_of, "point_in_time": True,
                "execution_authority": False, "universe": [], "coverage": 0.0,
                "market": {"regime": "unknown", "regime_probabilities": {},
                           "advisory_risk_multiplier": .5}, "factors": {},
                "provenance": {"inputs": [], "requested_symbols": requested,
                               "future_data_used": False}}
