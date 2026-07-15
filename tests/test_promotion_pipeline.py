import pytest

from database.db import Database
from intelligence.promotion_pipeline import PromotionPipeline, STAGES


def pipeline(tmp_path, **kwargs):
    return PromotionPipeline(Database(str(tmp_path / "promotion.db")), **kwargs)


def test_pipeline_is_sequential_and_records_blocked_attempts(tmp_path):
    p = pipeline(tmp_path)
    p.register("momentum", "Momentum")

    blocked = p.promote("momentum", actor="research", reason="candidate ready")
    assert blocked["promoted"] is False
    assert "missing evidence: research_reviewed" in blocked["blockers"]
    assert p.snapshot()["candidates"][0]["stage"] == "research"
    assert p.snapshot()["audit"][0]["allowed"] is False

    p.update_evidence("momentum", {"research_reviewed": True})
    result = p.promote("momentum", actor="research", reason="review complete")
    assert result["promoted"] is True
    assert result["to_stage"] == "backtest"

    skipped = p.promote("momentum", actor="research", reason="skip",
                        target_stage="paper")
    assert skipped["promoted"] is False
    assert "exactly one stage" in skipped["blockers"][0]


def test_evidence_gates_reach_shadow_but_default_policy_blocks_canary(tmp_path):
    p = pipeline(tmp_path)
    p.register("pairs", "Pairs")
    p.update_evidence("pairs", {
        "research_reviewed": True,
        "backtest_passed": True,
        "walk_forward_passed": True,
        "paper_observations": 30,
        "paper_sharpe": 0.8,
        "paper_max_drawdown": 0.05,
        "shadow_observations": 250,
        "shadow_sharpe": 1.1,
        "shadow_max_drawdown": 0.04,
    })
    for target in STAGES[1:5]:
        assert p.promote("pairs", actor="committee", reason="gate pass",
                         target_stage=target)["promoted"] is True

    result = p.promote("pairs", actor="owner", reason="request canary",
                       target_stage="canary", human_approved=True)
    assert result["promoted"] is False
    assert "canary stage disabled by host policy" in result["blockers"]
    assert p.snapshot()["canary_enabled"] is False
    assert p.snapshot()["production_enabled"] is False
    assert p.snapshot()["execution_authority"] is False


def test_opted_in_canary_still_requires_explicit_human_approval(tmp_path):
    p = pipeline(tmp_path, allow_canary=True)
    p.register("wheel", "Wheel")
    p.database.update_promotion_candidate("wheel", stage="shadow", evidence={
        "shadow_observations": 150, "shadow_sharpe": 0.6,
        "shadow_max_drawdown": 0.08,
    })
    denied = p.promote("wheel", actor="system", reason="automatic request")
    assert denied["promoted"] is False
    assert "explicit human canary approval missing" in denied["blockers"]
    allowed = p.promote("wheel", actor="risk-officer", reason="signed review",
                        human_approved=True)
    assert allowed["promoted"] is True


def test_demotion_is_immediate_and_audited(tmp_path):
    p = pipeline(tmp_path)
    p.register("spread", "Credit Spread")
    p.database.update_promotion_candidate("spread", stage="shadow")
    result = p.demote("spread", actor="risk-engine", reason="drawdown breach",
                      target_stage="paper")
    assert result["demoted"] is True
    assert p.snapshot()["candidates"][0]["stage"] == "paper"
    assert p.snapshot()["audit"][0]["action"] == "demotion"


def test_unknown_candidate_and_invalid_demotion_fail_closed(tmp_path):
    p = pipeline(tmp_path)
    with pytest.raises(KeyError):
        p.promote("missing", actor="x", reason="x")
    p.register("x", "X")
    with pytest.raises(ValueError):
        p.demote("x", actor="x", reason="x", target_stage="research")
