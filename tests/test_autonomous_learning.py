from __future__ import annotations

import json
from datetime import datetime, timezone

from intelligence.autonomous_learning import AutonomousLearningPipeline
from intelligence.shadow_eval import ShadowObservation, score_provider
from database import Database


def _portfolio(a=100.0, b=100.0):
    return [
        {"symbol": "AAA", "price": a, "conviction": 0.7, "direction": "long"},
        {"symbol": "BBB", "price": b, "conviction": 0.6, "direction": "short"},
    ]


def _overlays():
    return {
        provider: {
            "per_symbol_adjust": {"AAA": 0.1, "BBB": 0.1},
            "risk_multiplier": 0.9,
            "telemetry": {"latency_ms": 25, "schema_valid": True, "fallback_used": False},
        }
        for provider in ("claude", "openai", "gemini", "grok", "nvidia")
    }


def test_pipeline_generates_and_resolves_every_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("SAHJONY_HOME", str(tmp_path))
    database = Database(str(tmp_path / "data" / "test.db"))
    clock = lambda: datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    pipeline = AutonomousLearningPipeline(min_observations=20, database=database, clock=clock)
    first = pipeline.run_cycle(1, _portfolio(), _overlays())
    assert first["resolved_this_cycle"] == 0
    assert first["pending_symbols"] == 2
    assert first["orders_enabled"] is False
    assert all(value is None for value in first["leaders"].values())
    first_archive = tmp_path / "data" / "shadow" / "2026" / "July" / "000001.json"
    assert first_archive.exists()
    first_bytes = first_archive.read_bytes()

    second = pipeline.run_cycle(2, _portfolio(102.0, 98.0), _overlays())
    # 5 models + consensus + neutral, for 2 symbols.
    assert second["resolved_this_cycle"] == 14
    assert second["observations"] == 14
    providers = {row["provider"] for row in second["providers"]}
    assert providers == {"claude", "openai", "gemini", "grok", "nvidia",
                         "consensus", "neutral"}
    lines = (tmp_path / "data" / "ai_shadow_observations.jsonl").read_text().splitlines()
    assert len(lines) == 14
    assert all("direction" in json.loads(line) for line in lines)
    count = database.conn.execute("SELECT COUNT(*) FROM ai_shadow_observations").fetchone()[0]
    assert count == 14
    assert second["leaders"]["today"]["provider"] in {
        "claude", "openai", "gemini", "grok", "nvidia"
    }
    assert second["leaders"]["equity"] is not None
    assert second["leaders"]["crypto"] is None
    assert second["leaders"]["options"] is None
    second_archive = tmp_path / "data" / "shadow" / "2026" / "July" / "000002.json"
    assert second_archive.exists()
    assert first_archive.read_bytes() == first_bytes
    archived = json.loads(second_archive.read_text())
    assert archived["cycle"] == 2
    assert archived["orders_enabled"] is False
    assert archived["automatic_promotion_enabled"] is False
    assert len(archived["resolved_observations"]) == 14
    database.close()


def test_short_direction_is_scored_on_directional_return():
    long = ShadowObservation("t", "long", "X", 0.6, 0.1, 1.0, 0.02, direction="long")
    short = ShadowObservation("t", "short", "X", 0.6, 0.1, 1.0, 0.02, direction="short")
    assert score_provider("long", [long], min_observations=1, min_sharpe=0).net_return > 0
    assert score_provider("short", [short], min_observations=1, min_sharpe=0).net_return < 0


def test_consensus_uses_only_available_models(monkeypatch, tmp_path):
    monkeypatch.setenv("SAHJONY_HOME", str(tmp_path))
    consensus = AutonomousLearningPipeline.consensus({
        "claude": {"per_symbol_adjust": {"AAA": 0.1}, "risk_multiplier": 0.8},
        "openai": {"per_symbol_adjust": {"AAA": -0.1}, "risk_multiplier": 1.2},
    }, ["AAA"])
    assert consensus["per_symbol_adjust"]["AAA"] == 0.0
    assert consensus["risk_multiplier"] == 1.0
