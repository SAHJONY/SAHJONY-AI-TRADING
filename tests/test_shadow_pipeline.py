from pathlib import Path

from intelligence.shadow_pipeline import ShadowPipeline


def test_record_clamps_and_resolves(tmp_path: Path):
    pending = tmp_path / "pending.jsonl"
    resolved = tmp_path / "resolved.jsonl"
    p = ShadowPipeline(pending, resolved)
    row = p.record(
        provider="OpenAI",
        symbol="nvda",
        entry_price=100.0,
        base_conviction=2.0,
        adjustment=9.0,
        risk_multiplier=9.0,
        horizon_seconds=60,
        now=1000.0,
    )
    assert row.base_conviction == 1.0
    assert row.adjustment == 0.15
    assert row.risk_multiplier == 1.2
    out = p.resolve_due(lambda symbol: 105.0, now=1060.0)
    assert out["resolved"] == 1
    assert p.counts() == {"pending": 0, "resolved": 1}
    text = resolved.read_text()
    assert '"provider":"openai"' in text
    assert '"forward_return":0.05' in text


def test_not_due_is_retained(tmp_path: Path):
    p = ShadowPipeline(tmp_path / "p.jsonl", tmp_path / "r.jsonl")
    p.record(
        provider="neutral",
        symbol="SPY",
        entry_price=500,
        base_conviction=0.5,
        adjustment=0,
        risk_multiplier=1,
        horizon_seconds=300,
        now=1000,
    )
    out = p.resolve_due(lambda symbol: 501, now=1100)
    assert out == {"resolved": 0, "pending": 1, "failed": 0}


def test_bad_price_retries_without_data_loss(tmp_path: Path):
    p = ShadowPipeline(tmp_path / "p.jsonl", tmp_path / "r.jsonl")
    p.record(
        provider="claude",
        symbol="QQQ",
        entry_price=400,
        base_conviction=0.6,
        adjustment=0.05,
        risk_multiplier=0.8,
        horizon_seconds=60,
        now=1000,
    )
    out = p.resolve_due(lambda symbol: 0, now=1060)
    assert out["failed"] == 1
    assert p.counts()["pending"] == 1
