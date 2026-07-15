"""Scheduled, broker-free monitoring for promotion evidence producers.

This module observes producer WAL health and freshness only. It has no broker,
order, portfolio, or execution imports and can never arm Canary or Production.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
from urllib import request

from promotion.artifacts import producer_health


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ProducerAlert:
    code: str
    severity: str
    message: str
    observed_at: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_health(
    health: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_pending: int = 25,
    max_freshness_seconds: int = 3600,
    max_delivery_lag_seconds: int = 3600,
) -> list[ProducerAlert]:
    """Convert producer health into deterministic, fail-closed alerts."""
    now = (now or _utc_now()).astimezone(timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")
    alerts: list[ProducerAlert] = []
    pending = int(health.get("pending", 0) or 0)
    if pending > max_pending:
        alerts.append(ProducerAlert(
            "queue_backlog", "critical",
            f"promotion evidence queue backlog is {pending}, above limit {max_pending}",
            stamp, {"pending": pending, "limit": max_pending},
        ))
    if health.get("last_error"):
        alerts.append(ProducerAlert(
            "producer_error", "critical", "promotion evidence producer reported an error",
            stamp, {"error": str(health.get("last_error"))[:500]},
        ))
    fresh = _parse_ts(health.get("freshness_timestamp"))
    if fresh is None:
        alerts.append(ProducerAlert(
            "no_evidence", "warning", "no promotion evidence has been emitted",
            stamp, {},
        ))
    else:
        age = max(0.0, (now - fresh).total_seconds())
        if age > max_freshness_seconds:
            alerts.append(ProducerAlert(
                "stale_evidence", "critical",
                f"latest promotion evidence is {int(age)} seconds old",
                stamp, {"age_seconds": int(age), "limit": max_freshness_seconds},
            ))
    delivered = _parse_ts(health.get("last_delivered_at"))
    if pending and delivered is not None:
        lag = max(0.0, (now - delivered).total_seconds())
        if lag > max_delivery_lag_seconds:
            alerts.append(ProducerAlert(
                "delivery_stalled", "critical",
                f"pending evidence has not been delivered for {int(lag)} seconds",
                stamp, {"lag_seconds": int(lag), "limit": max_delivery_lag_seconds},
            ))
    return alerts


def build_status(queue_dir: str | Path = "data/promotion_queue", **thresholds: Any) -> dict[str, Any]:
    health = producer_health(queue_dir)
    alerts = evaluate_health(health, **thresholds)
    return {
        "ts": _utc_now().isoformat().replace("+00:00", "Z"),
        "component": "promotion-evidence-producers",
        "healthy": not any(a.severity == "critical" for a in alerts),
        "health": health,
        "alerts": [a.to_dict() for a in alerts],
        "canary_enabled": False,
        "production_enabled": False,
        "execution_authority": False,
    }


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def send_webhook(payload: Mapping[str, Any], url: str, *, timeout: int = 10) -> None:
    body = json.dumps(dict(payload), sort_keys=True).encode()
    req = request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"alert webhook returned HTTP {response.status}")


def publish_status(
    *,
    queue_dir: str | Path = "data/promotion_queue",
    status_path: str | Path = "public/promotion_producers.json",
    alert_sink: Callable[[Mapping[str, Any]], Any] | None = None,
    **thresholds: Any,
) -> dict[str, Any]:
    payload = build_status(queue_dir, **thresholds)
    atomic_write_json(status_path, payload)
    if payload["alerts"] and alert_sink is not None:
        alert_sink(payload)
    return payload
