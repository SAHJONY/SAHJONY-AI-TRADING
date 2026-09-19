"""Regime classification + regime-conditional strategy gating.

The council already computes everything this needs (`stressed_prob`,
`composite_score`, `direction`, `vol`) — but until now the regime read was
advisory: it sat in the portfolio dict for the AI brain and changed nothing.
This module turns it into a real gate with three effects:

1. **Entries** — each regime scales the new-position budget (reduction-only).
   `stressed` blocks new entries outright; exits always flow.
2. **Desk selection** — each regime allowlists which strategy desks may OPEN
   risk. A bear market is no place for selling cash-secured puts; a stressed
   tape is no place for anything new.
3. **Sizing** — bear/chop halve budgets on top of every other scaler.

Fail-closed: an unreadable or missing regime read degrades to "chop"
(half size, restricted desks), never to "bull". Unknown strategy ids are
denied. Nothing here can raise.

Regimes:
  bull     — trend with the council, low stress. Full size, all desks.
  bear     — council bearish (composite <= -0.25). Half size; only
             market-neutral / short-capable desks (pairs, day).
  chop     — flat and noisy. Half size; mean-reversion-friendly desks.
  stressed — stressed_prob >= 0.5. No new entries; exits flow.
"""
from __future__ import annotations

import math
from typing import Dict, Tuple

from utils.logger import get_logger

log = get_logger("regime")

BULL = "bull"
BEAR = "bear"
CHOP = "chop"
STRESSED = "stressed"
REGIMES = (BULL, BEAR, CHOP, STRESSED)

# Reduction-only budget scale per regime. Stressed = 0: no new entries.
REGIME_ENTRY_SCALE: Dict[str, float] = {
    BULL: 1.0,
    BEAR: 0.5,
    CHOP: 0.5,
    STRESSED: 0.0,
}

# Desks allowed to OPEN new risk per regime. Everything not listed may only
# exit. "copy" mirrors an external feed with its own protective exits and is
# allowed wherever entries are allowed at all; it stays out of bear/stressed
# because a mirrored long into a falling tape is the failure mode.
# "promoted" covers research strategies running as live desks
# (strategies/promoted.py) — intraday BTC strategies, long/short by design.
REGIME_STRATEGIES: Dict[str, frozenset] = {
    BULL: frozenset({"wheel", "ladder", "spread", "day", "pairs", "copy", "promoted"}),
    BEAR: frozenset({"pairs", "day", "promoted"}),
    CHOP: frozenset({"pairs", "day", "ladder", "copy", "promoted"}),
    STRESSED: frozenset(),
}

# Composite-score thresholds on the council's [-1, 1] scale.
_BEAR_COMPOSITE = -0.25
_BULL_COMPOSITE = 0.15


def classify_regime(metrics: Dict, direction: str = "",
                    composite: float = 0.0) -> str:
    """Classify the per-symbol regime from council outputs. Never raises."""
    try:
        m = metrics or {}
        stressed = float(m.get("stressed_prob", 0.0) or 0.0)
        if math.isfinite(stressed) and stressed >= 0.5:
            return STRESSED
        comp = float(composite or 0.0)
        if not math.isfinite(comp):
            comp = 0.0
        d = str(direction or "").strip().lower()
        if comp <= _BEAR_COMPOSITE:
            return BEAR
        if d == "long" or comp >= _BULL_COMPOSITE:
            return BULL
        return CHOP
    except Exception as exc:      # fail-closed: unknown → chop (half size)
        log.warning("regime classification failed (%s) — degrading to chop", exc)
        return CHOP


def gate(regime: str, strategy_id: str) -> Tuple[float, bool]:
    """Return (budget_scale, entries_allowed) for a desk in a regime.

    Unknown regimes or strategy ids deny: (0.0, False)."""
    if regime not in REGIME_ENTRY_SCALE:
        return 0.0, False
    allowed = strategy_id in REGIME_STRATEGIES.get(regime, frozenset())
    scale = REGIME_ENTRY_SCALE[regime] if allowed else 0.0
    return scale, allowed


def describe(regime: str) -> str:
    return {
        BULL: "bull — full size, all desks",
        BEAR: "bear — half size, pairs/day only",
        CHOP: "chop — half size, mean-reversion desks",
        STRESSED: "stressed — no new entries, exits only",
    }.get(regime, "unknown — denied")
