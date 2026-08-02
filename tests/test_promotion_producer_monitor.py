from datetime import datetime, timedelta, timezone
import json

from promotion.producer_monitor import build_status, evaluate_health, publish_status


NOW = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)


def test_healthy_recent_producer_has_no_critical_alerts():
    health = {
        "pending": 0,
        "freshness_timestamp": (NOW - timedelta(minutes=5)).isoformat(),
        "last_delivered_at": (NOW - timedelta(minutes=4)).isoformat(),
        "last_error": None,
    }
    alerts = evaluate_health(health, now=NOW, max_freshness_seconds=3600)
    assert not any(a.severity == "critical" for a in alerts)


def test_backlog_and_staleness_are_critical():
    health = {
        "pending": 30,
        "freshness_timestamp": (NOW - timedelta(hours=2)).isoformat(),
        "last_delivered_at": (NOW - timedelta(hours=2)).isoformat(),
        "last_error": None,
    }
    codes = {a.code for a in evaluate_health(
        health, now=NOW, max_pending=25,
        max_freshness_seconds=3600, max_delivery_lag_seconds=3600,
    )}
    assert {"queue_backlog", "stale_evidence", "delivery_stalled"} <= codes


def test_error_is_critical_and_no_evidence_is_warning():
    alerts = evaluate_health({"pending": 0, "last_error": "disk full"}, now=NOW)
    by_code = {a.code: a.severity for a in alerts}
    assert by_code["producer_error"] == "critical"
    assert by_code["no_evidence"] == "warning"


def test_publish_status_is_broker_free_and_fail_closed(tmp_path):
    out = tmp_path / "public" / "promotion_producers.json"
    payload = publish_status(queue_dir=tmp_path / "queue", status_path=out)
    saved = json.loads(out.read_text())
    assert saved["execution_authority"] is False
    assert saved["canary_enabled"] is False
    assert saved["production_enabled"] is False
    assert payload == saved


def test_alert_sink_receives_payload(tmp_path):
    seen = []
    publish_status(queue_dir=tmp_path / "queue", status_path=tmp_path / "status.json",
                   alert_sink=seen.append)
    assert len(seen) == 1
    assert seen[0]["alerts"]
