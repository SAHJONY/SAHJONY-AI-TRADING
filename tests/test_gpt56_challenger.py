from __future__ import annotations

from dataclasses import dataclass

import pytest

from intelligence.gpt56_challenger_pipeline import GPT56ChallengerResearchPipeline
from intelligence.market_state import build_market_state
from intelligence.monte_carlo import simulate_returns
from intelligence.quant_ensemble import evaluate_quant_ensemble
from intelligence.shadow_pipeline import ShadowPipeline


@dataclass(frozen=True)
class _FakeReview:
    used: bool = True
    regime: str = "trend"
    uncertainty: float = 0.2
    model_disagreement: float = 0.1
    fragile_signal: bool = False
    abstain_from_promotion: bool = False
    rationale: str = "test"
    telemetry: dict | None = None

    def to_dict(self):
        return {
            "used": self.used,
            "regime": self.regime,
            "uncertainty": self.uncertainty,
            "model_disagreement": self.model_disagreement,
            "fragile_signal": self.fragile_signal,
            "abstain_from_promotion": self.abstain_from_promotion,
            "rationale": self.rationale,
            "telemetry": self.telemetry or {"latency_ms": 5, "schema_valid": True},
        }


class _FakeReviewer:
    def review(self, snapshot, quant, monte_carlo):
        assert "price" in snapshot
        assert "score" in quant
        assert "probability_profit" in monte_carlo
        return _FakeReview()


def _prices(n=80):
    return [100.0 + i * 0.15 + ((i % 7) - 3) * 0.04 for i in range(n)]


def test_market_state_requires_history():
    with pytest.raises(ValueError):
        build_market_state("BTC/USD", [100.0] * 10)


def test_quant_ensemble_is_bounded():
    state = build_market_state("BTC/USD", _prices(), microstructure={"order_flow_imbalance": 0.4})
    result = evaluate_quant_ensemble(state)
    assert -1.0 <= result.score <= 1.0
    assert 0.0 <= result.confidence <= 1.0
    assert result.direction in {-1, 0, 1}


def test_monte_carlo_is_deterministic_for_seed():
    px = _prices()
    returns = [px[i] / px[i - 1] - 1 for i in range(1, len(px))]
    a = simulate_returns(returns, paths=500, horizon_steps=3, seed=56)
    b = simulate_returns(returns, paths=500, horizon_steps=3, seed=56)
    assert a == b
    assert 0.0 <= a.probability_profit <= 1.0
    assert a.var_99 <= a.var_95


def test_pipeline_records_research_only_neutral_shadow(tmp_path):
    shadow = ShadowPipeline(
        pending_path=tmp_path / "pending.jsonl",
        resolved_path=tmp_path / "resolved.jsonl",
    )
    pipeline = GPT56ChallengerResearchPipeline(shadow=shadow, reviewer=_FakeReviewer())
    result = pipeline.evaluate("BTC/USD", _prices(), mc_paths=500)
    pending = pipeline.record_shadow(result, horizon_seconds=300)
    assert pending.provider == "gpt56_challenger_research"
    assert pending.adjustment == 0.0
    assert pending.risk_multiplier == 1.0
    assert pending.metadata["research_only"] is True
    assert shadow.counts()["pending"] == 1
