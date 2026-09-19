"""Performance-weighted council voting.

Each of the 12 council personas is a deterministic estimator — some read this
market regime well, others don't. This module tracks every agent's REALIZED
directional accuracy (did its call precede the actual move?) with exponential
decay, and converts it into a bounded per-agent vote weight in [0.5, 1.5].

Design rules (same safety envelope as Hermes):
- Weights only ever RESCALE influence; they never change a verdict's sign,
  never widen conviction bounds, never touch risk caps.
- Neutral (1.0) until _MIN_OBS graded calls — no early overfitting.
- Decayed memory: recent calls matter more; a reformed agent earns its
  influence back automatically.
- Graded calls with |score| < _DEADBAND are abstentions (no call, no grade) —
  the agent is never punished for staying neutral.
- Everything lives in state['council_cal'] (persisted with state.json);
  any failure degrades to all-weights-1.0, never a crash.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

log = get_logger("council_cal")

_DECAY = 0.97          # exponential decay on accuracy memory (recent > ancient)
_MIN_OBS = 20          # graded calls before a weight moves off neutral
_W_MIN, _W_MAX = 0.5, 1.5   # bounded influence — a bad agent halves, never vanishes
_DEADBAND = 0.05       # |score| below this = abstention, not graded


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _direction(score: float) -> Optional[str]:
    if score > _DEADBAND:
        return "long"
    if score < -_DEADBAND:
        return "short"
    return None


class CouncilCalibration:
    """Tracks per-agent realized accuracy and derives bounded vote weights."""

    def __init__(self, cfg=None):
        env_off = False
        try:
            import os
            env_off = str(os.getenv("COUNCIL_CALIBRATION_ENABLED", "1")).strip().lower() in (
                "0", "false", "no", "off")
        except Exception:
            pass
        self.enabled = not env_off and bool(getattr(cfg, "council_calibration_enabled", True))

    # ── per-cycle: grade last cycle's calls, record this cycle's ──────────────
    def grade_and_record(self, state: Dict[str, Any],
                         research: List[Dict[str, Any]]) -> Dict[str, float]:
        """Grade previous per-agent calls against realized moves, then store the
        current per-agent calls for next cycle. Returns the new weights.
        Fault-isolated: never raises."""
        try:
            mem = state.setdefault("council_cal", {})
            acc: Dict[str, Dict[str, float]] = mem.setdefault("acc", {})
            prev: Dict[str, Dict[str, Dict[str, float]]] = mem.get("pred") or {}

            for r in research:
                sym = str(r.get("symbol") or "?")
                verdict = r.get("verdict")
                verdicts = list(getattr(verdict, "verdicts", []) or [])
                snap = r.get("snap")
                price = _finite(getattr(snap, "price", 0.0))
                # Grade each agent's previous call on this symbol.
                for v in verdicts:
                    name = str(getattr(v, "name", "?"))
                    old = (prev.get(sym) or {}).get(name)
                    if not old or price <= 0 or _finite(old.get("price")) <= 0:
                        continue
                    want = old.get("dir")
                    if want not in ("long", "short"):
                        continue
                    realized = price / _finite(old.get("price")) - 1.0
                    if not math.isfinite(realized):
                        continue
                    correct = realized > 0 if want == "long" else realized < 0
                    m = acc.get(name, {"n": 0.0, "h": 0.0})
                    m["n"] = m["n"] * _DECAY + 1.0
                    m["h"] = m["h"] * _DECAY + (1.0 if correct else 0.0)
                    acc[name] = m
                # Record this cycle's per-agent calls for next time.
                sym_preds: Dict[str, Dict[str, float]] = {}
                for v in verdicts:
                    d = _direction(_finite(getattr(v, "score", 0.0)))
                    if d is None:
                        continue
                    sym_preds[str(getattr(v, "name", "?"))] = {"dir": d, "price": price}
                prev[sym] = sym_preds
            mem["pred"] = prev
            return self.weights(state)
        except Exception as exc:  # calibration never breaks the cycle
            log.warning("council calibration skipped: %s", exc)
            return {}

    # ── bounded weights ───────────────────────────────────────────────────────
    def weights(self, state: Dict[str, Any]) -> Dict[str, float]:
        """Per-agent vote weight in [_W_MIN, _W_MAX]; 1.0 until enough evidence."""
        try:
            acc = (state.get("council_cal") or {}).get("acc") or {}
            out: Dict[str, float] = {}
            for name, m in acc.items():
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

    def accuracy(self, state: Dict[str, Any]) -> Dict[str, float]:
        """Realized hit-rate per agent (for the dashboard / self-review)."""
        try:
            acc = (state.get("council_cal") or {}).get("acc") or {}
            return {str(n): round(_finite(m.get("h")) / max(1e-9, _finite(m.get("n"))), 3)
                    for n, m in acc.items() if _finite(m.get("n")) >= _MIN_OBS}
        except Exception:
            return {}
