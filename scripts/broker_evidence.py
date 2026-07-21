#!/usr/bin/env python3
"""Collect immutable private broker evidence and publish a redacted projection."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from observability.broker_evidence import (build_mcp_evidence, evidence_digest, parse_ui_observation,
                                           reconcile_evidence)
from scripts import broker_diagnostics


def _atomic_json(path: Path, payload: dict[str, Any], *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if private:
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def collect_mcp() -> tuple[Any, list[str]]:
    cfg = broker_diagnostics._config()
    blockers: list[str] = []
    if not cfg["token"]:
        return None, ["gateway token missing"]
    health_status, health = broker_diagnostics._get(cfg["url"], cfg["token"], "/health", timeout=90)
    account_status, account = broker_diagnostics._get(cfg["url"], cfg["token"], "/account", timeout=90)
    positions_status, positions = broker_diagnostics._get(
        cfg["url"], cfg["token"], "/positions", timeout=285
    )
    if health_status != 200 or account_status != 200 or positions_status != 200:
        return None, ["authenticated MCP account or positions evidence unavailable"]
    if not isinstance(health, dict) or not isinstance(account, dict):
        return None, ["authenticated MCP account evidence is invalid"]
    if not isinstance(positions, dict) or not isinstance(positions.get("positions"), list):
        return None, ["authenticated MCP positions evidence is invalid"]
    verified = bool(isinstance(health, dict) and health.get("identity_verified")
                    and str(health.get("account_number_last4", ""))[-4:] == cfg["expected_last4"])
    try:
        evidence = build_mcp_evidence(
            account, positions["positions"],
            observed_at=datetime.now(timezone.utc).isoformat(), identity_verified=verified,
            expected_last4=cfg["expected_last4"],
        )
    except (TypeError, ValueError) as exc:
        return None, [str(exc)]
    return evidence, blockers


def produce(*, ui_path: Path | None = None, public_path: Path | None = None,
            private_dir: Path | None = None, now: datetime | None = None,
            value_tolerance: float = 1.0, max_age_seconds: int = 900) -> dict[str, Any]:
    mcp, collection_blockers = collect_mcp()
    ui = None
    ui_error = None
    if ui_path:
        try:
            ui = parse_ui_observation(json.loads(ui_path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            ui_error = f"manual evidence unavailable: {exc}"
    extra = tuple([*collection_blockers, *([ui_error] if ui_error else [])])
    report = reconcile_evidence(mcp, ui, now=now, value_tolerance=value_tolerance,
                                max_age_seconds=max_age_seconds, evidence_blockers=extra)
    private = report.private_dict()
    public = json.loads(json.dumps(private))
    if public.get("ui"):
        public["ui"]["human_notes"] = "[REDACTED]" if ui and ui.human_notes else ""
    if public.get("mcp"):
        public["mcp"]["account_last4"] = str(public["mcp"]["account_last4"])[-4:]
    public["execution_authority"] = False
    public["trading_armed"] = False
    public["trading_ready"] = False
    public_target = public_path or ROOT / "public" / "broker_evidence.json"
    evidence_dir = private_dir or ROOT / "data" / "broker_evidence"
    private_target = evidence_dir / f"{report.report_digest}.json"
    if private_target.exists():
        existing = json.loads(private_target.read_text(encoding="utf-8"))
        if existing != private:
            raise RuntimeError("immutable private evidence digest collision")
    else:
        _atomic_json(private_target, private, private=True)
    _atomic_json(public_target, public)
    return public


def publish_hosted(report: dict[str, Any], *, timeout: int = 30) -> bool:
    url = os.getenv("BROKER_EVIDENCE_API_URL", "").strip()
    if not url:
        runtime_url = os.getenv("RUNTIME_STATUS_URL", "").strip()
        if runtime_url.endswith("/runtime-status"):
            url = runtime_url.removesuffix("/runtime-status") + "/broker-evidence"
    token = (os.getenv("BROKER_EVIDENCE_PUBLISH_TOKEN", "").strip()
             or os.getenv("RUNTIME_STATUS_PUBLISH_TOKEN", "").strip())
    if not url and not token:
        return False
    if not url or not token:
        raise RuntimeError("broker evidence publication URL and token must both be configured")
    req = Request(url, data=json.dumps(report, separators=(",", ":")).encode(), method="POST",
                  headers={"Accept": "application/json", "Content-Type": "application/json",
                           "Authorization": f"Bearer {token}"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - configured hosted endpoint
        if response.status != 202:
            raise RuntimeError(f"broker evidence publisher returned HTTP {response.status}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce read-only dual-source broker evidence")
    parser.add_argument("--ui-observation", type=Path)
    parser.add_argument("--public-output", type=Path)
    parser.add_argument("--private-dir", type=Path)
    parser.add_argument("--value-tolerance", type=float, default=1.0)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--digest-manual", type=Path,
                        help="print the SHA-256 digest for a manual JSON object and exit")
    args = parser.parse_args()
    if args.digest_manual:
        raw = json.loads(args.digest_manual.read_text(encoding="utf-8"))
        print(evidence_digest(raw))
        return 0
    report = produce(ui_path=args.ui_observation, public_path=args.public_output,
                     private_dir=args.private_dir, value_tolerance=args.value_tolerance,
                     max_age_seconds=args.max_age_seconds)
    publish_hosted(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "RECONCILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
