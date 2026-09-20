"""Learn-while-halted: the shadow-decision ledger.

When the desk is halted or stood down to dry-run (kill switch, daily circuit
breaker, self-heal circuit breaker / 3-strike escalation, cadence guard, LIVE
reconciliation failure), the strategy desks still compute entry intents and
``ExecutionTrader.execute`` suppresses them at the HALT BLOCK branch. Without
this module those would-be orders vanish: only a ``halt_block`` event with
``{symbol, purpose}`` remains, so the desk can never grade what it WOULD have
done and the learning loop goes blind for the whole stand-down.

This module closes that hole, and NOTHING else:

1. RECORD — at the suppression point, the intended action is persisted as a
   paper decision to a JSONL shadow ledger: symbol, side, size, price,
   conviction, contributing engine scores, rationale snapshot. Unknowns are
   recorded as ``"unknown"`` — never invented.
2. GRADE — when subsequent price data arrives, each shadow decision is graded
   against the realized move (same 1-cycle-forward style as the council
   calibration's grade-and-record), into bounded, decayed per-strategy stats.

HARD SAFETY PROPERTIES (asserted by tests/test_learn_while_halted.py):
- This module CANNOT emit a real order. It imports no broker client, defines
  no submit/place/order-emission function, and knows no credentials. The only
  write it performs is appending JSON lines to its own ledger file. The
  recording hook sits in execute()'s HALT BLOCK branch, which ends with
  ``continue`` — order submission is textually and logically unreachable.
- It never clears the circuit breaker, never re-arms any feed, never changes
  live trading behavior, order emission, risk caps, or the halt/dry-run
  decision itself. Measurement and grading only.
- Keyless: grading reuses the desk's own price accessor (no new network, no
  new credentials). Everything is fault-isolated — any failure degrades to a
  skipped record/grade, never a raised exception into the trading loop.
- Bounded: in-memory window capped, per-cycle grading work capped, JSONL
  append guarded by a file-size ceiling, stats exponentially decayed like
  council_calibration (recent evidence outweighs ancient).

Env gating: SHADOW_LEARNING_ENABLED (default ON) + cfg.shadow_learning_enabled.
"""
from __future__ import annotations

import json
import math
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from paths import home
from utils.logger import get_logger

log = get_logger("shadow_learning")

_DECAY = 0.97          # same decay convention as council_calibration
_MIN_OBS = 20          # graded decisions before a strategy's accuracy is quoted
_MEM_CAP = 2000        # in-memory decision window (JSONL is the durable trail)
_MAX_GRADE_PER_CYCLE = 200   # bounded grading work per cycle
_MAX_GRADED_IDS = 5000       # bounded graded-id memory in state
_MAX_PER_CYCLE = 64          # cap records per cycle (halt-storm guard)
_LEDGER_MAX_BYTES = 8 * 1024 * 1024  # stop appending past 8 MB, warn loudly
_UNKNOWN = "unknown"

# side -> directional sign for grading. Sides not listed here cannot be signed
# honestly, so those decisions are marked graded with correct=None (ungradable).
_SIDE_SIGN = {
    "buy": 1.0, "buy_to_open": 1.0, "sell_to_close": 1.0,
    "sell": -1.0, "sell_to_open": -1.0, "buy_to_close": -1.0,
}

# Tokens that must NEVER appear in this module: it has no order-emission path.
_FORBIDDEN_TOKENS = ("submit_equity_order", "submit_option_order",
                     "submit_order", "place_order")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _side_sign(side: Any) -> float:
    return _SIDE_SIGN.get(str(side or "").strip().lower(), 0.0)


