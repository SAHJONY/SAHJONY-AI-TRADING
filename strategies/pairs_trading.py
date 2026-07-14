"""Pairs Desk — market-neutral statistical arbitrage on cointegrated pairs.

The one strategy class the desk lacked: profit from RELATIVE mispricing while
staying hedged against market direction. For each configured pair "A:B"
(default SPY:QQQ and GLD:SLV — structurally related instruments):

  entry   Engle-Granger cointegration (intelligence/engines.py) confirms the
          pair is tradeable AND the spread z-score stretches beyond PAIRS_ENTRY_Z
          → SHORT the rich leg, LONG the cheap leg, ~equal notional per leg.
  exit    spread reverts (|z| ≤ PAIRS_EXIT_Z) → close both legs, book the P&L.
  stop    spread keeps diverging (|z| ≥ PAIRS_STOP_Z) or the trade ages past
          PAIRS_MAX_HOLD cycles → cut it; cointegration may have broken.
  orphan  if one leg ever exists without its partner (partial fill), the desk
          closes the survivor immediately — it never runs an unhedged leg.

Legs are stored under their REAL symbols with strategy "pairs" (short leg =
negative shares, marked to market naturally); the core desks skip any symbol
the Pairs Desk owns. Both legs are risk-gated, whole shares only (Alpaca does
not short fractionals). Pure decision engine per house rules: no broker, no DB.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config import Config
from strategies.base import OrderIntent

_MIN_HISTORY = 60      # closes needed before the desk will judge a pair


def _pnl(pos: Dict, price: float) -> float:
    """Signed-shares mark-out: works for longs (+q) and shorts (-q) alike."""
    shares = float(pos.get("shares", 0) or 0)
    return shares * (price - float(pos.get("cost_basis", 0.0)))


class PairsDesk:
    name = "Pairs / StatArb Desk"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.entry_z = float(getattr(cfg, "pairs_entry_z", 2.0))
        self.exit_z = float(getattr(cfg, "pairs_exit_z", 0.5))
        self.stop_z = float(getattr(cfg, "pairs_stop_z", 4.0))
        self.max_hold = int(getattr(cfg, "pairs_max_hold", 96))

    def decide(self, sym_a: str, sym_b: str, price_a: float, price_b: float,
               pos_a: Optional[Dict], pos_b: Optional[Dict],
               budget: float, coint: Dict[str, float]) -> List[OrderIntent]:
        """coint: output of engines.cointegration(closes_a, closes_b) —
        {'hedge_ratio','spread_z','adf','cointegrated'}. budget = total for the
        pair (split ~half per leg)."""
        a_ours = bool(pos_a) and pos_a.get("strategy") == "pairs"
        b_ours = bool(pos_b) and pos_b.get("strategy") == "pairs"

        # ── orphan leg: never run unhedged ──
        if a_ours != b_ours:
            leg, sym, px = (pos_a, sym_a, price_a) if a_ours else (pos_b, sym_b, price_b)
            return self._close_leg(sym, leg, px, "orphan leg — partner missing, closing")

        # ── open position: manage the spread ──
        if a_ours and b_ours:
            return self._manage(sym_a, sym_b, price_a, price_b, pos_a, pos_b, coint)

        # ── flat: look for an entry ──
        # never fight another desk for a symbol
        if pos_a is not None or pos_b is not None:
            return []
        z = float(coint.get("spread_z", 0.0))
        if not coint.get("cointegrated"):
            return []
        if abs(z) < self.entry_z:
            return [OrderIntent(sym_a, "pairs", "state", "pairs_wait",
                                reason=f"{sym_a}/{sym_b} z {z:+.2f} inside ±{self.entry_z} band")]
        if price_a <= 0 or price_b <= 0 or budget <= 0:
            return []
        per_leg = budget / 2.0
        qty_a = int(per_leg // price_a)
        qty_b = int(per_leg // price_b)
        if qty_a < 1 or qty_b < 1:
            return [OrderIntent(sym_a, "pairs", "state", "pairs_skip",
                                reason=f"budget ${budget:,.0f} can't fund whole shares of both legs")]
        # z > 0: A rich vs B → short A, long B. z < 0: the reverse.
        (s_sym, s_px, s_qty), (l_sym, l_px, l_qty) = (
            ((sym_a, price_a, qty_a), (sym_b, price_b, qty_b)) if z > 0
            else ((sym_b, price_b, qty_b), (sym_a, price_a, qty_a)))
        pair, entry_note = f"{sym_a}|{sym_b}", f"z {z:+.2f} (enter ±{self.entry_z})"
        return [
            OrderIntent(l_sym, "pairs", "equity", "pairs_open_long", side="buy",
                        reason=f"stat-arb LONG cheap leg · {entry_note}",
                        qty=l_qty, est_notional=l_px * l_qty, risk_check=True,
                        set_position={"strategy": "pairs", "shares": l_qty,
                                      "cost_basis": l_px, "pair": pair,
                                      "entry_z": round(z, 3), "cycles_held": 0}),
            OrderIntent(s_sym, "pairs", "equity", "pairs_open_short", side="sell",
                        reason=f"stat-arb SHORT rich leg · {entry_note}",
                        qty=s_qty, est_notional=s_px * s_qty, risk_check=True,
                        set_position={"strategy": "pairs", "shares": -s_qty,
                                      "cost_basis": s_px, "pair": pair,
                                      "entry_z": round(z, 3), "cycles_held": 0}),
        ]

    # ── manage an open spread ────────────────────────────────────────────────────
    def _manage(self, sym_a, sym_b, price_a, price_b, pos_a, pos_b, coint) -> List[OrderIntent]:
        z = float(coint.get("spread_z", 0.0))
        held = int(pos_a.get("cycles_held", 0)) + 1
        total = _pnl(pos_a, price_a) + _pnl(pos_b, price_b)
        if abs(z) <= self.exit_z:
            why = f"spread reverted (z {z:+.2f}) — take ${total:,.0f}"
        elif abs(z) >= self.stop_z:
            why = f"spread blown out (z {z:+.2f} ≥ {self.stop_z}) — stop, ${total:,.0f}"
        elif held >= self.max_hold:
            why = f"max hold {self.max_hold} cycles — time stop, ${total:,.0f}"
        else:
            return [OrderIntent(sym_a, "pairs", "state", "pairs_hold",
                                reason=f"z {z:+.2f}, P&L ${total:,.0f}, cycle {held}",
                                merge_position={"cycles_held": held}),
                    OrderIntent(sym_b, "pairs", "state", "pairs_hold_leg",
                                reason="", merge_position={"cycles_held": held})]
        out = self._close_leg(sym_a, pos_a, price_a, why)
        out += self._close_leg(sym_b, pos_b, price_b, "")
        # realized P&L booked once, on the first closing intent
        if out:
            out[0].realized_delta = total
        return out

    @staticmethod
    def _close_leg(sym: str, pos: Dict, price: float, why: str) -> List[OrderIntent]:
        shares = float(pos.get("shares", 0) or 0)
        if not shares:
            return [OrderIntent(sym, "pairs", "state", "pairs_clean",
                                reason=why or "empty leg", clear_position=True)]
        side = "sell" if shares > 0 else "buy"   # buy back the short, sell the long
        return [OrderIntent(sym, "pairs", "equity", "pairs_close", side=side,
                            reason=why or f"close {sym} pairs leg",
                            qty=abs(shares), est_notional=0.0, risk_check=False,
                            clear_position=True)]
