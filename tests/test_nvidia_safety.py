"""Offline regression tests for NVIDIA provider safety."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

os.environ["AI_BRAIN_ENABLED"] = "true"
os.environ["NVIDIA_API_KEY"] = "test-key-never-sent"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("XAI_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)

from config import load_config
from intelligence.ai_brain import AIBrain


PORTFOLIO = [{
    "symbol": "ETH/USD", "price": 1900.0, "conviction": 0.6,
    "direction": "long", "composite": 0.2, "alpha": 0.0, "beta": 1.0,
    "vol": 0.5,
}]


def test_nvidia_is_not_called_twice_when_primary():
    brain = AIBrain(load_config())
    with patch.object(brain, "_ask_nvidia") as counsellor, \
            patch.object(brain, "_ask_nim_brain", side_effect=TimeoutError("slow")) as primary:
        verdict = brain.advise(PORTFOLIO)
    counsellor.assert_not_called()
    primary.assert_called_once()
    assert verdict.used is False
    assert verdict.posture == "risk_off"
    assert verdict.global_risk_multiplier == 0.70


def test_healthcheck_never_returns_key():
    brain = AIBrain(load_config())
    fake_requests = SimpleNamespace(
        Timeout=TimeoutError,
        post=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("offline")),
    )
    with patch.dict(sys.modules, {"requests": fake_requests}):
        result = brain.nvidia_healthcheck()
    assert "test-key-never-sent" not in repr(result)
    assert result["ok"] is False
    assert result["provider"] == "nvidia"


if __name__ == "__main__":
    test_nvidia_is_not_called_twice_when_primary()
    test_healthcheck_never_returns_key()
    print("✓ NVIDIA provider safety tests")
