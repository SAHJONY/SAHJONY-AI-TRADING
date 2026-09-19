"""End-to-end GPT-5.6 challenger research pipeline.

This path is intentionally execution-isolated. It computes features, a local
ensemble, Monte Carlo diagnostics, and an optional GPT-5.6 research review, then
records a neutral ShadowPipeline observation with the research payload attached.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from intelligence.gpt56_shadow_reviewer import GPT56ShadowReviewer
from intelligence.market_state import MarketStateSnapshot, build_market_state
from intelligence.monte_carlo import MonteCarloSummary, simulate_returns
from intelligence.quant_ensemble import QuantEnsembleResult, evaluate_quant_ensemble
from intelligence.shadow_pipeline import PendingShadow, ShadowPipeline


@dataclass(frozen=True)
class ChallengerResearchResult:
    snapshot: MarketStateSnapshot
    quant: QuantEnsembleResult
    monte_carlo: MonteCarloSummary
    review: dict[str, Any]


class GPT56ChallengerResearchPipeline:
    def __init__(self, *, shadow: ShadowPipeline | None = None,
                 reviewer: GPT56ShadowReviewer | None = None) -> None:
        self.shadow = shadow or ShadowPipeline()
        self.reviewer = reviewer or GPT56ShadowReviewer()

    def evaluate(
        self,
        symbol: str,
        prices: Iterable[float],
        *,
        microstructure: Mapping[str, float] | None = None,
        mc_paths: int = 10_000,
        mc_horizon_steps: int = 3,
        mc_seed: int = 56,
    ) -> ChallengerResearchResult:
        px = [float(v) for v in prices]
        snapshot = build_market_state(symbol, px, microstructure=microstructure)
        quant = evaluate_quant_ensemble(snapshot)
        returns = [px[i] / px[i - 1] - 1.0 for i in range(1, len(px)) if px[i - 1] > 0]
        mc = simulate_returns(returns, paths=mc_paths, horizon_steps=mc_horizon_steps,
                              seed=mc_seed)
        review_obj = self.reviewer.review(snapshot.to_dict(), quant.to_dict(), mc.to_dict())
        return ChallengerResearchResult(snapshot, quant, mc, review_obj.to_dict())

    def record_shadow(
        self,
        result: ChallengerResearchResult,
        *,
        horizon_seconds: int = 1800,
        turnover_cost_bps: float = 0.0,
    ) -> PendingShadow:
        """Record research evidence without creating an execution-facing signal.

        Adjustment is deliberately zero and risk multiplier one. The quant score
        and GPT diagnostics live only in metadata for later champion/challenger
        evaluation; they cannot alter broker behavior through this method.
        """
        review = dict(result.review)
        telemetry = dict(review.get("telemetry") or {})
        return self.shadow.record(
            provider="gpt56_challenger_research",
            symbol=result.snapshot.symbol,
            entry_price=result.snapshot.price,
            base_conviction=max(0.0, min(1.0, result.quant.confidence)),
            adjustment=0.0,
            risk_multiplier=1.0,
            horizon_seconds=horizon_seconds,
            turnover_cost_bps=turnover_cost_bps,
            latency_ms=float(telemetry.get("latency_ms", 0.0) or 0.0),
            schema_valid=bool(telemetry.get("schema_valid", not review.get("used", False))),
            fallback_used=False,
            metadata={
                "research_only": True,
                "quant": result.quant.to_dict(),
                "monte_carlo": result.monte_carlo.to_dict(),
                "gpt56_review": review,
            },
        )