class ShadowLearning:
    """Paper-decision recorder + grader for halted/dry-run cycles."""

    def __init__(self, cfg=None, path: Optional[str] = None):
        self.path = path or os.path.join(home(), "data", "shadow_decisions.jsonl")
        env_off = str(os.getenv("SHADOW_LEARNING_ENABLED", "1")).strip().lower() in (
            "0", "false", "no", "off")
        self.enabled = (not env_off
                        and bool(getattr(cfg, "shadow_learning_enabled", True)))
        self._decisions: deque = deque(maxlen=_MEM_CAP)  # newest at the right
        self._seq = 0
        self._per_cycle_counts: Dict[int, int] = {}
        try:
            self._load_tail()
        except Exception as exc:
            log.warning("shadow ledger tail load skipped: %s", exc)

    # ── recording ─────────────────────────────────────────────────────────────
    def record_shadow(self, *, intent: Any, state: Optional[Dict[str, Any]],
                      cycle: int, conviction: float = 0.0,
                      halt: Optional[Dict[str, Any]] = None,
                      get_price: Optional[Callable[[str], Any]] = None,
                      mode: str = "") -> Dict[str, Any]:
        """Persist one suppressed order intent as a paper decision.

        Called ONLY from execute()'s HALT BLOCK branch (the point where the
        order would have been emitted but the halt suppressed it). Returns the
        recorded decision dict, or {} when disabled/skipped. NEVER raises and
        NEVER emits an order — the only side effect is a JSONL append.
        """
        try:
            if not self.enabled:
                return {}
            cyc = int(cycle or 0)
            if self._per_cycle_counts.get(cyc, 0) >= _MAX_PER_CYCLE:
                return {}  # halt-storm guard
            symbol = str(getattr(intent, "symbol", "") or _UNKNOWN)
            side = str(getattr(intent, "side", "") or _UNKNOWN)
            ctx = ((state or {}).get("_shadow_ctx") or {}).get(symbol) or {}
            price = 0.0
            if get_price is not None:
                try:
                    price = _finite(get_price(symbol))
                except Exception:
                    price = 0.0
            halt = halt or {}
            self._seq += 1
            dec: Dict[str, Any] = {
                "id": f"shdw-{cyc:06d}-{self._seq:04d}",
                "ts": _now(),
                "cycle": cyc,
                "mode": str(mode or ""),
                "halt": {"halted": bool(halt.get("halted")),
                         "reason": str(halt.get("reason") or _UNKNOWN)[:240]},
                "symbol": symbol,
                "side": side,
                "qty": _finite(getattr(intent, "qty", 0.0)),
                "kind": str(getattr(intent, "kind", "") or _UNKNOWN),
                "strategy": str(getattr(intent, "strategy", "") or _UNKNOWN),
                "purpose": str(getattr(intent, "purpose", "") or _UNKNOWN),
                "price": price,  # arrival/underlying price at suppression time
                "est_notional": _finite(getattr(intent, "est_notional", 0.0)),
                "conviction": _finite(conviction),
                "contract": str(getattr(intent, "contract", "") or ""),
                "strike": _finite(getattr(intent, "strike", 0.0)),
                "premium": _finite(getattr(intent, "premium", 0.0)),
                "scores": {
                    # contributing engine scores stashed by run_cycle; anything
                    # missing stays "unknown" — never invented.
                    "conviction": _finite(ctx.get("conviction", conviction)),
                    "risk_mult": ctx.get("risk_mult", _UNKNOWN),
                    "budget": ctx.get("budget", _UNKNOWN),
                    "tilts": ctx.get("tilts", _UNKNOWN),
                    "dispersion_scale": ctx.get("dispersion_scale", _UNKNOWN),
                    "composite": ctx.get("composite", _UNKNOWN),
                    "direction": str(ctx.get("direction", "") or _UNKNOWN),
                    "regime": str(ctx.get("regime", "") or _UNKNOWN),
                },
                "rationale": (str(getattr(intent, "reason", "") or "").strip()
                              or _UNKNOWN),
                "graded": False,
            }
            self._decisions.append(dec)
            self._per_cycle_counts[cyc] = self._per_cycle_counts.get(cyc, 0) + 1
            self._append(dec)
            return dec
        except Exception as exc:  # recording never breaks the cycle
            log.warning("shadow decision record skipped: %s", exc)
            return {}

    def _append(self, dec: Dict[str, Any]) -> None:
        try:
            if os.path.exists(self.path) and os.path.getsize(self.path) >= _LEDGER_MAX_BYTES:
                log.warning("shadow ledger at size cap (%d bytes) — record kept in "
                            "memory only", _LEDGER_MAX_BYTES)
                return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(dec) + "\n")
        except Exception as exc:
            log.warning("shadow ledger persist failed (kept in memory): %s", exc)

    def _load_tail(self, max_lines: int = _MEM_CAP) -> None:
        """Cold-start: recover the recent ungraded window from the JSONL trail."""
        if not os.path.exists(self.path):
            return
        tail: deque = deque(maxlen=max_lines)
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict) and row.get("id"):
                    tail.append(row)
        # keep memory as the working set; seq resumes past the largest seen
        for row in tail:
            self._decisions.append(row)
            try:
                n = int(str(row.get("id", "")).rsplit("-", 1)[-1])
                self._seq = max(self._seq, n)
            except (TypeError, ValueError):
                pass

    # ── grading ───────────────────────────────────────────────────────────────
    def grade_pending(self, state: Dict[str, Any],
                      get_price: Callable[[str], Any],
                      current_cycle: int) -> Dict[str, Any]:
        """Grade ungraded decisions from EARLIER cycles against realized moves.

        Same horizon style as the council calibration: a decision recorded at
        cycle N is graded once cycle N+1 (or later) prices arrive — the
        1-cycle-forward realized move. Returns {"graded": [...], "skipped": n}.
        Fault-isolated: never raises.
        """
        out: Dict[str, Any] = {"graded": [], "skipped": 0}
        try:
            if not self.enabled:
                return out
            mem = state.setdefault("shadow_learn", {})
            stats: Dict[str, Dict[str, float]] = mem.setdefault("stats", {})
            graded_ids: List[str] = mem.setdefault("graded_ids", [])
            graded_set = set(graded_ids)
            grades: List[Dict[str, Any]] = mem.setdefault("grades", [])
            cur = int(current_cycle or 0)
            pending = [d for d in self._decisions
                       if isinstance(d, dict) and not d.get("graded")
                       and int(d.get("cycle", 0) or 0) < cur
                       and str(d.get("id") or "") not in graded_set]
            for dec in pending[:_MAX_GRADE_PER_CYCLE]:
                res = self._grade_one(dec, get_price, cur, stats)
                if res is None:
                    out["skipped"] += 1
                    continue  # no price yet — retry next cycle
                dec["graded"] = True
                graded_ids.append(dec["id"])
                grades.append(res)
                out["graded"].append(res)
            # bound the state memory
            del graded_ids[:-_MAX_GRADED_IDS]
            del grades[:-200]
            for strat in list(stats.keys()):
                if strat not in ("__all__",) and not isinstance(stats[strat], dict):
                    del stats[strat]
            return out
        except Exception as exc:  # grading never breaks the cycle
            log.warning("shadow grading skipped: %s", exc)
            return out

    def _grade_one(self, dec: Dict[str, Any], get_price: Callable[[str], Any],
                   cur: int, stats: Dict[str, Dict[str, float]]) -> Optional[Dict]:
        entry_px = _finite(dec.get("price"))
        if entry_px <= 0:
            return None  # no valid entry price recorded; nothing honest to grade
        try:
            px = _finite(get_price(str(dec.get("symbol") or "")))
        except Exception:
            return None
        if px <= 0:
            return None  # price unavailable — retry next cycle
        sign = _side_sign(dec.get("side"))
        strat = str(dec.get("strategy") or _UNKNOWN)
        fwd = (px / entry_px - 1.0) * sign if sign else 0.0
        correct: Optional[bool] = (fwd > 0) if sign else None
        if correct is not None:
            for key in (strat, "__all__"):
                m = stats.get(key) or {"n": 0.0, "h": 0.0}
                m["n"] = _finite(m.get("n")) * _DECAY + 1.0
                m["h"] = _finite(m.get("h")) * _DECAY + (1.0 if correct else 0.0)
                stats[key] = m
        return {"id": dec.get("id"), "symbol": dec.get("symbol"),
                "side": dec.get("side"), "strategy": strat,
                "entry_price": round(entry_px, 6), "grade_price": round(px, 6),
                "fwd_return": round(fwd, 6), "correct": correct,
                "recorded_cycle": dec.get("cycle"), "graded_cycle": cur}

    # ── queries ───────────────────────────────────────────────────────────────
    def pending_count(self) -> int:
        try:
            return sum(1 for d in self._decisions
                       if isinstance(d, dict) and not d.get("graded"))
        except Exception:
            return 0

    def accuracy(self, state: Dict[str, Any]) -> Dict[str, float]:
        """Decayed realized hit-rate per strategy (1.0-neutral until _MIN_OBS)."""
        try:
            stats = (state.get("shadow_learn") or {}).get("stats") or {}
            out: Dict[str, float] = {}
            for strat, m in stats.items():
                if strat == "__all__" or not isinstance(m, dict):
                    continue
                n = _finite(m.get("n"))
                if n >= _MIN_OBS:
                    out[str(strat)] = round(_finite(m.get("h")) / n, 3)
            return out
        except Exception:
            return {}

    def summary(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            st = state or {}
            mem = st.get("shadow_learn") or {}
            return {"enabled": self.enabled,
                    "pending": self.pending_count(),
                    "graded_total": len(mem.get("graded_ids") or []),
                    "accuracy": self.accuracy(st),
                    "ledger": self.path}
        except Exception:
            return {"enabled": self.enabled}
