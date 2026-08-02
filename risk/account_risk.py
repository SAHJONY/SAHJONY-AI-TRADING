from __future__ import annotations

import math
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

        policy = {
            "max_risk": account.max_risk,
            "max_position": account.max_position,
            "max_daily_loss": account.max_daily_loss,
        }
        for name, value in policy.items():
            if not math.isfinite(value) or value <= 0 or value > 1:
                return self._block(account, f"invalid account {name}")

        values = {
            "equity": equity,
            "proposed notional": proposed_notional,
            "daily pnl": daily_pnl,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                return self._block(account, f"invalid {name}")

        if equity <= 0:
            return self._block(account, "non-positive equity")

        if proposed_notional < 0:
            return self._block(account, "negative proposed notional")

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
