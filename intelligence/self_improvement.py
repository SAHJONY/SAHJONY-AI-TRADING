"""Evidence-based operational learning scorecard."""
from __future__ import annotations

from typing import Any, Dict


def self_improvement_score(state: Dict[str, Any], shadow: Dict[str, Any] | None,
                           min_observations: int = 100) -> Dict[str, Any]:
    shadow = shadow or {}
    hermes = state.get("hermes") or {}
    knowledge_nodes = len(hermes.get("hits") or {}) + len(hermes.get("strat") or {})
    knowledge_score = min(100.0, knowledge_nodes / 20.0 * 100.0)

    model_rows = [row for row in shadow.get("providers", [])
                  if row.get("provider") in {"claude", "openai", "gemini", "grok", "nvidia"}
                  and float(row.get("observations", 0) or 0) > 0]
    total_model_observations = sum(float(row.get("observations", 0) or 0) for row in model_rows)
    accuracy = (sum(float(row.get("hit_rate", 0.0) or 0.0) *
                    float(row.get("observations", 0) or 0) for row in model_rows) /
                total_model_observations) if total_model_observations else None

    observation_count = int(shadow.get("observations", 0) or 0)
    learning_progress = min(1.0, observation_count / max(1, int(min_observations)))
    providers_covered = len(model_rows) / 5.0
    leaders = shadow.get("leaders") or {}
    assets_covered = sum(1 for key in ("crypto", "equity", "options") if leaders.get(key)) / 3.0
    regime_covered = 1.0 if leaders.get("market_regime") else 0.0
    training_coverage = min(1.0, providers_covered * 0.5 + assets_covered * 0.35
                            + regime_covered * 0.15)
    promotion_ready = bool(shadow.get("recommended_provider"))

    accuracy_score = (accuracy or 0.0) * 100.0
    overall = (knowledge_score * 0.20 + accuracy_score * 0.25
               + learning_progress * 100.0 * 0.25
               + training_coverage * 100.0 * 0.20
               + (100.0 if promotion_ready else 0.0) * 0.10)
    evidence_state = ("mature" if promotion_ready else "learning" if observation_count
                      else "no_evidence")
    return {
        "knowledge_base": {"score": round(knowledge_score, 2), "nodes": knowledge_nodes},
        "model_accuracy": round(accuracy, 4) if accuracy is not None else None,
        "learning_progress": round(learning_progress, 4),
        "observation_count": observation_count,
        "training_coverage": round(training_coverage, 4),
        "promotion_ready": promotion_ready,
        "overall_intelligence": round(overall, 2),
        "interpretation": "operational learning index; not a measure of general intelligence",
        "evidence_state": evidence_state,
    }
