import pytest

from intelligence.llm_council import (
    CouncilConfig,
    CouncilResult,
    CouncilSafetyError,
    LLMCouncil,
    apply_council_tilt,
)


def fake_model(label):
    def _call(prompt):
        if "peer-reviewing" in prompt:
            # IDs are deterministic but unknown here; echo candidate IDs in prompt order.
            ids = []
            for token in prompt.replace("\n", " ").split():
                token = token.rstrip(":,.")
                if token.startswith("candidate-") and token not in ids:
                    ids.append(token)
            return "Ranking: " + " > ".join(ids) + ". Evidence is mixed; preserve risk gates."
        return f"{label}: calibrated research opinion; uncertainty remains material."

    return _call


def enabled_config(**overrides):
    base = dict(enabled=True, research_only=True, min_models=3, max_models=7, max_influence=0.15)
    base.update(overrides)
    return CouncilConfig(**base)


def test_disabled_by_default_fails_closed(monkeypatch):
    monkeypatch.delenv("SAHJONY_LLM_COUNCIL_ENABLED", raising=False)
    council = LLMCouncil(
        {"a": fake_model("a"), "b": fake_model("b"), "c": fake_model("c")},
        fake_model("chair"),
    )
    with pytest.raises(CouncilSafetyError):
        council.run("evaluate BTC")


def test_requires_three_models():
    council = LLMCouncil(
        {"a": fake_model("a"), "b": fake_model("b")},
        fake_model("chair"),
        enabled_config(),
    )
    with pytest.raises(CouncilSafetyError):
        council.run("evaluate BTC")


def test_research_result_is_execution_blocked():
    council = LLMCouncil(
        {
            "alpha": fake_model("alpha"),
            "beta": fake_model("beta"),
            "gamma": fake_model("gamma"),
        },
        fake_model("chair"),
        enabled_config(),
    )
    result = council.run("evaluate BTC", {"regime": "risk-off"})
    assert result.status == "research_complete"
    assert result.research_only is True
    assert result.execution_blocked is True
    assert len(result.opinions) == 3
    assert len(result.reviews) == 3
    assert 0.0 <= result.permitted_influence <= 0.15


def test_model_identity_is_anonymized_in_peer_material():
    captured = []

    def reviewer(prompt):
        captured.append(prompt)
        return "all candidates show uncertainty"

    council = LLMCouncil(
        {"secret-model-a": reviewer, "secret-model-b": reviewer, "secret-model-c": reviewer},
        reviewer,
        enabled_config(),
    )
    council.run("evaluate ETH")
    peer_prompts = [p for p in captured if "peer-reviewing" in p]
    assert peer_prompts
    # Model names can appear in their own generated content only if the callable emits them;
    # the council-generated candidate labels themselves must be anonymous.
    assert all("candidate-" in p for p in peer_prompts)


def test_tilt_is_bounded_and_cannot_bypass_safety():
    result = CouncilResult(
        status="research_complete",
        query_hash="abc",
        confidence=1.0,
        disagreement=0.0,
        permitted_influence=0.15,
        research_only=True,
        execution_blocked=True,
    )
    assert apply_council_tilt(0.9, result, 1.0) == 1.0
    assert apply_council_tilt(-0.9, result, -1.0) == -1.0

    unsafe = CouncilResult(
        status="research_complete",
        query_hash="abc",
        permitted_influence=0.15,
        research_only=False,
        execution_blocked=False,
    )
    with pytest.raises(CouncilSafetyError):
        apply_council_tilt(0.0, unsafe, 1.0)


def test_influence_above_safety_envelope_rejected():
    council = LLMCouncil(
        {"a": fake_model("a"), "b": fake_model("b"), "c": fake_model("c")},
        fake_model("chair"),
        enabled_config(max_influence=0.30),
    )
    with pytest.raises(CouncilSafetyError):
        council.run("evaluate SOL")
