"""Continuous, evidence-weighted strategy ranking for the operations dashboard."""
from __future__ import annotations

from typing import Any, Dict


STRATEGIES = (
    ("Pairs", "pairs", "integrated"),
    ("Momentum", "daytrade", "integrated"),
    ("Mean Reversion", "mean_reversion", "incubator"),
    ("Credit Spread", "spread", "integrated"),
    ("Wheel", "wheel", "integrated"),
    ("Volatility Breakout", "volatility_breakout", "incubator"),
    ("Regime Momentum", "regime_momentum", "incubator"),
)


def rank_strategies(state: Dict[str, Any], shadow_report: Dict[str, Any] | None = None) -> list[Dict]:
    memory = ((state.get("hermes") or {}).get("strat") or {})
    rows = []
    for name, key, stage in STRATEGIES:
        stats = memory.get(key) or {}
        observations = max(0.0, float(stats.get("n", 0.0) or 0.0))
        wins = max(0.0, min(observations, float(stats.get("w", 0.0) or 0.0)))
        win_rate = wins / observations if observations else 0.0
        # Beta(2,2) shrinkage plus an evidence multiplier prevents a lucky first
        # trade from outranking a strategy with a meaningful track record.
        posterior = (wins + 2.0) / (observations + 4.0) if observations else 0.5
        confidence = min(1.0, observations / 20.0)
        score = round(100.0 * posterior * confidence, 2) if observations else 0.0
        rows.append({
            "name": name, "key": key, "stage": stage, "score": score,
            "observations": round(observations, 2), "win_rate": round(win_rate, 4),
            "evidence": "realized-hermes" if observations else "none",
            "live_eligible": False,
        })

    consensus = next((row for row in (shadow_report or {}).get("providers", [])
                      if row.get("provider") == "consensus"), {})
    rows.append({
        "name": "AI Consensus", "key": "ai_consensus", "stage": "shadow",
        "score": float(consensus.get("score", 0.0) or 0.0),
        "observations": int(consensus.get("observations", 0) or 0),
        "win_rate": float(consensus.get("hit_rate", 0.0) or 0.0),
        "evidence": "ai-shadow" if consensus.get("observations") else "none",
        "live_eligible": False,
    })
    rows.sort(key=lambda row: (row["score"], row["observations"]), reverse=True)
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows
