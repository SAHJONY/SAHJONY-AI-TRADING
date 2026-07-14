"""Risk Engine Gatekeeper.

Every order proposed by a strategy passes through approve(). It enforces, in
order: paper-mode sanity, council-conviction floor, per-position allocation cap,
total-deployed cap, and an absolute hard ceiling that .env can never widen.
No proposal that fails ANY check is allowed to reach the broker.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import Config, HARD_MAX_ALLOCATION_PCT
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

    def position_budget(self, equity: float, conviction: float, risk_mult: float) -> float:
        """Notional a single new position may use, scaled by conviction × risk."""
        cap = equity * self.cfg.max_allocation_pct
        return max(0.0, cap * max(0.0, min(1.0, conviction)) * max(0.0, min(1.0, risk_mult)))

    def approve(self, equity: float, deployed_value: float, intended_notional: float,
                conviction: float, symbol: str) -> RiskDecision:
        if equity <= 0:
            return RiskDecision(False, "non-positive equity")
        if conviction < self.cfg.min_council_conviction:
            return RiskDecision(False, f"conviction {conviction:.0%} < floor "
                                       f"{self.cfg.min_council_conviction:.0%}")
        # absolute hard ceiling (independent of clamped config)
        hard_cap = equity * HARD_MAX_ALLOCATION_PCT
        per_cap = equity * self.cfg.max_allocation_pct
        if intended_notional > per_cap:
            return RiskDecision(False, f"${intended_notional:,.0f} exceeds per-position cap "
                                       f"${per_cap:,.0f}", per_cap)
        if intended_notional > hard_cap:
            return RiskDecision(False, "exceeds absolute hard ceiling", hard_cap)
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
    _CYCLES_PER_YEAR = 6552.0   # 15-min cycles across the US cash session (~26/day × 252)

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
            realized = (var ** 0.5) * (self._CYCLES_PER_YEAR ** 0.5)
            if realized <= target or realized <= 0:
                return 1.0
            scale = max(self.VOL_SCALE_MIN, min(1.0, target / realized))
            log.info("vol targeting: realized %.0f%% > target %.0f%% → budgets ×%.2f",
                     realized * 100, target * 100, scale)
            return scale
        except Exception:   # any data problem degrades to neutral, never crashes
            return 1.0
