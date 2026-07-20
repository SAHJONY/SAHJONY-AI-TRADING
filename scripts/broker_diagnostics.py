#!/usr/bin/env python3
"""Collect a redacted, read-only Robinhood MCP diagnostics snapshot.

This utility never calls order, preview, modify, or cancel endpoints. It reads the
local loopback gateway only and publishes an operations-safe JSON artifact.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    dotenv_values = None

READ_ONLY_PATHS = ("/health", "/account", "/positions")
DEFAULT_SYMBOLS = ("VTI", "QQQ", "NVDA", "MSFT")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _config() -> dict[str, str]:
    file_values = dotenv_values(ROOT / ".env") if dotenv_values else {}
    def value(name: str, default: str = "") -> str:
        return str(os.getenv(name) or file_values.get(name) or default).strip()
    return {
        "url": value("ROBINHOOD_MCP_GATEWAY_URL", "http://127.0.0.1:8787").rstrip("/"),
        "token": value("ROBINHOOD_MCP_GATEWAY_TOKEN"),
        "expected_last4": value("ROBINHOOD_MCP_EXPECTED_LAST4", "1131"),
        "symbols": value("TICKERS", ",".join(DEFAULT_SYMBOLS)),
    }


def _get(base: str, token: str, path: str, timeout: float = 60.0) -> tuple[int, Any]:
    request = Request(base + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            payload = {"error": body[:500]}
        return exc.code, payload
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def collect() -> dict[str, Any]:
    cfg = _config()
    snapshot: dict[str, Any] = {
        "ts": _iso_now(),
        "mode": "read-only-diagnostics",
        "execution_authority": False,
        "gateway": {"url": cfg["url"], "reachable": False},
        "identity": {"expected_last4": cfg["expected_last4"], "verified": False},
        "account": None,
        "positions": None,
        "quotes": {},
        "reconciliation": {"status": "unavailable", "blockers": []},
    }
    if not cfg["token"]:
        snapshot["reconciliation"]["blockers"].append("gateway token missing")
        return snapshot

    health_status, health = _get(cfg["url"], cfg["token"], "/health")
    snapshot["gateway"].update(status=health_status, reachable=health_status == 200, health=health)
    actual_last4 = str(health.get("account_number_last4", "")) if isinstance(health, dict) else ""
    snapshot["identity"].update(
        actual_last4=actual_last4 or None,
        verified=bool(health_status == 200 and health.get("identity_verified") and actual_last4 == cfg["expected_last4"]),
    )

    account_status, account = _get(cfg["url"], cfg["token"], "/account")
    snapshot["account"] = {"http_status": account_status, "data": account}
    positions_status, positions = _get(cfg["url"], cfg["token"], "/positions")
    snapshot["positions"] = {"http_status": positions_status, "data": positions}

    symbols = [s.strip().upper() for s in cfg["symbols"].split(",") if s.strip()]
    for symbol in symbols:
        status, payload = _get(cfg["url"], cfg["token"], f"/quotes/{quote(symbol, safe='')}")
        snapshot["quotes"][symbol] = {"http_status": status, "data": payload}

    blockers: list[str] = []
    if not snapshot["identity"]["verified"]:
        blockers.append("account identity not verified")
    if account_status != 200:
        blockers.append("account endpoint unavailable")
    if positions_status != 200:
        blockers.append("positions endpoint unavailable")
    elif isinstance(positions, dict) and not positions.get("positions"):
        blockers.append("broker reports no visible positions")
    failed_quotes = [symbol for symbol, result in snapshot["quotes"].items() if result["http_status"] != 200]
    if failed_quotes:
        blockers.append("quote failures: " + ", ".join(failed_quotes))

    snapshot["reconciliation"] = {
        "status": "blocked" if blockers else "observed",
        "blockers": blockers,
        "trading_ready": False,
        "reason": "read-only adapter has no execution authority",
    }
    return snapshot


def main() -> int:
    output = ROOT / "public" / "broker_diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = collect()
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0 if snapshot["gateway"]["reachable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
