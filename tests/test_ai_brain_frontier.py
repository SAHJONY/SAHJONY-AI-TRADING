"""Frontier AI brain tests; all provider traffic is mocked."""
from __future__ import annotations

import json

from config import load_config
from intelligence.ai_brain import AIBrain


class _Response:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _brain(monkeypatch) -> AIBrain:
    monkeypatch.setenv("AI_BRAIN_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("AUTO_UPDATE_MODELS", "false")
    return AIBrain(load_config())


def test_openai_uses_responses_api_and_strict_schema(monkeypatch):
    brain = _brain(monkeypatch)
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, payload=kwargs["json"])
        return _Response({"model": "gpt-5.6-sol", "usage": {"input_tokens": 42, "output_tokens": 9},
                          "output_text": json.dumps({
            "risk_summary": "fragile momentum", "fragilities": ["high beta"],
            "confidence": 1.7,
        })})

    import requests
    monkeypatch.setattr(requests, "post", post)
    result = json.loads(brain._ask_openai("portfolio") or "{}")
    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["payload"]["model"] == "gpt-5.6"
    assert seen["payload"]["reasoning"] == {"effort": "high"}
    assert seen["payload"]["text"]["format"]["strict"] is True
    assert result["confidence"] == 1.0


def test_openai_is_bounded_fallback_brain(monkeypatch):
    brain = _brain(monkeypatch)

    def post(url, **kwargs):
        name = kwargs["json"]["text"]["format"]["name"]
        data = ({"risk_summary": "neutral", "fragilities": [], "confidence": 0.8}
                if name == "portfolio_risk_counsel" else
                {"posture": "risk_off", "global_risk_multiplier": 0.1,
                 "commentary": "protect capital", "per_symbol_adjust": {"SPY": -9.0}})
        return _Response({"model": "gpt-5.6-sol",
                          "usage": {"input_tokens": 100, "output_tokens": 25},
                          "output": [{"content": [{"type": "output_text",
                                                    "text": json.dumps(data)}]}]})

    import requests
    monkeypatch.setattr(requests, "post", post)
    verdict = brain.advise([{"symbol": "SPY", "price": 500.0, "conviction": 0.7}])
    assert verdict.used is True
    assert verdict.brain_model == "openai:gpt-5.6"
    assert verdict.global_risk_multiplier == 0.5
    assert verdict.per_symbol_adjust["SPY"] == -0.15
    assert verdict.telemetry == {
        "provider": "openai",
        "requested_model": "gpt-5.6",
        "resolved_model": "gpt-5.6-sol",
        "latency_ms": verdict.telemetry["latency_ms"],
        "input_tokens": 100,
        "output_tokens": 25,
        "estimated_cost_usd": 0.00125,
        "fallback_used": False,
        "schema_valid": True,
        "conviction_adjustment": {"SPY": -0.15},
        "risk_multiplier": 0.5,
        "clamp_applied": True,
    }


def test_no_provider_stays_neutral(monkeypatch):
    monkeypatch.setenv("AI_BRAIN_ENABLED", "true")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    brain = AIBrain(load_config())
    assert brain.enabled is False
    assert brain.advise([{"symbol": "SPY"}]).used is False
