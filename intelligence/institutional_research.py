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
PROMOTION_KEY = "institutional_research"
PROMOTION_STAGES = ("research", "backtest", "walk_forward", "paper", "shadow",
                    "canary", "production")


def multiplier_enabled(promotion_stage: str, feature_flag_enabled: bool) -> bool:
    """Only promoted, explicitly enabled research may affect order sizing."""
    try:
        promoted = PROMOTION_STAGES.index(str(promotion_stage).strip().lower()) \
            >= PROMOTION_STAGES.index("canary")
    except ValueError:
        promoted = False
    return bool(feature_flag_enabled) and promoted


def applied_multiplier(proposed: float, promotion_stage: str,
                       feature_flag_enabled: bool) -> float:
    if not multiplier_enabled(promotion_stage, feature_flag_enabled):
        return 1.0
    try:
        value = float(proposed)
    except (TypeError, ValueError):
        return 1.0
    return max(0.5, min(1.0, value)) if math.isfinite(value) else 1.0


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


def _timestamp(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float, np.integer, np.floating)):
            number = float(value)
            parsed = datetime.fromtimestamp(number / 1000.0 if number > 1e11 else number,
                                            tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _dated_returns(snapshot: MarketSnapshot) -> dict[Any, float]:
    closes = np.asarray(snapshot.closes, dtype=float)
    timestamps = np.asarray(snapshot.bar_timestamps, dtype=object)
    if closes.size < 2 or timestamps.size != closes.size or not np.all(np.isfinite(closes)):
        return {}
    out: dict[Any, float] = {}
    for index in range(1, closes.size):
        stamp = _timestamp(timestamps[index])
        if stamp is None or closes[index - 1] <= 0 or closes[index] <= 0:
            continue
        # Histories are daily; normalize venue-specific close times to the UTC
        # session date before joining (e.g. crypto 00:00 vs equity 21:00).
        out[stamp.date()] = float(math.log(closes[index] / closes[index - 1]))
    return out


class InstitutionalResearchFabric:
    def analyze(self, snapshots: Sequence[MarketSnapshot], *,
                as_of: str | None = None,
                requested_symbols: Sequence[str] | None = None,
                max_age_seconds: int | None = None,
                require_timestamps: bool = False) -> dict[str, Any]:
        generated_at = as_of or datetime.now(timezone.utc).isoformat()
        generated_dt = _timestamp(generated_at) or datetime.now(timezone.utc)
        requested = list(dict.fromkeys(requested_symbols or [s.symbol for s in snapshots]))
        supplied = {snapshot.symbol for snapshot in snapshots}
        rejected: dict[str, str] = {
            symbol: "research_unavailable" for symbol in requested if symbol not in supplied
        }
        valid: list[MarketSnapshot] = []
        ages: dict[str, float] = {}
        for snapshot in snapshots:
            closes = np.asarray(snapshot.closes, dtype=float)
            timestamps = np.asarray(snapshot.bar_timestamps, dtype=object)
            if snapshot.price <= 0 or closes.size < 20 or not np.all(np.isfinite(closes)):
                rejected[snapshot.symbol] = "invalid_or_short_history"
                continue
            last_bar = _timestamp(timestamps[-1]) if timestamps.size == closes.size else None
            if require_timestamps and last_bar is None:
                rejected[snapshot.symbol] = "missing_bar_timestamps"
                continue
            if last_bar is not None:
                age = max(0.0, (generated_dt - last_bar).total_seconds())
                ages[snapshot.symbol] = age
                if max_age_seconds is not None and age > max_age_seconds:
                    rejected[snapshot.symbol] = "stale_history"
                    continue
            valid.append(snapshot)
        if not valid:
            return self._empty(generated_at, len(requested), rejected)

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

        dated = {snapshot.symbol: _dated_returns(snapshot) for snapshot in valid}
        pair_correlations: list[float] = []
        pair_overlaps: list[int] = []
        for left_index, left in enumerate(sorted(dated)):
            for right in sorted(dated)[left_index + 1:]:
                overlap = sorted(set(dated[left]).intersection(dated[right]))[-60:]
                if len(overlap) < 20:
                    continue
                corr = float(np.corrcoef([dated[left][t] for t in overlap],
                                        [dated[right][t] for t in overlap])[0, 1])
                if math.isfinite(corr):
                    pair_correlations.append(corr)
                    pair_overlaps.append(len(overlap))
        correlation = float(np.median(pair_correlations)) if pair_correlations else 0.0
        observation_times = {
            snapshot.symbol: _timestamp(np.asarray(snapshot.bar_timestamps, dtype=object)[-1])
            for snapshot in valid if np.asarray(snapshot.bar_timestamps, dtype=object).size
        }
        observation_times = {symbol: stamp for symbol, stamp in observation_times.items()
                             if stamp is not None}
        snapshot_provenance = {}
        for snapshot in valid:
            bar_time = observation_times.get(snapshot.symbol)
            retrieved = _timestamp(snapshot.retrieved_at)
            source_time = _timestamp(snapshot.exchange_timestamp or snapshot.feed_timestamp) or bar_time
            snapshot_provenance[snapshot.symbol] = {
                "bar_timestamp": bar_time.isoformat() if bar_time else None,
                "exchange_timestamp": snapshot.exchange_timestamp,
                "feed_timestamp": snapshot.feed_timestamp,
                "retrieved_at": retrieved.isoformat() if retrieved else snapshot.retrieved_at,
                "latency_ms": round(max(0.0, (retrieved - source_time).total_seconds()) * 1000, 3)
                if retrieved and source_time else None,
                "age_seconds": round(ages[snapshot.symbol], 3) if snapshot.symbol in ages else None,
            }

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
            "point_in_time": len(observation_times) == len(valid), "execution_authority": False,
            "universe": sorted(raw), "coverage": len(valid) / max(1, len(requested)),
            "configured_symbols": len(requested), "successful_symbols": len(valid),
            "rejected_symbols": rejected,
            "market": {"regime": regime, "regime_probabilities": regimes,
                       "breadth_20d": round(breadth20, 6), "breadth_50d": round(breadth50, 6),
                       "breadth_200d": round(breadth200, 6),
                       "median_correlation_60d": round(correlation, 6),
                       "correlation_pairs": len(pair_correlations),
                       "minimum_pair_overlap": min(pair_overlaps) if pair_overlaps else 0,
                       "cross_sectional_dispersion": round(dispersion, 8),
                       "average_volatility": round(avg_vol, 6),
                       "volatility_change": round(vol_change, 6),
                       "expected_shortfall_95": round(avg_tail, 8),
                       "stress_score": round(stress_score, 6),
                       "advisory_risk_multiplier": round(max(.5, min(1.0, 1.0 - .5*stress_score)), 6)},
            "factors": factors,
            "provenance": {"inputs": ["adjusted_close", "volume", "bar_timestamp"],
                           "method": "transparent_public_domain_estimators",
                           "latest_bar_timestamp": max(observation_times.values()).isoformat()
                           if observation_times else None,
                           "oldest_age_seconds": round(max(ages.values()), 3) if ages else None,
                           "snapshots": snapshot_provenance,
                           "future_data_used": False},
        }

    @staticmethod
    def _empty(as_of: str, requested: int, rejected: dict[str, str] | None = None) -> dict[str, Any]:
        return {"version": VERSION, "as_of": as_of, "point_in_time": False,
                "execution_authority": False, "universe": [], "coverage": 0.0,
                "configured_symbols": requested, "successful_symbols": 0,
                "rejected_symbols": rejected or {},
                "market": {"regime": "unknown", "regime_probabilities": {},
                           "advisory_risk_multiplier": .5}, "factors": {},
                "provenance": {"inputs": [], "requested_symbols": requested,
                               "future_data_used": False}}
