from intelligence.strategy_ranking import rank_strategies


def test_requested_strategy_roster_is_always_present():
    rows = rank_strategies({})
    assert {row["name"] for row in rows} == {
        "Pairs", "Momentum", "Mean Reversion", "Credit Spread", "Wheel",
        "Volatility Breakout", "Regime Momentum", "AI Consensus",
    }
    assert all(row["score"] == 0.0 for row in rows)
    assert all(row["live_eligible"] is False for row in rows)


def test_realized_evidence_is_confidence_weighted():
    state = {"hermes": {"strat": {
        "pairs": {"n": 20.0, "w": 15.0},
        "wheel": {"n": 5.0, "w": 5.0},
    }}}
    rows = rank_strategies(state)
    by_name = {row["name"]: row for row in rows}
    assert by_name["Pairs"]["score"] > by_name["Wheel"]["score"]
    assert by_name["Pairs"]["win_rate"] == 0.75
    assert by_name["Pairs"]["evidence"] == "realized-hermes"


def test_ai_consensus_uses_shadow_score_without_execution_authority():
    shadow = {"providers": [{
        "provider": "consensus", "score": 88.0, "observations": 120, "hit_rate": 0.61,
    }]}
    rows = rank_strategies({}, shadow)
    assert rows[0]["name"] == "AI Consensus"
    assert rows[0]["score"] == 88.0
    assert rows[0]["evidence"] == "ai-shadow"
    assert rows[0]["live_eligible"] is False
    assert [row["rank"] for row in rows] == list(range(1, 9))
