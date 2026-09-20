"""Regime-aware council calibration.

Extends intel/council_calibration.py: instead of one GLOBAL accuracy memory
per agent, this module keeps TWO per-agent memories — one for calm regimes,
one for stressed regimes — because trend agents win in trends while
mean-reversion agents win in ranges, and one blended weight hides that.

HOW THE REGIME FOR A HISTORICAL CALL IS DETERMINED
-------------------------------------------------
At record time (inside ``grade_and_record``, when this cycle's per-agent calls
are stored for grading next cycle), we evaluate the SAME 2-state Gaussian
regime model the council uses (``intelligence.engines.regime_model``) on the
log-returns series of the snapshot the agent actually evaluated
(``engines.log_returns(snap.closes)``), take its hard ``state`` (0 = calm,
1 = stressed), and store that label alongside the prediction in
``state['regime_cal']['pred'][symbol][agent] = {dir, price, regime}``.
At grade time (next cycle) the stored label decides which (agent, regime)
accuracy cell receives the decayed update. The regime that matters is the one
prevailing when the call was EMITTED — not the regime at grade time, which is
contaminated by the very move being graded.

The global memory from CouncilCalibration is kept untouched and is graded in
parallel, so the global weights remain EXACTLY what council_calibration.py
produced — they are the fallback whenever the current regime is unknown.

Safety properties (identical to council_calibration.py):
- Weights only RESCALE influence in [0.5, 1.5]; never change a verdict's
  sign, never widen conviction bounds, never touch risk caps.
- Neutral (1.0) until _MIN_OBS graded calls PER (agent, regime) CELL.
- Exponential decay on every cell; deadband abstentions (|score| < _DEADBAND)
  are never graded; any failure degrades to 1.0 / global weights, never raises.
- Memory bounded: prediction store capped, accuracy store pruned to the two
  regime labels.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from intel.council_calibration import (
    _DEADBAND,
    _DECAY,
    _MIN_OBS,
    _W_MAX,
    _W_MIN,
    _direction,
    _finite,
    CouncilCalibration,
)
from utils.logger import get_logger

log = get_logger("regime_cal")

REGIMES = ("calm", "stressed")
_MAX_PRED_SYMBOLS = 128  # bound the prediction store (tickers are far fewer)


def current_regime(snap: Any) -> Optional[str]:
    """Regime label for a snapshot: 'calm' | 'stressed' | None.

    Runs intelligence.engines.regime_model on the snapshot's log-returns and
    returns the hard state. None on any failure (regime unknown -> the caller
    must fall back to the global weights).
    """
    try:
        from intelligence import engines
        closes = getattr(snap, "closes", None)
        if closes is None:
            return None
        reg = engines.regime_model(engines.log_returns(closes))
        return "stressed" if int(reg.get("state", 0)) == 1 else "calm"
    except Exception:
        return None


class RegimeCalibration:
    """Wraps CouncilCalibration with per-regime accuracy memories.

    Drop-in compatible with CouncilCalibration: ``enabled``,
    ``grade_and_record(state, research)``, ``weights(state)`` and
    ``accuracy(state)`` delegate to the global tracker unchanged, while the
    wrapper additionally maintains per-regime cells and exposes
    ``weights_for_regime(state, regime)``.
    """

    def __init__(self, cfg=None, base: Optional[CouncilCalibration] = None):
        self.base = base if base is not None else CouncilCalibration(cfg)
        self.enabled = bool(self.base.enabled)
        regime_off = False
        try:
            import os
            regime_off = str(os.getenv("COUNCIL_REGIME_CALIBRATION_ENABLED", "1")
                             ).strip().lower() in ("0", "false", "no", "off")
        except Exception:
            pass
        self.regime_enabled = (not regime_off
                               and bool(getattr(cfg, "council_regime_calibration_enabled", True)))

    # ── per-cycle: global grading (delegated) + per-regime grading ───────────
    def grade_and_record(self, state: Dict[str, Any],
                         research: List[Dict[str, Any]]) -> Dict[str, float]:
        """Grade previous calls (global + per-regime) and record current calls.

        Returns the GLOBAL weights — identical contract to
        CouncilCalibration.grade_and_record. Fault-isolated: never raises.
        """
        try:
            out = self.base.grade_and_record(state, research)
        except Exception as exc:  # calibration never breaks the cycle
            log.warning("regime calibration: global grading skipped: %s", exc)
            out = {}
        try:
            if self.regime_enabled and isinstance(state, dict):
                self._grade_regime(state, research or [])
        except Exception as exc:
            log.warning("regime calibration grading skipped: %s", exc)
        return out

    def _grade_regime(self, state: Dict[str, Any], research: List[Dict[str, Any]]) -> None:
        mem = state.setdefault("regime_cal", {})
        acc: Dict[str, Dict[str, Dict[str, float]]] = mem.setdefault("acc", {})
        prev: Dict[str, Dict[str, Dict[str, Any]]] = mem.get("pred") or {}

        for r in research or []:
            if not isinstance(r, dict):
                continue
            sym = str(r.get("symbol") or "?")
            verdict = r.get("verdict")
            verdicts = list(getattr(verdict, "verdicts", []) or [])
            snap = r.get("snap")
            price = _finite(getattr(snap, "price", 0.0))
            regime_now = current_regime(snap)
            # Grade each agent's previous call into its recorded regime cell.
            for v in verdicts:
                name = str(getattr(v, "name", "?"))
                old = (prev.get(sym) or {}).get(name)
                if not old or price <= 0 or _finite(old.get("price")) <= 0:
                    continue
                want = old.get("dir")
                if want not in ("long", "short"):
                    continue
                regime = old.get("regime")
                if regime not in REGIMES:
                    continue  # no known regime at emit time -> global memory only
                realized = price / _finite(old.get("price")) - 1.0
                if not math.isfinite(realized):
                    continue
                correct = realized > 0 if want == "long" else realized < 0
                cell = (acc.setdefault(regime, {})).get(name, {"n": 0.0, "h": 0.0})
                cell["n"] = _finite(cell.get("n")) * _DECAY + 1.0
                cell["h"] = _finite(cell.get("h")) * _DECAY + (1.0 if correct else 0.0)
                acc[regime][name] = cell
            # Record this cycle's calls (with emit-time regime) for next time.
            sym_preds: Dict[str, Dict[str, Any]] = {}
            for v in verdicts:
                d = _direction(_finite(getattr(v, "score", 0.0)))
                if d is None:
                    continue  # deadband abstention: no call, no grade
                entry: Dict[str, Any] = {"dir": d, "price": price}
                if regime_now is not None:
                    entry["regime"] = regime_now
                sym_preds[str(getattr(v, "name", "?"))] = entry
            prev[sym] = sym_preds
        # bound the memory: keep the most recent symbols, prune unknown regimes
        if len(prev) > _MAX_PRED_SYMBOLS:
            for sym in list(prev.keys())[:len(prev) - _MAX_PRED_SYMBOLS]:
                del prev[sym]
        for regime in list(acc.keys()):
            if regime not in REGIMES:
                del acc[regime]
        mem["pred"] = prev

    # ── bounded regime-conditional weights ────────────────────────────────────
    def weights_for_regime(self, state: Any, regime: Any) -> Dict[str, float]:
        """Per-agent weight map for the given regime ('calm' | 'stressed').

        Each (agent, regime) cell stays neutral (1.0) until _MIN_OBS graded
        calls. Unknown / unavailable regime falls back EXACTLY to the global
        weights (no behavior change). Never raises.
        """
        try:
            if regime not in REGIMES:
                return self.base.weights(state)
            cells = ((state.get("regime_cal") or {}).get("acc") or {}).get(regime) or {}
            out: Dict[str, float] = {}
            for name, m in cells.items():
                n = _finite(m.get("n"))
                if n < _MIN_OBS:
                    out[str(name)] = 1.0
                    continue
                rate = _finite(m.get("h")) / n
                # 50% hit-rate => 1.0; map [0,1] accuracy onto [0.5, 1.5] linearly.
                out[str(name)] = round(max(_W_MIN, min(_W_MAX, 0.5 + rate)), 3)
            return out
        except Exception:
            return {}

    def weights_by_regime(self, state: Any) -> Dict[str, Dict[str, float]]:
        """Both regime weight maps; convenience for the per-cycle snapshot."""
        return {"calm": self.weights_for_regime(state, "calm"),
                "stressed": self.weights_for_regime(state, "stressed")}

    # ── delegated global contract (unchanged behavior) ────────────────────────
    def weights(self, state: Any) -> Dict[str, float]:
        try:
            return self.base.weights(state)
        except Exception:
            return {}

    def accuracy(self, state: Any) -> Dict[str, float]:
        try:
            return self.base.accuracy(state)
        except Exception:
            return {}

    def regime_accuracy(self, state: Any) -> Dict[str, Dict[str, float]]:
        """Realized hit-rate per (regime, agent), for dashboard / self-review."""
        try:
            acc = (state.get("regime_cal") or {}).get("acc") or {}
            out: Dict[str, Dict[str, float]] = {}
            for regime, cells in acc.items():
                if regime not in REGIMES:
                    continue
                out[str(regime)] = {
                    str(n): round(_finite(m.get("h")) / max(1e-9, _finite(m.get("n"))), 3)
                    for n, m in cells.items() if _finite(m.get("n")) >= _MIN_OBS
                }
            return out
        except Exception:
            return {}
