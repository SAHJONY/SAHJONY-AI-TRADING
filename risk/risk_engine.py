"""Risk Engine Gatekeeper.

Every order proposed by a strategy passes through approve(). It enforces, in
order: paper-mode sanity, council-conviction floor, per-position allocation cap,
total-deployed cap, and an absolute hard ceiling that .env can never widen.
No proposal that fails ANY check is allowed to reach the broker.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from config import Config, HARD_MAX_ALLOCATION_PCT
from institutional_validation import DEFAULT_POLICY
from utils.logger import get_logger

log = get_logger("risk_engine")


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    max_notional: float = 0.0


class RiskEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @property
    def effective_position_cap_pct(self) -> float:
        """Position ceiling used by the actual execution gate.

        Paper/sim remain configurable research environments. In LIVE mode,
        configuration may tighten the institutional ceiling but can never widen
        beyond it. The historical hard ceiling remains in force everywhere.
        """
        configured = max(0.0, float(getattr(self.cfg, "max_allocation_pct", 0.0) or 0.0))
        baseline = min(configured, HARD_MAX_ALLOCATION_PCT)
        if str(getattr(self.cfg, "mode", "sim") or "sim").lower() == "live":
            return min(baseline, DEFAULT_POLICY.max_position_exposure_pct)
        return baseline

    def position_budget(self, equity: float, conviction: float, risk_mult: float) -> float:
        """Notional a single new position may use, scaled by conviction × risk.

        Venue minimums matter for small accounts: a sub-minimum budget is rounded
        up only when the venue minimum still fits inside the position cap.
        """
        if not all(math.isfinite(value) for value in (equity, conviction, risk_mult)):
            return 0.0
        cap_pct = self.effective_position_cap_pct
        cap = equity * cap_pct
        budget = max(0.0, cap * max(0.0, min(1.0, conviction)) * max(0.0, min(1.0, risk_mult)))
        floor = max(0.0, float(getattr(self.cfg, "min_order_notional", 0.0) or 0.0))
        if floor > 0 and 0.0 < budget < floor:
            if floor <= cap:
                log.info("budget $%.2f below the $%.2f venue minimum — sizing at the "
                         "minimum (still inside the %.0f%% per-position cap)",
                         budget, floor, cap_pct * 100)
                return floor
            log.info("budget $%.2f below the $%.2f venue minimum and the minimum "
                     "exceeds the per-position cap $%.2f — standing down",
                     budget, floor, cap)
            return 0.0
        return budget

    def approve(self, equity: float, deployed_value: float, intended_notional: float,
                conviction: float, symbol: str,
                existing_position_value: float = 0.0) -> RiskDecision:
        """Gate one exposure-adding order.

        `existing_position_value` is the gross value ALREADY held in `symbol`. It
        matters because the cap this method enforces is documented as a cap on a
        *position*, and without it the check only ever saw the increment: a desk
        that adds to the same name every cycle — the ladder averaging in, or
        copy-trading mirroring repeated filings — passes an individually-small
        order every time and compounds a position without limit. That is not
        hypothetical. desks/stocks reached 12,104 AMPY shares at a $4.08 basis
        ($49,384) on a $2,000 account whose per-position cap was $240, built out
        of orders that were each, on their own, inside the cap.

        Defaults to 0.0 so a caller that genuinely means "size this order alone"
        keeps the old behaviour.
        """
        values = {
            "equity": equity,
            "deployed value": deployed_value,
            "intended notional": intended_notional,
            "conviction": conviction,
            "existing position value": existing_position_value,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                return RiskDecision(False, f"invalid {name}")
        if equity <= 0:
            return RiskDecision(False, "non-positive equity")
        if deployed_value < 0:
            return RiskDecision(False, "negative deployed value")
        if intended_notional < 0:
            return RiskDecision(False, "negative intended notional")
        if existing_position_value < 0:
            return RiskDecision(False, "negative existing position value")
        if not symbol or not symbol.strip():
            return RiskDecision(False, "missing symbol")
        if conviction < self.cfg.min_council_conviction:
            return RiskDecision(False, f"conviction {conviction:.0%} < floor "
                                       f"{self.cfg.min_council_conviction:.0%}")

        per_cap = equity * self.effective_position_cap_pct
        resulting = existing_position_value + intended_notional
        if resulting > per_cap:
            room = max(0.0, per_cap - existing_position_value)
            return RiskDecision(False, f"${resulting:,.0f} in {symbol} would exceed the "
                                       f"per-position cap ${per_cap:,.0f} "
                                       f"(holding ${existing_position_value:,.0f}, "
                                       f"room ${room:,.0f})", room)

        total_cap = equity * self.cfg.max_total_deployed_pct
        if deployed_value + intended_notional > total_cap:
            room = max(0.0, total_cap - deployed_value)
            return RiskDecision(False, f"would breach total-deployed cap ${total_cap:,.0f} "
                                       f"(room ${room:,.0f})", room)
        return RiskDecision(True, "approved", intended_notional)

    def hard_stop_breached(self, entry_price: float, current_price: float,
                           floor_pct: float) -> bool:
        """Millennium-style hard stop-out: programmatic exit before drawdown grows."""
        if entry_price <= 0:
            return False
        return (current_price / entry_price - 1.0) <= -abs(floor_pct)

    # Vol targeting can trim budgets to at most half — it de-risks, never leverages
    # up (scale is capped at 1.0), and the hard ceilings above still apply on top.
    VOL_SCALE_MIN = 0.50
    # Fallback only. The live factor comes from cfg.cycles_per_year, which tracks
    # the ACTUAL cadence and calendar — a hardcoded cash-session figure understated
    # a 24/7 crypto desk's realized vol by ~2.3x, leaving this rail nearly inert.
    _CYCLES_PER_YEAR = 6552.0   # 15-min cycles across the US cash session (~26/day × 252)

    @property
    def _cycles_per_year(self) -> float:
        try:
            value = float(getattr(self.cfg, "cycles_per_year", 0.0) or 0.0)
        except (TypeError, ValueError):
            return self._CYCLES_PER_YEAR
        return value if value > 0 else self._CYCLES_PER_YEAR

    def vol_scalar(self, equity_values) -> float:
        """Volatility targeting: when the desk's REALIZED portfolio vol runs above
        VOL_TARGET_ANNUAL, scale every new-position budget down proportionally
        (target/realized, clamped to [0.5, 1.0]). Classic institutional practice:
        risk is sized to the environment, not just to conviction. Neutral (1.0)
        when disabled (target 0), on short history, or on any data problem."""
        target = float(getattr(self.cfg, "vol_target_annual", 0.0) or 0.0)
        if target <= 0:
            return 1.0
        try:
            ys = [float(v) for v in (equity_values or []) if v and float(v) > 0]
            if len(ys) < 12:
                return 1.0
            ys = ys[-60:]
            rets = [ys[i] / ys[i - 1] - 1.0 for i in range(1, len(ys))]
            n = len(rets)
            mean = sum(rets) / n
            var = sum((r - mean) ** 2 for r in rets) / max(1, n - 1)
            realized = (var ** 0.5) * (self._cycles_per_year ** 0.5)
            if realized <= target or realized <= 0:
                return 1.0
            scale = max(self.VOL_SCALE_MIN, min(1.0, target / realized))
            log.info("vol targeting: realized %.0f%% > target %.0f%% → budgets ×%.2f",
                     realized * 100, target * 100, scale)
            return scale
        except Exception:   # any data problem degrades to neutral, never crashes
            return 1.0
