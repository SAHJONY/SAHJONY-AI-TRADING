"""Bounded self-tuning of NON-RISK parameters.

The desk may tune a small allowlist of non-risk parameters (conviction floor,
dispersion sensitivity, anomaly threshold) within HARD-CODED safe bounds — and
only when a genuine WALK-FORWARD test improves: recorded closed trades are
split chronologically, the best step is chosen on the FIRST (in-sample) half,
and it is applied only if the SAME step also improves the SECOND
(out-of-sample) half. In-sample-only counterfactuals are optimistic and are
never enough on their own.

HARD RULE — risk parameters are NEVER self-tunable. Any attempt to tune one of
FROZEN_RISK_PARAMS raises and is logged as a rejected event. The risk envelope
($10/order, 12% per position, 70% deployed, 10% daily halt) is untouchable.

Every tuning event is logged with before/after values and the evidence that
justified it. Tuning runs at most once per day and changes one parameter per
run (small steps, auditable).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

log = get_logger("auto_tune")

# Allowlist: param -> (min, max, step). Everything else is untunable by design.
TUNABLE_BOUNDS: Dict[str, Tuple[float, float, float]] = {
    "min_council_conviction": (0.35, 0.65, 0.05),
    "dispersion_k": (1.5, 4.0, 0.5),
    "anomaly_z_limit": (4.0, 8.0, 1.0),
}

# NEVER self-tunable — hard-coded exclusion, checked before any tuning math.
FROZEN_RISK_PARAMS = frozenset({
    "max_order_usd", "max_allocation_pct", "max_total_deployed_pct",
    "max_daily_drawdown_pct", "min_order_notional", "kill_switch",
    "trading_capital",
})

_MIN_TRADES = 10          # evidence floor for a tuning decision
_MIN_IMPROVEMENT_USD = 0.25
_MIN_IMPROVEMENT_PCT = 0.02


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class AutoTune:
    def __init__(self, cfg=None):
        import os
        self.enabled = str(os.getenv("AUTO_TUNE_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")
        self.cfg = cfg

    # ── safety API ────────────────────────────────────────────────────────────
    @staticmethod
    def assert_tunable(name: str) -> None:
        """Raise if `name` must never be self-tuned."""
        if name in FROZEN_RISK_PARAMS:
            raise ValueError(f"REFUSED: '{name}' is a frozen risk parameter and "
                             f"can never be self-tuned")
        if name not in TUNABLE_BOUNDS:
            raise ValueError(f"REFUSED: '{name}' is not on the tunable allowlist")

    def current(self, name: str, state: Dict[str, Any]) -> float:
        self.assert_tunable(name)
        tuned = (state.get("auto_tune") or {}).get("params") or {}
        if name in tuned:
            return _finite(tuned[name])
        return _finite(getattr(self.cfg, name, TUNABLE_BOUNDS[name][0]))

    def apply(self, name: str, value: float, state: Dict[str, Any],
              evidence: str = "") -> Dict[str, Any]:
        """Set a tuned value (bounded), logging before/after. Never raises the
        caller — but REFUSES frozen params loudly (ValueError)."""
        self.assert_tunable(name)  # raises on frozen / unknown — by design
        lo, hi, _ = TUNABLE_BOUNDS[name]
        value = max(lo, min(hi, _finite(value, lo)))
        mem = state.setdefault("auto_tune", {})
        params = mem.setdefault("params", {})
        events = mem.setdefault("events", [])
        before = self.current(name, state)
        params[name] = round(value, 4)
        events.append({"ts": datetime.now(timezone.utc).isoformat(), "param": name,
                       "before": before, "after": round(value, 4),
                       "evidence": evidence[:300]})
        del events[:-50]
        # apply to the live config object so the running desk uses it now
        try:
            setattr(self.cfg, name, round(value, 4))
        except Exception as exc:
            log.warning("could not apply tuned %s to cfg: %s", name, exc)
        log.info("auto-tune: %s %.4f → %.4f (%s)", name, before, value, evidence[:120])
        return {"param": name, "before": before, "after": round(value, 4)}

    def load_into_cfg(self, state: Dict[str, Any]) -> None:
        """Re-apply persisted tuned params to cfg at cycle start. Frozen params
        found here would indicate tampering — they are ignored and logged."""
        try:
            for name, value in ((state.get("auto_tune") or {}).get("params") or {}).items():
                if name in FROZEN_RISK_PARAMS:
                    log.error("auto-tune state contained frozen param '%s' — ignored", name)
                    continue
                if name in TUNABLE_BOUNDS:
                    setattr(self.cfg, name, _finite(value))
        except Exception as exc:
            log.warning("auto-tune load failed: %s", exc)

    # ── evidence-gated tuning ─────────────────────────────────────────────────
    def maybe_tune(self, state: Dict[str, Any], trade_memory=None) -> Dict[str, Any]:
        """At most once/day, try ONE parameter step justified by recent realized
        P&L. Returns {'tuned': bool, ...}. Never raises."""
        out: Dict[str, Any] = {"tuned": False}
        try:
            if not self.enabled:
                return out
            mem = state.setdefault("auto_tune", {})
            if mem.get("last_run") == _today():
                return out
            mem["last_run"] = _today()
            if trade_memory is None:
                return out
            trades = [t for t in trade_memory._all()
                      if _finite(t.get("entry_conviction"), -1) >= 0]
            if len(trades) < _MIN_TRADES:
                out["reason"] = f"insufficient evidence ({len(trades)} < {_MIN_TRADES})"
                return out
            return self._tune_conviction_floor(state, trades, out)
        except Exception as exc:
            log.warning("auto-tune skipped: %s", exc)
            return out

    def _tune_conviction_floor(self, state: Dict[str, Any],
                               trades: List[Dict[str, Any]],
                               out: Dict[str, Any]) -> Dict[str, Any]:
        """Genuine walk-forward: chronological split; the winning step is chosen
        on the in-sample half and applied only if it ALSO improves the
        out-of-sample half. Never raises."""
        name = "min_council_conviction"
        lo, hi, step = TUNABLE_BOUNDS[name]
        cur = self.current(name, state)
        # chronological walk-forward split on recorded exit time
        ordered = sorted(trades,
                         key=lambda t: str(t.get("exit_ts") or t.get("ts") or ""))
        n = len(ordered)
        ins, oos = ordered[:n // 2], ordered[n // 2:]
        if len(oos) < max(5, _MIN_TRADES // 2):
            out["reason"] = (f"insufficient out-of-sample evidence "
                             f"({len(oos)} closes)")
            return out

        def pnl_at(tr: List[Dict[str, Any]], floor: float) -> float:
            return sum(_finite(t.get("realized_pnl"))
                       for t in tr if _finite(t.get("entry_conviction"), 0) >= floor)

        candidates = []
        if cur - step >= lo:
            candidates.append(round(cur - step, 4))
        if cur + step <= hi:
            candidates.append(round(cur + step, 4))
        # 1) in-sample selection
        ins_pnl = {c: pnl_at(ins, c) for c in [cur] + candidates}
        best = max([cur] + candidates, key=lambda c: ins_pnl[c])
        if best == cur:
            out["reason"] = ("walk-forward: in-sample shows no better step "
                             f"(floor stays {cur:.2f})")
            return out
        # 2) out-of-sample confirmation of the SAME step
        cur_oos, best_oos = pnl_at(oos, cur), pnl_at(oos, best)
        gain_oos = best_oos - cur_oos
        needed = max(_MIN_IMPROVEMENT_USD, abs(cur_oos) * _MIN_IMPROVEMENT_PCT)
        if gain_oos >= needed:
            ev = (f"walk-forward on {len(ins)} in-sample + {len(oos)} "
                  f"out-of-sample recorded closes: floor {cur:.2f} → {best:.2f} "
                  f"improves in-sample P&L ${ins_pnl[cur]:+.2f} → ${ins_pnl[best]:+.2f} "
                  f"AND out-of-sample P&L ${cur_oos:+.2f} → ${best_oos:+.2f}")
            res = self.apply(name, best, state, evidence=ev)
            out.update({"tuned": True, **res, "evidence": ev,
                        "last_tuned_at": datetime.now(timezone.utc).isoformat(),
                        "walk_forward": {"in_sample": len(ins),
                                         "out_of_sample": len(oos)}})
        else:
            out["reason"] = (f"walk-forward: in-sample winner {best:.2f} fails "
                             f"out-of-sample confirmation (OOS gain ${gain_oos:+.2f} < "
                             f"${needed:.2f} required) — no tune")
        return out
