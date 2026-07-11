from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AccountProfile:
    id: str
    display_name: str
    enabled: bool
    broker: str
    asset_class: str
    strategy: str
    execution_mode: str
    live_requested: bool
    adapter_ready: bool
    symbols: list[str]
    max_risk: float
    max_position: float
    max_daily_loss: float
    paper: bool


class AccountOrchestrator:
    def __init__(self, path: str = "accounts.yaml"):
        self.path = Path(path)
        self.accounts = self._load()

    def _load(self) -> list[AccountProfile]:
        if not self.path.exists():
            return []

        data = yaml.safe_load(self.path.read_text()) or {}
        accounts: list[AccountProfile] = []

        for raw in data.get("accounts", []):
            accounts.append(
                AccountProfile(
                    id=raw["id"],
                    display_name=raw.get("display_name", raw["id"]),
                    enabled=bool(raw.get("enabled", True)),
                    broker=raw["broker"],
                    asset_class=raw.get("asset_class", "unknown"),
                    strategy=raw.get("strategy", "balanced"),
                    execution_mode=raw.get("execution_mode", "monitor_only"),
                    live_requested=bool(raw.get("live_requested", False)),
                    adapter_ready=bool(raw.get("adapter_ready", False)),
                    symbols=list(raw.get("symbols", [])),
                    max_risk=float(raw.get("max_risk", 0.01)),
                    max_position=float(raw.get("max_position", 0.10)),
                    max_daily_loss=float(raw.get("max_daily_loss", 0.05)),
                    paper=bool(raw.get("paper", True)),
                )
            )

        return accounts

    def enabled_accounts(self) -> list[AccountProfile]:
        return [a for a in self.accounts if a.enabled]

    def executable_accounts(self) -> list[AccountProfile]:
        return [
            a for a in self.enabled_accounts()
            if a.execution_mode == "api" and a.adapter_ready
        ]

    def monitor_only_accounts(self) -> list[AccountProfile]:
        return [
            a for a in self.enabled_accounts()
            if a.execution_mode == "monitor_only" or not a.adapter_ready
        ]

    def accounts_for_broker(self, broker: str) -> list[AccountProfile]:
        return [a for a in self.enabled_accounts() if a.broker == broker]

    def can_execute(self, account_id: str) -> bool:
        for account in self.accounts:
            if account.id == account_id:
                return (
                    account.enabled
                    and account.execution_mode == "api"
                    and account.adapter_ready
                )
        return False

    def risk_cap_for(self, account_id: str) -> dict[str, Any]:
        for account in self.accounts:
            if account.id == account_id:
                return {
                    "max_risk": account.max_risk,
                    "max_position": account.max_position,
                    "max_daily_loss": account.max_daily_loss,
                    "paper": account.paper,
                }
        raise ValueError(f"Unknown account_id: {account_id}")

    def summary(self) -> dict[str, Any]:
        return {
            "count": len(self.accounts),
            "enabled": len(self.enabled_accounts()),
            "accounts": [
                {
                    "id": a.id,
                    "display_name": a.display_name,
                    "broker": a.broker,
                    "asset_class": a.asset_class,
                    "strategy": a.strategy,
                    "execution_mode": a.execution_mode,
                    "live_requested": a.live_requested,
                    "adapter_ready": a.adapter_ready,
                    "symbols": a.symbols,
                    "paper": a.paper,
                    "max_risk": a.max_risk,
                    "max_position": a.max_position,
                    "max_daily_loss": a.max_daily_loss,
                }
                for a in self.accounts
            ],
        }
