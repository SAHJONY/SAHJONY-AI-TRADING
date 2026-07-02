"""The Advisory Board — SAHJONY AI Trading Intelligence Council (advisory layer).

Six investor-philosophy agents plus a Decision Engine, exactly as specified in
the README: Buffett (quality/value), Munger (risk & decision discipline), Macro
(economic environment), Growth (innovation/expansion), Quant (statistical
signals) and a Risk Agent that acts as a portfolio-protection GATE. This layer
is ADVISORY ONLY — it nudges conviction by a small bounded tilt; execution
remains controlled by the hard risk rules (Risk Officer + config ceilings).

Honesty per house rules: each agent is a transparent, public-domain estimator
computed from prices — a PROXY for its namesake's philosophy, not that
investor's actual model, and no guarantee of profit. Every score comes with a
one-line rationale so the owner can always see why.

Scores are in [-1, +1]. The Decision Engine combines them into a composite,
converts it into a conviction tilt clamped to ±0.10, and the Risk Agent's gate
(0..1) scales it — a stressed name can never receive a positive nudge.
Deterministic, fault-isolated, disabled via ADVISORS_ENABLED=false.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from intelligence.agents import MarketSnapshot
from utils.logger import get_logger

log = get_logger("advisors")

_MAX_TILT = 0.10          # advisory nudge, never a hijack
_GATE_BLOCK = 0.35        # below this protection level, positive tilt is blocked

# Decision Engine weights — sum to 1.0; Quant leads (it is a quant desk), the
# philosophical agents temper it.
_WEIGHTS = {"buffett": 0.22, "munger": 0.18, "macro": 0.15, "growth": 0.20, "quant": 0.25}


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return max(lo, min(hi, v))


@dataclass
class BoardVerdict:
    symbol: str
    scores: Dict[str, float] = field(default_factory=dict)   # per-agent, [-1, 1]
    rationale: Dict[str, str] = field(default_factory=dict)  # per-agent one-liner
    gate: float = 1.0                                        # Risk Agent, 0..1
    composite: float = 0.0                                   # weighted blend, [-1, 1]
    tilt: float = 0.0                                        # conviction nudge, ±0.10


# ── the six agents (each: snapshot → score in [-1,1] + rationale) ───────────────
def buffett_agent(s: MarketSnapshot) -> tuple:
    """Quality/value: pay less than the long-run mean for a stable business."""
    ma200 = s.sma(200)
    discount = (ma200 - s.price) / ma200 if ma200 > 0 else 0.0
    quality = 1.0 - 2.0 * min(1.0, (s.vol or 0.0) / 0.60)     # low vol ≈ stable
    score = _clamp(0.55 * math.tanh(4.0 * discount) + 0.45 * quality)
    return score, f"{discount:+.1%} vs 200d mean, vol {s.vol:.0%}"


def munger_agent(s: MarketSnapshot) -> tuple:
    """Risk & decision discipline: avoid overpaying into extended, frothy moves."""
    ma50 = s.sma(50)
    extension = (s.price - ma50) / ma50 if ma50 > 0 else 0.0
    froth = max(0.0, extension - 0.10)                        # >10% above trend = froth
    spike = max(0.0, abs(s.ret_over(5)) - 0.08)               # violent week = indiscipline
    score = _clamp(0.3 - 5.0 * froth - 4.0 * spike)
    return score, f"{extension:+.1%} vs 50d trend, 5d move {s.ret_over(5):+.1%}"


def macro_agent(s: MarketSnapshot) -> tuple:
    """Economic environment: read risk-on/off from the benchmark's trend."""
    b = np.asarray(s.bench_closes, dtype=float)
    if b.size < 200:
        return 0.0, "insufficient benchmark history"
    b50, b200 = float(np.mean(b[-50:])), float(np.mean(b[-200:]))
    risk_on = (b50 / b200 - 1.0) if b200 > 0 else 0.0
    score = _clamp(math.tanh(18.0 * risk_on))
    return score, f"benchmark 50/200 spread {risk_on:+.1%} ({'risk-on' if risk_on > 0 else 'risk-off'})"


