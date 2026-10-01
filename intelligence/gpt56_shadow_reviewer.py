"""GPT-5.6 shadow reviewer for quantitative research.

Research-only by construction: this module emits regime/uncertainty diagnostics
and never emits trade direction, order intent, position size, or broker action.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GPT56ResearchReview:
    used: bool
    regime: str
    uncertainty: float
    model_disagreement: float
    fragile_signal: bool
    abstain_from_promotion: bool
    rationale: str = ""
    telemetry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SCHEMA = {
    "type": "object",
    "properties": {
        "regime": {"type": "string", "enum": [
            "trend", "range", "breakout", "high_volatility", "low_volatility",
            "liquidity_stress", "event_shock", "unknown"
        ]},
        "uncertainty": {"type": "number"},
        "model_disagreement": {"type": "number"},
        "fragile_signal": {"type": "boolean"},
        "abstain_from_promotion": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": ["regime", "uncertainty", "model_disagreement", "fragile_signal",
                 "abstain_from_promotion", "rationale"],
    "additionalProperties": False,
}


def _clip(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


class GPT56ShadowReviewer:
    def __init__(self) -> None:
        self.enabled = (os.getenv("GPT56_CHALLENGER_ENABLED", "false").strip().lower()
                        in {"1", "true", "yes", "on"})
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = (os.getenv("GPT56_CHALLENGER_MODEL", "gpt-5.6") or "gpt-5.6").strip()
        effort = (os.getenv("GPT56_CHALLENGER_REASONING", "medium") or "medium").strip().lower()
        self.reasoning_effort = effort if effort in {"low", "medium", "high", "xhigh"} else "medium"

    def review(self, snapshot: Mapping[str, Any], quant: Mapping[str, Any],
               monte_carlo: Mapping[str, Any]) -> GPT56ResearchReview:
        if not self.enabled or not self.api_key:
            return GPT56ResearchReview(False, "unknown", 1.0, 1.0, True, True,
                                       "challenger disabled or API key absent", {})
        prompt = json.dumps({
            "market_state": dict(snapshot),
            "quant_ensemble": dict(quant),
            "monte_carlo_summary": dict(monte_carlo),
        }, separators=(",", ":"), default=str)
        payload = {
            "model": self.model,
            "instructions": (
                "You are a research reviewer for a shadow quantitative experiment. "
                "Classify market regime and assess uncertainty, disagreement, and signal fragility. "
                "Do not recommend trades, directions, orders, leverage, or position sizes. "
                "Your output is only for experiment evaluation and promotion gating."
            ),
            "input": prompt,
            "max_output_tokens": 1000,
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": {"type": "json_schema", "name": "gpt56_shadow_research_review",
                                 "strict": True, "schema": _SCHEMA}},
        }
        import requests
        started = time.perf_counter()
        response = requests.post(
            "https://api.openai.com/v1/responses",
            timeout=max(5.0, float(os.getenv("GPT56_CHALLENGER_TIMEOUT_SECONDS", "45"))),
            headers={"Authorization": "Bearer " + self.api_key,
                     "Content-Type": "application/json"},
            json=payload,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        if not response.ok:
            return GPT56ResearchReview(False, "unknown", 1.0, 1.0, True, True,
                                       f"OpenAI HTTP {response.status_code}",
                                       {"latency_ms": latency_ms, "schema_valid": False})
        body = response.json()
        text = body.get("output_text") or ""
        if not text:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text += content.get("text", "")
        try:
            data = json.loads(text)
        except Exception:
            return GPT56ResearchReview(False, "unknown", 1.0, 1.0, True, True,
                                       "structured response could not be parsed",
                                       {"latency_ms": latency_ms, "schema_valid": False})
        usage = body.get("usage") or {}
        return GPT56ResearchReview(
            True,
            str(data.get("regime", "unknown")),
            _clip(data.get("uncertainty"), 0.0, 1.0, 1.0),
            _clip(data.get("model_disagreement"), 0.0, 1.0, 1.0),
            bool(data.get("fragile_signal", True)),
            bool(data.get("abstain_from_promotion", True)),
            str(data.get("rationale", ""))[:600],
            {
                "provider": "openai",
                "requested_model": self.model,
                "resolved_model": body.get("model") or self.model,
                "reasoning_effort": self.reasoning_effort,
                "latency_ms": latency_ms,
                "schema_valid": True,
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
            },
        )
