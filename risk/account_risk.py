from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccountRiskDecision:
    approved: bool
    reason: str
    account_id: str
    max_risk: float
    max_position: float
    max_daily_loss: float
    paper: bool


class AccountRiskEngine:
    def approve(self, account, equity: float, proposed_notional: float, daily_pnl: float = 0.0) -> AccountRiskDecision:
        if not account.enabled:
            return self._block(account, "account disabled")

        if daily_pnl <= -(equity * account.max_daily_loss):
            return self._block(account, "daily loss limit hit")

        if proposed_notional > equity * account.max_position:
            return self._block(account, "position size exceeds account limit")

        if proposed_notional > equity * account.max_risk:
            return self._block(account, "trade risk exceeds account max_risk")

        return AccountRiskDecision(
            approved=True,
            reason="approved",
            account_id=account.id,
            max_risk=account.max_risk,
            max_position=account.max_position,
            max_daily_loss=account.max_daily_loss,
            paper=account.paper,
        )

    def _block(self, account, reason: str) -> AccountRiskDecision:
        return AccountRiskDecision(
            approved=False,
            reason=reason,
            account_id=account.id,
            max_risk=account.max_risk,
            max_position=account.max_position,
            max_daily_loss=account.max_daily_loss,
            paper=account.paper,
        )
