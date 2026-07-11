from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from accounts.orchestrator import AccountOrchestrator, AccountProfile
from risk.account_risk import AccountRiskDecision, AccountRiskEngine
from strategies.base import OrderIntent, is_crypto


@dataclass
class RouteDecision:
    approved: bool
    reason: str
    account_id: str | None = None
    broker: str | None = None
    execution_mode: str | None = None
    risk: AccountRiskDecision | None = None


class ExecutionRouter:
    """Selects an account and applies account-level execution safeguards.

    The router never submits an order. It only decides whether an intent may be
    sent to the active broker adapter. This keeps routing policy testable and
    prevents brokerage symbols from reaching the Robinhood Crypto endpoint.
    """

    def __init__(
        self,
        orchestrator: AccountOrchestrator | None = None,
        risk_engine: AccountRiskEngine | None = None,
    ) -> None:
        self.orchestrator = orchestrator or AccountOrchestrator()
        self.risk_engine = risk_engine or AccountRiskEngine()

    @staticmethod
    def asset_class_for(symbol: str) -> str:
        return "crypto" if is_crypto(symbol) else "equity"

    def _candidate_accounts(self, symbol: str) -> list[AccountProfile]:
        asset_class = self.asset_class_for(symbol)
        return [
            account
            for account in self.orchestrator.enabled_accounts()
            if account.asset_class == asset_class and symbol in account.symbols
        ]

    def select_account(self, symbol: str) -> AccountProfile | None:
        candidates = self._candidate_accounts(symbol)
        if not candidates:
            return None

        executable = [a for a in candidates if a.execution_mode == "api"]
        if executable:
            return executable[0]

        return candidates[0]

    def decide(
        self,
        intent: OrderIntent,
        *,
        equity: float,
        buying_power: float,
        daily_pnl: float = 0.0,
    ) -> RouteDecision:
        account = self.select_account(intent.symbol)
        if account is None:
            return RouteDecision(False, "no configured account for symbol")

        if account.execution_mode != "api":
            return RouteDecision(
                False,
                "account is monitor-only",
                account_id=account.id,
                broker=account.broker,
                execution_mode=account.execution_mode,
            )

        if not self.orchestrator.can_execute(account.id):
            return RouteDecision(
                False,
                "account execution disabled",
                account_id=account.id,
                broker=account.broker,
                execution_mode=account.execution_mode,
            )

        if account.asset_class == "crypto" and not is_crypto(intent.symbol):
            return RouteDecision(False, "equity symbol cannot route to crypto account", account_id=account.id)

        if account.asset_class == "equity" and is_crypto(intent.symbol):
            return RouteDecision(False, "crypto symbol cannot route to equity account", account_id=account.id)

        if intent.risk_check and intent.est_notional > buying_power:
            return RouteDecision(
                False,
                "insufficient buying power",
                account_id=account.id,
                broker=account.broker,
                execution_mode=account.execution_mode,
            )

        risk = self.risk_engine.approve(
            account,
            equity=equity,
            proposed_notional=max(0.0, intent.est_notional),
            daily_pnl=daily_pnl,
        )
        if intent.risk_check and not risk.approved:
            return RouteDecision(
                False,
                risk.reason,
                account_id=account.id,
                broker=account.broker,
                execution_mode=account.execution_mode,
                risk=risk,
            )

        return RouteDecision(
            True,
            "approved",
            account_id=account.id,
            broker=account.broker,
            execution_mode=account.execution_mode,
            risk=risk,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "accounts": self.orchestrator.summary(),
            "executable": [a.id for a in self.orchestrator.executable_accounts()],
            "monitor_only": [a.id for a in self.orchestrator.monitor_only_accounts()],
        }
