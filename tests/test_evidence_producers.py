from datetime import datetime, timedelta, timezone
import json

import pytest

from database.db import Database
from intelligence.promotion_pipeline import PromotionPipeline
from promotion.artifacts import (BacktestEvidenceProducer, CanaryEvidenceProducer,
                                 ShadowEvidenceProducer, artifact_digest,
                                 canonical_json)


METRICS = {"observations": 150, "sharpe": 0.8, "max_drawdown": 0.05,
           "data_quality": 0.995, "operational_health": 0.99,
           "calibration_error": 0.08}


def pipeline(tmp_path, **kwargs):
    p = PromotionPipeline(Database(str(tmp_path / "db.sqlite")), **kwargs)
    p.register("model", "Model", "model")
    return p


def test_canonical_serialization_and_unique_monotonic_envelopes(tmp_path):
    fixed = datetime(2026, 7, 14, tzinfo=timezone.utc)
    producer = ShadowEvidenceProducer(queue_dir=tmp_path, clock=lambda: fixed)
    first = producer.emit("model", METRICS)
    second = producer.emit("model", METRICS)
    assert first["artifact_id"] != second["artifact_id"]
    assert first["timestamp"] < second["timestamp"]
    assert first["digest"] == artifact_digest(first)
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert first["signature"] is None


def test_key_rotation_signature_mismatch_and_allowlist_fail_closed(tmp_path):
    producer = ShadowEvidenceProducer(queue_dir=tmp_path / "q", signing_keys={"k2": "new"},
                                      active_key_id="k2")
    item = producer.emit("model", METRICS)
    p = pipeline(tmp_path, artifact_signing_keys={"k1": "old", "k2": "new"},
                 require_signatures=True)
    assert p.ingest_artifact(item)["signed"] is True
    bad = dict(item, artifact_id="different", signature="0" * 64)
    bad["digest"] = artifact_digest(bad)
    with pytest.raises(ValueError, match="signature verification"):
        p.ingest_artifact(bad)
    denied = dict(item, artifact_id="denied", source="untrusted")
    denied["digest"] = artifact_digest(denied)
    with pytest.raises(ValueError, match="allowlisted"):
        p.ingest_artifact(denied)


def test_wal_retry_is_idempotent_and_duplicate_delivery_is_safe(tmp_path):
    producer = ShadowEvidenceProducer(queue_dir=tmp_path / "q")
    item = producer.emit("model", METRICS)
    attempts = []
    def flaky(artifact):
        attempts.append(artifact["artifact_id"])
        if len(attempts) == 1:
            raise RuntimeError("offline")
        return "ok"
    with pytest.raises(RuntimeError):
        producer.deliver(item, flaky)
    assert producer.health()["pending"] == 1
    assert producer.retry(flaky) == ["ok"]
    assert producer.health()["pending"] == 0

    p = pipeline(tmp_path / "ingest")
    first = p.ingest_artifact(item)
    duplicate = p.ingest_artifact(item)
    assert first["duplicate"] is False and duplicate["duplicate"] is True


def test_stale_and_non_monotonic_artifacts_are_rejected(tmp_path):
    p = pipeline(tmp_path, max_artifact_age_seconds=60)
    old = ShadowEvidenceProducer(queue_dir=tmp_path / "old").emit(
        "model", METRICS, timestamp=datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(ValueError, match="stale"):
        p.ingest_artifact(old)

    now = datetime.now(timezone.utc)
    producer = ShadowEvidenceProducer(queue_dir=tmp_path / "new")
    later = producer.emit("model", METRICS, timestamp=now)
    assert p.ingest_artifact(later)["verified"]
    earlier = ShadowEvidenceProducer(queue_dir=tmp_path / "other").emit(
        "model", METRICS, timestamp=now - timedelta(seconds=1))
    with pytest.raises(ValueError, match="monotonic"):
        p.ingest_artifact(earlier)


def test_all_stage_producers_have_no_execution_authority(tmp_path):
    assert BacktestEvidenceProducer(queue_dir=tmp_path / "b").health()["execution_authority"] is False
    assert CanaryEvidenceProducer(queue_dir=tmp_path / "c").health()["execution_authority"] is False
