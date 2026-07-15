"""Publish a secret-free dashboard snapshot from the local read-only MCP gateway."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.request import Request, urlopen

from dotenv import load_dotenv


def _get(base_url: str, token: str, path: str, timeout: int) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured gateway
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"gateway {path} returned a non-object response")
    return payload


def build_snapshot(
    health: dict[str, Any], account: dict[str, Any], positions: dict[str, Any]
) -> dict[str, Any]:
    last4 = str(account.get("account_number_last4", ""))[-4:]
    health_last4 = str(health.get("account_number_last4", ""))[-4:]
    if not health.get("ok") or not health.get("read_only"):
        raise RuntimeError("gateway is not healthy and read-only")
    if not health.get("identity_verified") or last4 != health_last4:
        raise RuntimeError("gateway account identity is not verified")
    if len(last4) != 4 or not last4.isdigit():
        raise RuntimeError("gateway did not provide a valid masked account suffix")

    rows = []
    for item in positions.get("positions", []):
        qty = float(item.get("qty", 0) or 0)
        market_value = float(item.get("market_value", 0) or 0)
        rows.append({
            "symbol": str(item.get("symbol", "")).upper(),
            "shares": qty,
            "avg_cost": float(item.get("avg_entry_price", 0) or 0),
            "price": abs(market_value / qty) if qty else 0.0,
            "market_value": market_value,
            "unrealized": 0.0,
            "asset_type": str(item.get("asset_type", "equity")),
        })

    equity = float(account.get("equity", 0) or 0)
    cash = float(account.get("cash", 0) or 0)
    buying_power = float(account.get("buying_power", 0) or 0)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    agentic = {
        "connected": True, "ok": True, "read_only": True,
        "identity_verified": True, "account_number_last4": last4,
        "account_type": str(account.get("account_type", "Agentic")),
        "status": str(account.get("status", "active")),
        "equity": equity, "cash": cash, "buying_power": buying_power,
        "positions": rows, "updated": now,
    }
    return {
        "schema_version": 2, "updated": now,
        "source": "robinhood-trading-mcp", "broker": "Robinhood",
        "live": True, "read_only": True, "account_mask": f"••••{last4}",
        "nickname": "Agentic", "total_value": equity, "equity_value": equity,
        "cash": cash, "buying_power": buying_power,
        "committed_open_orders": 0.0, "positions": rows, "orders": [],
        "agentic": agentic,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish read-only Robinhood MCP dashboard data")
    parser.add_argument("--output", default="public/robinhood.json")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    load_dotenv()
    base_url = os.getenv("ROBINHOOD_MCP_GATEWAY_URL", "http://127.0.0.1:8787").strip()
    token = os.getenv("ROBINHOOD_MCP_GATEWAY_TOKEN", "").strip()
    if not token:
        parser.error("ROBINHOOD_MCP_GATEWAY_TOKEN is required")
    snapshot = build_snapshot(
        _get(base_url, token, "/health", args.timeout),
        _get(base_url, token, "/account", args.timeout),
        _get(base_url, token, "/positions", args.timeout),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=output.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(snapshot, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        temp_path = Path(tmp.name)
    temp_path.replace(output)
    runtime_url = os.getenv("RUNTIME_STATUS_URL", "").strip()
    runtime_token = os.getenv("RUNTIME_STATUS_PUBLISH_TOKEN", "").strip()
    if runtime_url or runtime_token:
        if not runtime_url or not runtime_token:
            raise RuntimeError("both RUNTIME_STATUS_URL and RUNTIME_STATUS_PUBLISH_TOKEN are required")
        hosted = {**snapshot, "execution_authority": False}
        request = Request(runtime_url, data=json.dumps(hosted).encode(), method="POST", headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "Authorization": f"Bearer {runtime_token}",
        })
        with urlopen(request, timeout=args.timeout) as response:  # noqa: S310 - configured endpoint
            if response.status != 202:
                raise RuntimeError(f"runtime publisher returned HTTP {response.status}")
    print(f"Published read-only snapshot for Agentic ••••{snapshot['agentic']['account_number_last4']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
