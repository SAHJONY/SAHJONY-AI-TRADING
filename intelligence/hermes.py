"""Hermes — the firm's background guardian agent (data integrity · scores · self-improvement).

Hermes runs quietly in the background of every cycle, before the strategists,
with a WELL-DEFINED GOAL the whole desk can be held to (see DEFAULT_GOAL /
HERMES_GOAL). Its three mandates:

  1. ACCURATE DATA — validates every symbol's market feed each cycle (bad price,
     non-finite history, stale feed, extreme jumps). Symbols with hard data
     problems are QUARANTINED: their conviction is forced to zero so the Risk
     Officer blocks any NEW risk, while exits still flow. Garbage in, no orders out.
  2. SHARP SCORES — an honest performance scorecard straight off the equity
     curve: annualized Sharpe & Sortino, volatility, max drawdown. No cherry-
     picking; the same numbers the owner sees.
  3. SELF-IMPROVEMENT — tracks the council's REALIZED directional hit-rate per
     symbol (did "long" actually precede a rise?) with exponential decay, and
     converts it into a small, bounded conviction tilt in [-0.10, +0.10]. The
     desk leans into symbols it has genuinely been right about and away from
     ones it keeps misreading — transparently, never a black box.

House rules preserved: Hermes is deterministic and advisory — it never invents
trades, all tilts are clamped small, hard risk ceilings are untouched, and every
step is fault-isolated so a Hermes failure degrades to neutral, never crashing
the trading loop. Disable anytime with HERMES_ENABLED=false.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from config import Config
from utils.logger import get_logger

log = get_logger("hermes")

# Self-improvement tilt is clamped small so calibration can nudge, never hijack.
_MAX_TILT = 0.10
_DECAY = 0.97          # exponential decay on the hit-rate memory (recent > ancient)
_MIN_OBS = 8           # observations required before calibration kicks in
# Strategy-level capital re-weighting stays in a tight band: a winning desk earns at
# most +15% budget, a losing one is trimmed at most -30% — never switched off, so it
# can keep generating the evidence needed to earn its budget back (perpetual loop).
_W_MIN, _W_MAX = 0.70, 1.15
_JUMP_LIMIT = 0.25     # |price/last_close - 1| beyond this = suspect feed
# Annualization for 15-min cycles across the US cash session (~26/day * 252).
_CYCLES_PER_YEAR = 6552.0

DEFAULT_GOAL = ("Maximize risk-adjusted return (Sharpe) within the hard risk "
                "ceilings — capital preservation first, paper trading only.")


@dataclass
class HermesReport:
    used: bool = False
    goal: str = DEFAULT_GOAL
    issues: Dict[str, List[str]] = field(default_factory=dict)   # symbol -> problems found
    quarantined: List[str] = field(default_factory=list)          # hard data failures
    tilt: Dict[str, float] = field(default_factory=dict)          # calibration nudge per symbol
    hit_rates: Dict[str, float] = field(default_factory=dict)     # realized council accuracy
    data_ok_pct: float = 1.0                                      # share of clean feeds this cycle
    strategy_weights: Dict[str, float] = field(default_factory=dict)  # capital weight per desk


class Hermes:
    """Background guardian: data validation, honest scoring, bounded self-calibration."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        env = os.getenv("HERMES_ENABLED")
        self.enabled = env is None or env.strip().lower() in ("1", "true", "yes", "on")
        self.goal = (os.getenv("HERMES_GOAL", DEFAULT_GOAL) or DEFAULT_GOAL).strip()

    @property
    def status(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "agent": "hermes", "goal": self.goal}

    # ── per-cycle review (called before the strategists) ─────────────────────────
    def review(self, research: List[Dict[str, Any]], state: Dict[str, Any]) -> HermesReport:
        """research: [{symbol, snap, verdict}]. Mutates state['hermes'] memory only.
        Any internal failure returns a neutral report — the loop never depends on it."""
        if not self.enabled or not research:
            return HermesReport(used=False, goal=self.goal)
        rep = HermesReport(used=True, goal=self.goal)
        mem = state.setdefault("hermes", {})

        # 1) ACCURATE DATA — validate every feed; quarantine hard failures.
        clean = 0
        for r in research:
            sym = r["symbol"]
            try:
                hard, soft = self._data_issues(r["snap"])
            except Exception as exc:
                hard, soft = ["validator error: " + str(exc)[:80]], []
            if hard:
                rep.quarantined.append(sym)
            if hard or soft:
                rep.issues[sym] = hard + soft
            else:
                clean += 1
        rep.data_ok_pct = round(clean / len(research), 3)

        # 3) SELF-IMPROVEMENT — grade last cycle's council calls, then record this
        # cycle's calls for grading next time. Decayed hit-rate → bounded tilt.
        preds = mem.get("pred") or {}
        hits: Dict[str, Dict[str, float]] = mem.setdefault("hits", {})
        for r in research:
            sym = r["symbol"]
            price = self._safe_price(r["snap"])
            prev = preds.get(sym)
            if prev and prev.get("dir") in ("long", "short") and prev.get("price", 0) > 0 and price > 0:
                realized = price / prev["price"] - 1.0
                correct = realized > 0 if prev["dir"] == "long" else realized < 0
                h = hits.get(sym, {"n": 0.0, "h": 0.0})
                h["n"] = h["n"] * _DECAY + 1.0
                h["h"] = h["h"] * _DECAY + (1.0 if correct else 0.0)
                hits[sym] = h
        mem["pred"] = {r["symbol"]: {"dir": getattr(r["verdict"], "direction", "flat"),
                                     "price": self._safe_price(r["snap"])}
                       for r in research}

        for r in research:
            sym = r["symbol"]
            h = hits.get(sym)
            if h and h["n"] >= _MIN_OBS:
                rate = h["h"] / h["n"]
                rep.hit_rates[sym] = round(rate, 3)
                rep.tilt[sym] = max(-_MAX_TILT, min(_MAX_TILT, (rate - 0.5) * 0.5))
            else:
                rep.tilt[sym] = 0.0
        # Quarantine overrides calibration: force conviction to zero so the Risk
        # Officer blocks all NEW risk on a broken feed. Exits still flow.
        for sym in rep.quarantined:
            rep.tilt[sym] = -1.0

        # 3b) STRATEGY-LEVEL SELF-IMPROVEMENT — consume the execution desk's realized
        # outcomes (state['hermes_events']) into decayed per-strategy win-rates and
        # convert them to bounded capital weights. Winning desks earn more budget,
        # losing desks are trimmed but never switched off — the loop runs forever.
        strat_mem: Dict[str, Dict[str, float]] = mem.setdefault("strat", {})
        for ev in state.get("hermes_events") or []:
            name = str(ev.get("strategy") or "?")
            try:
                won = float(ev.get("realized") or 0.0) > 0
            except (TypeError, ValueError):
                continue
            m = strat_mem.get(name, {"n": 0.0, "w": 0.0})
            m["n"] = m["n"] * _DECAY + 1.0
            m["w"] = m["w"] * _DECAY + (1.0 if won else 0.0)
            strat_mem[name] = m
        state["hermes_events"] = []
        for name, m in strat_mem.items():
            if m["n"] >= _MIN_OBS:
                rate = m["w"] / m["n"]
                rep.strategy_weights[name] = round(
                    max(_W_MIN, min(_W_MAX, 1.0 + (rate - 0.5) * 0.6)), 3)
        return rep

    # ── 2) SHARP SCORES — honest stats straight off the equity curve ─────────────
    @staticmethod
    def scorecard(equity_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        ys = []
        for row in equity_rows or []:
            try:
                y = float(row.get("equity") or 0)
            except (TypeError, ValueError):
                y = 0.0
            if y > 0 and math.isfinite(y):
                ys.append(y)
        if len(ys) < 3:
            return {"cycles": len(ys), "sharpe": None, "sortino": None,
                    "max_drawdown_pct": None, "volatility_pct": None}
        rets = [ys[i] / ys[i - 1] - 1.0 for i in range(1, len(ys))]
        n = len(rets)
        mean = sum(rets) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / max(1, n - 1))
        dsd = math.sqrt(sum(min(0.0, x) ** 2 for x in rets) / max(1, n - 1))
        ann = math.sqrt(_CYCLES_PER_YEAR)
        peak, mdd = -float("inf"), 0.0
        for y in ys:
            peak = max(peak, y)
            mdd = min(mdd, (y - peak) / peak)
        return {
            "cycles": len(ys),
            # zero variance means the ratio is undefined — report None, never a fake 0
            "sharpe": round(mean / sd * ann, 2) if sd > 1e-12 else None,
            "sortino": round(mean / dsd * ann, 2) if dsd > 1e-12 else None,
            "max_drawdown_pct": round(mdd * 100, 2),
            "volatility_pct": round(sd * 100, 3),   # per-cycle stdev
        }

    # ── helpers ───────────────────────────────────────────────────────────────────
    @staticmethod
    def _safe_price(snap) -> float:
        try:
            p = float(getattr(snap, "price", 0) or 0)
            return p if math.isfinite(p) else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _data_issues(snap):
        """Returns (hard, soft) problem lists. Hard problems quarantine the symbol."""
        hard, soft = [], []
        price = Hermes._safe_price(snap)
        if price <= 0:
            hard.append("bad price")
        closes = []
        bad_hist = False
        for c in list(getattr(snap, "closes", []) or []):
            try:
                v = float(c)
            except (TypeError, ValueError):
                bad_hist = True
                continue
            if math.isfinite(v):
                closes.append(v)
            else:
                bad_hist = True
        if bad_hist:
            hard.append("non-finite history")
        if len(closes) < 30:
            soft.append("short history")
        elif len({round(c, 10) for c in closes[-10:]}) == 1:
            soft.append("stale feed (flat last 10)")
        if closes and price > 0 and closes[-1] > 0 and abs(price / closes[-1] - 1.0) > _JUMP_LIMIT:
            hard.append("extreme jump vs last close")
        return hard, soft
