#!/usr/bin/env python3
"""Read-only readiness auditor for configured brokerage accounts.

This tool never submits, cancels, or modifies an order. It verifies that an
account is configured, that the selected adapter is online, and that the
runtime account data is consistent with the operator-approved identifiers.

Exit codes:
  0 = every enabled account is ready for its configured mode
  2 = one or more accounts are blocked/not ready
  3 = the audit itself failed
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv(".env", override=True)
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from accounts.orchestrator import AccountOrchestrator  # noqa: E402
from config import load_config  # noqa: E402
from utils.broker import get_broker  # noqa: E402


@dataclass
class AccountAudit:
    account_id: str
    display_name: str
    expected_last4: str
    broker: str
    asset_class: str
    configured_mode: str
    adapter_ready: bool
    authenticated: bool
    identity_verified: bool
    funded_or_holding_assets: bool
    trading_ready: bool
    runtime_mode: str
    runtime_account_masked: str
    buying_power: float
    holdings_count: int
    blockers: list[str]


def _mask(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return f"***{text[-4:]}"


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _crypto_runtime(broker: Any) -> tuple[bool, dict[str, Any], list[dict[str, Any]], str]:
    online = bool(getattr(broker, "online", False))
    runtime_mode = str(getattr(broker, "mode", "unknown"))
    if not online or not hasattr(broker, "_request"):
        return False, {}, [], runtime_mode

    account = broker._request("GET", "/api/v1/crypto/trading/accounts/") or {}
    holdings_payload = broker._request("GET", "/api/v1/crypto/trading/holdings/") or {}
    holdings = holdings_payload.get("results", []) if isinstance(holdings_payload, dict) else []
    return True, account, list(holdings or []), runtime_mode


def audit() -> list[AccountAudit]:
    cfg = load_config()
    orchestrator = AccountOrchestrator()
    broker = get_broker(cfg)

    approved_api_account = os.getenv("ROBINHOOD_APPROVED_API_ACCOUNT", "").strip()
    results: list[AccountAudit] = []

    crypto_authenticated, crypto_account, crypto_holdings, crypto_mode = _crypto_runtime(broker)

    for profile in orchestrator.enabled_accounts():
        blockers: list[str] = []
        authenticated = False
        identity_verified = False
        funded = False
        runtime_mode = "unavailable"
        runtime_account = ""
        buying_power = 0.0
        holdings_count = 0

        if profile.asset_class == "crypto" and profile.broker == "robinhood":
            authenticated = crypto_authenticated
            runtime_mode = crypto_mode
            runtime_account_raw = crypto_account.get("account_number", "")
            runtime_account = _mask(runtime_account_raw)
            buying_power = _to_float(crypto_account.get("buying_power"))
            holdings_count = len(crypto_holdings)
            funded = buying_power > 0 or holdings_count > 0

            if not authenticated:
                blockers.append("Robinhood Crypto API is not authenticated")
            if not approved_api_account:
                blockers.append("ROBINHOOD_APPROVED_API_ACCOUNT is not set")
            elif str(runtime_account_raw) != approved_api_account:
                blockers.append("runtime API account does not match operator-approved account")
            else:
                identity_verified = True
            if not funded:
                blockers.append("API account has zero buying power and no holdings")
            if profile.execution_mode != "api":
                blockers.append("account is not configured for API execution")
            if not profile.adapter_ready:
                blockers.append("adapter_ready is false")
            if profile.paper:
                blockers.append("account registry is still marked paper=true")
            if not cfg.robinhood_live:
                blockers.append("ROBINHOOD_LIVE is false")
            if not cfg.live_trading_ack:
                blockers.append("LIVE_TRADING_ACK is not armed")

        else:
            runtime_mode = "monitor-only"
            if profile.execution_mode != "api":
                blockers.append("account is monitor-only")
            if not profile.adapter_ready:
                blockers.append("no authenticated equity execution adapter")
            if profile.paper:
                blockers.append("account registry is still marked paper=true")
            blockers.append("RHS account number alone is not an execution credential")

        trading_ready = (
            authenticated
            and identity_verified
            and funded
            and profile.execution_mode == "api"
            and profile.adapter_ready
            and not profile.paper
            and not blockers
        )

        results.append(
            AccountAudit(
                account_id=profile.id,
                display_name=profile.display_name,
                expected_last4=profile.account_number_last4,
                broker=profile.broker,
                asset_class=profile.asset_class,
                configured_mode=profile.execution_mode,
                adapter_ready=profile.adapter_ready,
                authenticated=authenticated,
                identity_verified=identity_verified,
                funded_or_holding_assets=funded,
                trading_ready=trading_ready,
                runtime_mode=runtime_mode,
                runtime_account_masked=runtime_account,
                buying_power=buying_power,
                holdings_count=holdings_count,
                blockers=blockers,
            )
        )

    return results


def main() -> int:
    try:
        results = audit()
    except Exception as exc:
        print(json.dumps({"status": "audit_error", "error": str(exc)}, indent=2))
        return 3

    payload = {
        "status": "ready" if results and all(r.trading_ready for r in results) else "blocked",
        "safety": "read-only audit; no orders submitted",
        "accounts": [asdict(r) for r in results],
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
