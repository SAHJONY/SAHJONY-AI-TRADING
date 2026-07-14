from intelligence.self_improvement import self_improvement_score


def test_no_evidence_is_zero_and_not_promotion_ready():
    score = self_improvement_score({}, {}, 100)
    assert score["knowledge_base"] == {"score": 0.0, "nodes": 0}
    assert score["model_accuracy"] is None
    assert score["learning_progress"] == 0.0
    assert score["training_coverage"] == 0.0
    assert score["promotion_ready"] is False
    assert score["overall_intelligence"] == 0.0
    assert score["evidence_state"] == "no_evidence"


def test_score_combines_knowledge_accuracy_progress_and_coverage():
    state = {"hermes": {"hits": {f"S{i}": {} for i in range(10)},
                         "strat": {f"X{i}": {} for i in range(5)}}}
    shadow = {
        "observations": 100,
        "recommended_provider": "openai",
        "providers": [
            {"provider": "claude", "observations": 60, "hit_rate": 0.6},
            {"provider": "openai", "observations": 40, "hit_rate": 0.7},
        ],
        "leaders": {"crypto": {"provider": "openai"}, "equity": {"provider": "claude"},
                    "options": None, "market_regime": {"provider": "openai"}},
    }
    score = self_improvement_score(state, shadow, 100)
    assert score["knowledge_base"]["score"] == 75.0
    assert score["model_accuracy"] == 0.64
    assert score["learning_progress"] == 1.0
    assert score["training_coverage"] > 0.5
    assert score["promotion_ready"] is True
    assert 0 < score["overall_intelligence"] <= 100
    assert score["evidence_state"] == "mature"


def test_progress_and_scores_are_bounded():
    shadow = {"observations": 999999, "providers": [], "leaders": {}}
    score = self_improvement_score({}, shadow, 20)
    assert score["learning_progress"] == 1.0
    assert 0.0 <= score["overall_intelligence"] <= 100.0
