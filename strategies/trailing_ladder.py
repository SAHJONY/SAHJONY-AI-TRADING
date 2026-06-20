"""Trailing-Ladder long-equity strategy.

Three behaviors:
  • Hard catastrophic floor — liquidate if price falls below the floor.
  • Ratchet trailing stop — once up RATCHET_TRIGGER (10%), trail TRAIL_PCT (5%)
    below the running peak; liquidate if breached (locks in gains).
  • Ladder-in averaging — add LADDER_BASE_QTY shares at -20% and 2× at -30%.

Reconciliation: a literal reading of the spec puts a -10% hard stop AND -20%/-30%
adds on the same position, which is contradictory (the stop fires before the
adds). With LADDER_ENABLE_AVERAGING on (default), the floor is the deeper
LADDER_CATASTROPHIC_PCT so the rungs can fill; with it off, the -10% stop applies
and there is no averaging-in. Both regimes are implemented and configurable.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config import Config
from intelligence.agents import CouncilVerdict, MarketSnapshot
from strategies.base import OrderIntent


class TrailingLadder:
    name = "Equity Ladder Desk"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def decide(self, symbol: str, snap: MarketSnapshot, pos: Optional[Dict],
               council: CouncilVerdict, budget: float) -> List[OrderIntent]:
        if pos is None or pos.get("shares", 0) <= 0:
            return self._enter(symbol, snap, council, budget)
        return self._manage(symbol, snap, pos, budget)

    def _enter(self, symbol, snap, council, budget) -> List[OrderIntent]:
        if council.conviction < self.cfg.min_council_conviction or council.direction != "long":
            return []
        price = snap.price
        if price <= 0 or budget <= 0:
            return []
        qty = min(self.cfg.ladder_base_qty, int(budget // price))
        if qty < 1:
            return [OrderIntent(symbol, "ladder", "state", "ladder_skip",
                                reason=f"budget ${budget:,.0f} < 1 share @ {price:.2f}")]
        floor_pct = (self.cfg.ladder_catastrophic_pct if self.cfg.ladder_enable_averaging
                     else self.cfg.ladder_hard_floor_pct)
        return [OrderIntent(
            symbol, "ladder", "equity", "ladder_entry", side="buy",
            reason=f"open {qty} sh @ {price:.2f}, floor {floor_pct:.0%}",
            qty=qty, est_notional=qty * price, risk_check=True,
            set_position={"strategy": "ladder", "shares": qty, "entry_price": price,
                          "cost_basis": price, "peak_price": price, "ratcheted": False,
                          "trailing_floor": None, "hard_floor": price * (1 - floor_pct),
                          "rungs_hit": [False, False]})]

    def _manage(self, symbol, snap, pos, budget) -> List[OrderIntent]:
        price = snap.price
        entry = float(pos.get("entry_price", price))
        shares = int(pos.get("shares", 0))
        cost = float(pos.get("cost_basis", entry))
        peak = max(float(pos.get("peak_price", price)), price)
        ratcheted = bool(pos.get("ratcheted", False))
        trailing_floor = pos.get("trailing_floor", None)
        hard_floor = float(pos.get("hard_floor", entry * (1 - self.cfg.ladder_hard_floor_pct)))
        rungs = list(pos.get("rungs_hit", [False, False]))
        gain = price / entry - 1.0 if entry else 0.0

        # --- ratchet the trailing stop on the upside ---
        if not ratcheted and gain >= self.cfg.ladder_ratchet_trigger_pct:
            ratcheted = True
            trailing_floor = peak * (1 - self.cfg.ladder_trail_pct)
        if ratcheted:
            trailing_floor = max(float(trailing_floor or 0.0), peak * (1 - self.cfg.ladder_trail_pct))

        # --- EXITS (checked before adds) ---
        if ratcheted and price <= float(trailing_floor):
            realized = (price - cost) * shares
            return [OrderIntent(symbol, "ladder", "equity", "trail_exit", side="sell",
                                reason=f"trail stop {trailing_floor:.2f} hit, realize ${realized:,.0f}",
                                qty=shares, est_notional=0.0, risk_check=False,
                                realized_delta=realized, clear_position=True)]
        if price <= hard_floor:
            realized = (price - cost) * shares
            label = "catastrophic_floor" if self.cfg.ladder_enable_averaging else "hard_stop"
            return [OrderIntent(symbol, "ladder", "equity", label, side="sell",
                                reason=f"{label} {hard_floor:.2f} hit, realize ${realized:,.0f}",
                                qty=shares, est_notional=0.0, risk_check=False,
                                realized_delta=realized, clear_position=True)]

        # --- LADDER-IN averaging on the downside ---
        intents: List[OrderIntent] = []
        new_shares, new_cost = shares, cost
        if self.cfg.ladder_enable_averaging and not ratcheted:
            adds = [(-0.20, 0, self.cfg.ladder_base_qty), (-0.30, 1, 2 * self.cfg.ladder_base_qty)]
            for threshold, idx, add_qty in adds:
                if gain <= threshold and not rungs[idx] and price > 0:
                    q = min(add_qty, int(budget // price))
                    if q >= 1:
                        new_cost = (new_cost * new_shares + price * q) / (new_shares + q)
                        new_shares += q
                        rungs[idx] = True
                        intents.append(OrderIntent(
                            symbol, "ladder", "equity", "ladder_add", side="buy",
                            reason=f"rung {idx+1}: +{q} sh @ {price:.2f} (dd {gain:+.0%})",
                            qty=q, est_notional=q * price, risk_check=True))

        # --- persist bookkeeping (peak / ratchet / trailing / rungs / averaged basis) ---
        intents.append(OrderIntent(
            symbol, "ladder", "state", "ladder_update",
            reason=f"px {price:.2f} peak {peak:.2f} gain {gain:+.0%}"
                   + (f" trail {float(trailing_floor):.2f}" if ratcheted else ""),
            merge_position={"shares": new_shares, "cost_basis": new_cost, "peak_price": peak,
                            "ratcheted": ratcheted, "trailing_floor": trailing_floor,
                            "rungs_hit": rungs}))
        return intents
