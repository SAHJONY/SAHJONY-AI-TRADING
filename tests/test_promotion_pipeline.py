import pytest
from datetime import datetime, timezone

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


def artifact(p, key="pairs", stage="shadow", **metric_overrides):
    metrics = {
        "observations": 150, "sharpe": 0.8, "max_drawdown": 0.05,
        "data_quality": 0.995, "operational_health": 0.99,
        "calibration_error": 0.08,
    }
    metrics.update(metric_overrides)
    body = {
        "artifact_id": f"{key}-{stage}-001", "candidate_key": key, "stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat(), "source": "test-harness",
        "payload": {"metrics": metrics},
    }
    body["payload_hash"] = p.artifact_hash(body)
    return body


def test_immutable_artifact_ingestion_updates_evidence(tmp_path):
    p = pipeline(tmp_path)
    p.register("pairs", "Pairs")
    item = artifact(p)
    result = p.ingest_artifact(item)
    assert result["verified"] is True
    assert result["signed"] is False
    assert result["breaches"] == []
    saved = p.snapshot()["artifacts"][0]
    assert saved["payload_hash"] == item["payload_hash"]
    assert p.database.promotion_candidate("pairs")["evidence"]["shadow_observations"] == 150
    event_count = len(p.snapshot()["audit"])
    replay = p.ingest_artifact(item)
    assert replay["duplicate"] is True
    assert replay["demotion"] is None
    assert len(p.snapshot()["audit"]) == event_count

    changed = dict(item)
    changed["payload"] = {"metrics": {**item["payload"]["metrics"], "sharpe": 9.0}}
    changed["payload_hash"] = p.artifact_hash({k: changed[k] for k in
        ("artifact_id", "candidate_key", "stage", "created_at", "source", "payload")})
    with pytest.raises(ValueError, match="different content"):
        p.ingest_artifact(changed)


def test_tampered_or_unsigned_required_artifact_is_rejected(tmp_path):
    p = pipeline(tmp_path, artifact_signing_key="secret", require_signatures=True)
    p.register("pairs", "Pairs")
    item = artifact(p)
    with pytest.raises(ValueError, match="signature required"):
        p.ingest_artifact(item)
    item["signature"] = "bad"
    with pytest.raises(ValueError, match="signature verification failed"):
        p.ingest_artifact(item)


def test_signed_artifact_covers_envelope_and_is_accepted(tmp_path):
    p = pipeline(tmp_path, artifact_signing_key="secret", require_signatures=True)
    p.register("pairs", "Pairs")
    item = artifact(p)
    content = {k: item[k] for k in
               ("artifact_id", "candidate_key", "stage", "created_at", "source", "payload")}
    item["signature"] = p.sign_artifact(content, "secret")
    item["signer"] = "research-ci"
    assert p.ingest_artifact(item)["signed"] is True
    tampered = dict(item, source="unknown")
    tampered["payload_hash"] = p.artifact_hash({k: tampered[k] for k in content})
    with pytest.raises(ValueError, match="signature verification failed"):
        p.ingest_artifact(tampered)


@pytest.mark.parametrize("metric,value,reason", [
    ("max_drawdown", 0.20, "drawdown"),
    ("calibration_error", 0.30, "calibration"),
    ("data_quality", 0.80, "data quality"),
    ("operational_health", 0.70, "operational health"),
])
def test_verified_threshold_breach_automatically_demotes(tmp_path, metric, value, reason):
    p = pipeline(tmp_path)
    p.register("pairs", "Pairs")
    p.database.update_promotion_candidate("pairs", stage="shadow")
    result = p.ingest_artifact(artifact(p, **{metric: value}))
    assert any(reason in blocker for blocker in result["breaches"])
    assert result["demotion"]["to_stage"] == "paper"
    assert p.database.promotion_candidate("pairs")["stage"] == "paper"
    assert p.snapshot()["execution_authority"] is False
