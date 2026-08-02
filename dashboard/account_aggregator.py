from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json
import yaml

from accounts.orchestrator import AccountOrchestrator


@dataclass
class DashboardAccount:
    id: str
    display_name: str
    account_type: str
    source: str
    connection_status: str
    portfolio_value: float
    buying_power: float
    day_change: float
    day_change_pct: float
    positions: list[dict[str, Any]]
    execution_mode: str
    live_requested: bool
    adapter_ready: bool


class AccountDashboardAggregator:
    def __init__(
        self,
        balances_path: str = "data/account_balances.yaml",
        output_path: str = "public/accounts_status.json",
    ) -> None:
        self.balances_path = Path(balances_path)
        self.output_path = Path(output_path)
        self.orchestrator = AccountOrchestrator()

    def _load_snapshot(self) -> dict[str, Any]:
        if not self.balances_path.exists():
            return {"accounts": [], "banking": {}, "portfolio": {}}
        return yaml.safe_load(self.balances_path.read_text()) or {}

    def _crypto_snapshot(self, broker) -> dict[str, Any]:
        try:
            account = broker.get_account()
            positions = broker.get_broker_positions()
            return {
                "portfolio_value": float(account.get("equity", 0.0) or 0.0),
                "buying_power": float(account.get("buying_power", 0.0) or 0.0),
                "connection_status": "live_data" if getattr(broker, "online", False) else "offline",
                "positions": [{"symbol": symbol, **position} for symbol, position in positions.items()],
            }
        except Exception as exc:
            return {
                "portfolio_value": 0.0,
                "buying_power": 0.0,
                "connection_status": "error",
                "positions": [],
                "error": str(exc),
            }

    def build(self, broker=None) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        source_accounts = {item["id"]: item for item in snapshot.get("accounts", [])}

        if broker is not None and "robinhood_crypto" in source_accounts:
            source_accounts["robinhood_crypto"].update(self._crypto_snapshot(broker))

        accounts: list[DashboardAccount] = []
        warnings: list[str] = []

        for profile in self.orchestrator.enabled_accounts():
            raw = source_accounts.get(profile.id, {})
            live_requested = bool(raw.get("live_requested", getattr(profile, "live_requested", False)))
            adapter_ready = bool(raw.get("adapter_ready", getattr(profile, "adapter_ready", False)))
            execution_mode = profile.execution_mode

            if live_requested and not adapter_ready:
                warnings.append(f"{profile.id}: live execution requested but no supported adapter is configured")

            accounts.append(
                DashboardAccount(
                    id=profile.id,
                    display_name=raw.get("display_name", getattr(profile, "display_name", profile.id)),
                    account_type=profile.asset_class,
                    source=raw.get("source", profile.broker),
                    connection_status=raw.get("connection_status", execution_mode),
                    portfolio_value=float(raw.get("portfolio_value", 0.0) or 0.0),
                    buying_power=float(raw.get("buying_power", 0.0) or 0.0),
                    day_change=float(raw.get("day_change", 0.0) or 0.0),
                    day_change_pct=float(raw.get("day_change_pct", 0.0) or 0.0),
                    positions=list(raw.get("positions", [])),
                    execution_mode=execution_mode,
                    live_requested=live_requested,
                    adapter_ready=adapter_ready,
                )
            )

        banking = snapshot.get("banking", {})
        banking_balance = float(banking.get("balance", 0.0) or 0.0)
        accounts_value = sum(account.portfolio_value for account in accounts)
        calculated_total = accounts_value + banking_balance
        displayed_total = float(snapshot.get("portfolio", {}).get("displayed_total", calculated_total))
        reconciliation_difference = round(displayed_total - calculated_total, 2)

        if abs(reconciliation_difference) >= 0.01:
            warnings.append(f"portfolio reconciliation difference: {reconciliation_difference:+.2f}")

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "accounts": [asdict(account) for account in accounts],
            "banking": banking,
            "totals": {
                "accounts_value": round(accounts_value, 2),
                "banking_value": round(banking_balance, 2),
                "calculated_total": round(calculated_total, 2),
                "displayed_total": round(displayed_total, 2),
                "reconciliation_difference": reconciliation_difference,
                "total_buying_power": round(sum(account.buying_power for account in accounts), 2),
            },
            "routing": self.orchestrator.summary(),
            "warnings": warnings,
        }

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(result, indent=2))
        return result
