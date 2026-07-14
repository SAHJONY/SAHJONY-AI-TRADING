"""The options Wheel — cash-secured puts → assignment → covered calls.

Stage 1: sell a cash-secured PUT ~WHEEL_PUT_OTM_PCT below market, 2-4 wk expiry.
Stage 2: if assigned (price < strike at expiry), hold the shares and sell a
         covered CALL ~WHEEL_CALL_OTM_PCT above cost basis. If called away,
         realize the gain; if it expires, keep the premium and sell another.

Option resolution is broker-driven in live/paper. In offline-sim we mirror it
with a short countdown (SIM_OPT_CYCLES) so a multi-cycle dry-run walks the full
wheel: CSP → assignment → covered call → called-away/expiry.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from config import Config
from intelligence.agents import CouncilVerdict, MarketSnapshot
from strategies.base import OrderIntent

SIM_OPT_CYCLES = 2  # sim-only: cycles until an open option resolves


def _nearest_contract(chain: List[Dict], target_strike: float, kind: str) -> Optional[Dict]:
    cands = [c for c in chain if c["type"] == kind and c.get("mid", 0) > 0]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(c["strike"] - target_strike))


class WheelStrategy:
    name = "Wheel Options Desk"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def decide(self, symbol: str, snap: MarketSnapshot, pos: Optional[Dict],
               council: CouncilVerdict, budget: float, chain: List[Dict]) -> List[OrderIntent]:
        stage = (pos or {}).get("stage", "flat")
        if stage in ("flat", None) or pos is None:
            return self._open_csp(symbol, snap, council, budget, chain)
        if stage == "short_put":
            return self._resolve_put(symbol, snap, pos)
        if stage == "long_assigned":
            return self._open_covered_call(symbol, snap, pos, chain)
        if stage == "covered_call":
            return self._resolve_call(symbol, snap, pos)
        return []

    # Stage 1 — open cash-secured put
    def _open_csp(self, symbol, snap, council, budget, chain) -> List[OrderIntent]:
        if council.conviction < self.cfg.min_council_conviction or council.direction != "long":
            return []
        if council.options_favorability < 0.4:
            return [OrderIntent(symbol, "wheel", "state", "wheel_wait",
                                reason=f"IV-rank {council.options_favorability:.0%} too low to sell premium")]
        spot = snap.price
        target = spot * (1 - self.cfg.wheel_put_otm_pct)
        put = _nearest_contract(chain, target, "put")
        if not put:
            return [OrderIntent(symbol, "wheel", "state", "wheel_wait", reason="no put contract found")]
        collateral = put["strike"] * 100
        contracts = int(budget // collateral)
        if contracts < 1:
            return [OrderIntent(symbol, "wheel", "state", "wheel_skip",
                                reason=f"budget ${budget:,.0f} < ${collateral:,.0f}/contract")]
        premium = put.get("mid", 0.0)
        return [OrderIntent(
            symbol, "wheel", "option", "open_csp", side="sell_to_open",
            reason=f"CSP {put['strike']:.0f}P {put['expiry']} (~{self.cfg.wheel_put_otm_pct:.0%} OTM)",
            qty=contracts, contract=put["contract"], strike=put["strike"], premium=premium,
            est_notional=collateral * contracts, risk_check=True,
            premium_delta=premium * 100 * contracts,
            set_position={"strategy": "wheel", "stage": "short_put", "shares": 0,
                          "cost_basis": 0.0, "contract": put["contract"], "strike": put["strike"],
                          "expiry": put["expiry"], "contracts": contracts,
                          "cycles_remaining": SIM_OPT_CYCLES,
                          "premium_open": premium * 100 * contracts}),
        ]

    def _resolve_put(self, symbol, snap, pos) -> List[OrderIntent]:
        remaining = int(pos.get("cycles_remaining", 0))
        if remaining > 1:
            return [OrderIntent(symbol, "wheel", "state", "csp_hold",
                                reason=f"short put open, {remaining-1} cycle(s) to expiry",
                                merge_position={"cycles_remaining": remaining - 1})]
        contracts = int(pos.get("contracts", 1))
        strike = float(pos.get("strike", snap.price))
        if snap.price < strike:  # assigned
            return [OrderIntent(
                symbol, "wheel", "equity", "assignment", side="buy",
                reason=f"assigned {100*contracts} sh @ {strike:.2f}",
                qty=100 * contracts, est_notional=strike * 100 * contracts, risk_check=False,
                set_position={"strategy": "wheel", "stage": "long_assigned",
                              "shares": 100 * contracts, "cost_basis": strike,
                              "contract": "", "strike": 0.0, "cycles_remaining": 0,
                              "premium_open": 0.0})]
        # Expired worthless → back to flat. The premium was already banked into
        # premium_collected when the CSP opened (open_csp.premium_delta); do NOT
        # also add it to realized_pnl here or _sleeve would count it twice.
        return [OrderIntent(symbol, "wheel", "state", "csp_expired",
                            reason=f"put expired worthless, kept ${pos.get('premium_open',0):,.0f}",
                            clear_position=True)]

    # Stage 2 — covered call
    def _open_covered_call(self, symbol, snap, pos, chain) -> List[OrderIntent]:
        shares = int(pos.get("shares", 0))
        contracts = shares // 100
        if contracts < 1:
            return [OrderIntent(symbol, "wheel", "state", "cc_skip", reason="<100 shares")]
        target = pos["cost_basis"] * (1 + self.cfg.wheel_call_otm_pct)
        call = _nearest_contract(chain, target, "call")
        if not call:
            return [OrderIntent(symbol, "wheel", "state", "cc_wait", reason="no call contract found")]
        premium = call.get("mid", 0.0)
        return [OrderIntent(
            symbol, "wheel", "option", "open_cc", side="sell_to_open",
            reason=f"covered call {call['strike']:.0f}C {call['expiry']}",
            qty=contracts, contract=call["contract"], strike=call["strike"], premium=premium,
            est_notional=0.0, risk_check=False, premium_delta=premium * 100 * contracts,
            merge_position={"stage": "covered_call", "contract": call["contract"],
                            "strike": call["strike"], "expiry": call["expiry"],
                            "cycles_remaining": SIM_OPT_CYCLES,
                            "premium_open": premium * 100 * contracts})]

    def _resolve_call(self, symbol, snap, pos) -> List[OrderIntent]:
        remaining = int(pos.get("cycles_remaining", 0))
        if remaining > 1:
            return [OrderIntent(symbol, "wheel", "state", "cc_hold",
                                reason=f"covered call open, {remaining-1} cycle(s) to expiry",
                                merge_position={"cycles_remaining": remaining - 1})]
        shares = int(pos.get("shares", 0))
        strike = float(pos.get("strike", snap.price))
        cost = float(pos.get("cost_basis", snap.price))
        if snap.price > strike:  # called away
            # Equity gain only — the call premium is already in premium_collected
            # (open_cc.premium_delta); adding premium_open here would double-count it.
            gain = (strike - cost) * shares
            return [OrderIntent(symbol, "wheel", "equity", "called_away", side="sell",
                                reason=f"called away {shares} sh @ {strike:.2f}, realize ${gain:,.0f}",
                                qty=shares, est_notional=0.0, risk_check=False,
                                realized_delta=gain, clear_position=True)]
        # Expired → keep premium (already in premium_collected), sell another call
        # next cycle. No realized_delta here — see csp_expired for the rationale.
        return [OrderIntent(symbol, "wheel", "state", "cc_expired",
                            reason=f"call expired, kept ${pos.get('premium_open',0):,.0f}",
                            merge_position={"stage": "long_assigned", "contract": "",
                                            "strike": 0.0, "cycles_remaining": 0,
                                            "premium_open": 0.0})]