def growth_agent(s: MarketSnapshot) -> tuple:
    """Innovation/expansion proxy: sustained momentum near new highs."""
    mom = s.ret_over(126)                                     # ~6 months
    c = np.asarray(s.closes, dtype=float)
    hi = float(np.max(c)) if c.size else 0.0
    prox = (s.price / hi - 1.0) if hi > 0 else -1.0           # 0 = at the high
    score = _clamp(0.65 * math.tanh(2.5 * mom) + 0.35 * _clamp(1.0 + 4.0 * prox))
    return score, f"6m {mom:+.1%}, {prox:+.1%} off the high"


def quant_agent(s: MarketSnapshot) -> tuple:
    """Statistical signals: mean-reversion z-score blended with trend."""
    c = np.asarray(s.closes, dtype=float)
    if c.size < 50:
        return 0.0, "insufficient history"
    ma20, sd20 = float(np.mean(c[-20:])), float(np.std(c[-20:]))
    z = (s.price - ma20) / sd20 if sd20 > 1e-9 else 0.0
    ma50 = float(np.mean(c[-50:]))
    trend = (ma20 / ma50 - 1.0) if ma50 > 0 else 0.0
    score = _clamp(0.5 * (-math.tanh(z / 2.0)) + 0.5 * math.tanh(8.0 * trend))
    return score, f"z {z:+.2f}, 20/50 trend {trend:+.1%}"


def risk_agent(s: MarketSnapshot) -> tuple:
    """Portfolio protection gate (0..1): stress scales the whole board down."""
    c = np.asarray(s.closes, dtype=float)
    peak = float(np.max(c)) if c.size else 0.0
    drawdown = (s.price / peak - 1.0) if peak > 0 else 0.0    # ≤ 0
    vol_excess = max(0.0, (s.vol or 0.0) - 0.50)
    dd_excess = max(0.0, -drawdown - 0.20)
    gate = _clamp(1.0 - 1.5 * vol_excess - 3.0 * dd_excess, 0.0, 1.0)
    return gate, f"drawdown {drawdown:+.1%}, vol {s.vol:.0%} → gate {gate:.2f}"


# ── Decision Engine ─────────────────────────────────────────────────────────────
class AdvisoryBoard:
    """Runs the six agents and combines them into one bounded advisory verdict."""

    AGENTS = {"buffett": buffett_agent, "munger": munger_agent, "macro": macro_agent,
              "growth": growth_agent, "quant": quant_agent}

    def __init__(self, cfg=None):
        env = os.getenv("ADVISORS_ENABLED")
        self.enabled = env is None or env.strip().lower() in ("1", "true", "yes", "on")

    @property
    def status(self) -> Dict[str, object]:
        return {"enabled": self.enabled,
                "agents": [*self.AGENTS.keys(), "risk_gate"],
                "weights": dict(_WEIGHTS), "max_tilt": _MAX_TILT}

    def deliberate(self, snap: MarketSnapshot) -> BoardVerdict:
        v = BoardVerdict(symbol=snap.symbol)
        if not self.enabled:
            return v
        for name, fn in self.AGENTS.items():
            try:
                score, why = fn(snap)
            except Exception as exc:   # one agent's failure never sinks the board
                score, why = 0.0, f"error: {str(exc)[:60]}"
            v.scores[name] = round(_clamp(score), 3)
            v.rationale[name] = why
        try:
            v.gate, v.rationale["risk_gate"] = risk_agent(snap)
        except Exception as exc:
            v.gate, v.rationale["risk_gate"] = 1.0, f"error: {str(exc)[:60]}"
        v.gate = round(_clamp(v.gate, 0.0, 1.0), 3)
        v.composite = round(sum(_WEIGHTS[a] * v.scores.get(a, 0.0) for a in _WEIGHTS), 3)
        tilt = _clamp(v.composite, -1, 1) * _MAX_TILT * v.gate
        if v.gate < _GATE_BLOCK:       # protection gate: stressed names get no help
            tilt = min(tilt, 0.0)
        v.tilt = round(_clamp(tilt, -_MAX_TILT, _MAX_TILT), 4)
        return v

    def evaluate(self, research: List[Dict]) -> Dict[str, BoardVerdict]:
        """research: [{symbol, snap, verdict}] → {symbol: BoardVerdict}."""
        out: Dict[str, BoardVerdict] = {}
        if not self.enabled:
            return out
        for r in research or []:
            try:
                out[r["symbol"]] = self.deliberate(r["snap"])
            except Exception as exc:
                log.warning("advisory board failed for %s: %s", r.get("symbol"), exc)
        return out
