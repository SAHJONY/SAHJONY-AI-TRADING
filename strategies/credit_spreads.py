"""Credit Spread Desk — defined-risk options (bull put spreads).

Sell an OTM put (~SPREAD_SHORT_OTM_PCT below spot) and BUY a further-OTM put
(~SPREAD_WIDTH_PCT lower) on the same expiry. The long leg caps the downside:

    max loss / contract = (width − net credit) × 100      ← capital at risk
    max gain / contract = net credit × 100                 ← if spot ≥ short strike

Compared with the wheel's cash-secured puts this is far more capital-efficient
(risk = spread width, not full strike collateral) and the worst case is known
to the dollar before entry — the Risk Officer gates on that exact number.

Entry: council long + conviction ≥ floor + options favorability (IV worth
selling). Resolution is broker-driven in live/paper; in offline-sim we mirror
expiry with the same countdown the wheel uses (SIM_OPT_CYCLES) and settle the
spread against the spot price: worthless above the short strike (keep credit),
max loss below the long strike, linear in between.

Pure decision engine per house rules: reads state + market + council, emits
OrderIntents, never touches the broker or DB.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config import Config
from intelligence.agents import CouncilVerdict, MarketSnapshot
from strategies.base import OrderIntent

SIM_OPT_CYCLES = 2  # sim-only: cycles until an open spread resolves (matches wheel)


def _nearest_contract(chain: List[Dict], target_strike: float, kind: str) -> Optional[Dict]:
    cands = [c for c in chain if c["type"] == kind and c.get("mid", 0) > 0]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(c["strike"] - target_strike))


class CreditSpreads:
    name = "Credit Spread Desk"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def decide(self, symbol: str, snap: MarketSnapshot, pos: Optional[Dict],
               council: CouncilVerdict, budget: float, chain: List[Dict]) -> List[OrderIntent]:
        stage = (pos or {}).get("stage", "flat")
        if pos is None or stage in ("flat", None):
            return self._open(symbol, snap, council, budget, chain)
        if stage == "put_spread":
            return self._resolve(symbol, snap, pos)
        return []

    # ── entry: sell the spread when the council is constructive and IV pays ──────
    def _open(self, symbol, snap, council, budget, chain) -> List[OrderIntent]:
        if council.conviction < self.cfg.min_council_conviction or council.direction != "long":
            return []
        if council.options_favorability < 0.4:
            return [OrderIntent(symbol, "spread", "state", "spread_wait",
                                reason=f"IV-rank {council.options_favorability:.0%} too low to sell premium")]
        spot = snap.price
        short_otm = self.cfg.spread_short_otm_pct
        short_put = _nearest_contract(chain, spot * (1 - short_otm), "put")
        long_put = _nearest_contract(chain, spot * (1 - short_otm - self.cfg.spread_width_pct), "put")
        if not short_put or not long_put or long_put["strike"] >= short_put["strike"]:
            return [OrderIntent(symbol, "spread", "state", "spread_wait",
                                reason="no viable strike pair for a put spread")]
        credit = max(0.0, short_put["mid"] - long_put["mid"])
        width = short_put["strike"] - long_put["strike"]
        max_loss = (width - credit) * 100          # per contract — the true capital at risk
        if credit <= 0 or max_loss <= 0:
            return [OrderIntent(symbol, "spread", "state", "spread_wait",
                                reason="spread priced with no edge (credit/width degenerate)")]
        contracts = int(budget // max_loss)
        if contracts < 1:
            return [OrderIntent(symbol, "spread", "state", "spread_skip",
                                reason=f"budget ${budget:,.0f} < ${max_loss:,.0f} max-loss/contract")]
        net_credit = credit * 100 * contracts
        return [
            OrderIntent(
                symbol, "spread", "option", "open_spread_short", side="sell_to_open",
                reason=(f"bull put spread {short_put['strike']:.0f}/{long_put['strike']:.0f}P "
                        f"{short_put['expiry']} · credit ${net_credit:,.0f} · "
                        f"max loss ${max_loss * contracts:,.0f}"),
                qty=contracts, contract=short_put["contract"], strike=short_put["strike"],
                premium=short_put["mid"],
                est_notional=max_loss * contracts, risk_check=True,
                premium_delta=short_put["mid"] * 100 * contracts,
                set_position={"strategy": "spread", "stage": "put_spread", "shares": 0,
                              "cost_basis": 0.0, "contract": short_put["contract"],
                              "short_strike": short_put["strike"], "long_strike": long_put["strike"],
                              "expiry": short_put["expiry"], "contracts": contracts,
                              "cycles_remaining": SIM_OPT_CYCLES, "net_credit": net_credit}),
            # the hedge leg CAPS the loss — it reduces risk, so it is not risk-gated
            OrderIntent(
                symbol, "spread", "option", "open_spread_hedge", side="buy_to_open",
                reason=f"hedge leg {long_put['strike']:.0f}P (caps loss at the width)",
                qty=contracts, contract=long_put["contract"], strike=long_put["strike"],
                premium=long_put["mid"],
                est_notional=0.0, risk_check=False,
                premium_delta=-long_put["mid"] * 100 * contracts),
        ]

    # ── expiry: settle the spread against spot (sim mirror of broker resolution) ─
    def _resolve(self, symbol, snap, pos) -> List[OrderIntent]:
        remaining = int(pos.get("cycles_remaining", 0))
        if remaining > 1:
            return [OrderIntent(symbol, "spread", "state", "spread_hold",
                                reason=f"put spread open, {remaining - 1} cycle(s) to expiry",
                                merge_position={"cycles_remaining": remaining - 1})]
        contracts = int(pos.get("contracts", 1))
        ss = float(pos.get("short_strike", snap.price))
        ls = float(pos.get("long_strike", ss))
        credit = float(pos.get("net_credit", 0.0))
        width = max(0.0, ss - ls)
        px = snap.price
        if px >= ss:
            realized = credit
            note = f"expired worthless, kept ${credit:,.0f} credit"
        elif px <= ls:
            realized = credit - width * 100 * contracts
            note = f"max loss hit (spot {px:.2f} ≤ {ls:.0f}P), net ${realized:,.0f}"
        else:
            realized = credit - (ss - px) * 100 * contracts
            note = f"partial (spot {px:.2f} inside spread), net ${realized:,.0f}"
        return [OrderIntent(symbol, "spread", "state", "spread_settle",
                            reason=note, realized_delta=realized, clear_position=True)]
