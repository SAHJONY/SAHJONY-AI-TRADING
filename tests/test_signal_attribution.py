"""Signal attribution ledger tests — fully offline, no network.

Synthetic engine inputs + synthetic price series only. Covers:
  * snapshot extraction from cycle verdicts (never re-runs engines)
  * signed-move / hit math at fixed horizons
  * exponential decay of hit-rate and mean signed return
  * the 20-observation neutrality gating (mirrors council_calibration)
  * missing prices -> None, never invented
  * refresh() never raises; the main.py hook is fault-isolated
  * SIGNAL_ATTRIBUTION_ENABLED env override
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel import signal_attribution as sa  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _agent(name, score, confidence=0.8):
    return SimpleNamespace(name=name, persona=f"{name} persona", score=score,
                           confidence=confidence, rationale="test")


def _entry(symbol, price, agents):
    return {"symbol": symbol,
            "snap": SimpleNamespace(symbol=symbol, price=price),
            "verdict": SimpleNamespace(verdicts=list(agents))}


def _graded(engine, signed, hit, family="council"):
    return {"engine": engine, "family": family, "graded": True,
            "signed_return_bps": signed, "hit": hit}


T0 = 1_000_000.0


# ---------------------------------------------------------------------------
# 1. Snapshot extraction
# ---------------------------------------------------------------------------

def test_snapshot_extracts_engine_inputs():
    research = [
        _entry("BTC", 100.0, [_agent("Up", 0.6, 0.8), _agent("Down", -0.3, 0.5)]),
        _entry("ETH", 200.0, [_agent("Up", 0.1, 1.0)]),
    ]
    inputs, errors = sa.snapshot_engine_inputs(research, cycle_id=7, ts=T0)
    assert errors == []
    assert len(inputs) == 3
    btc_up = next(i for i in inputs if i["symbol"] == "BTC" and i["engine"] == "Up")
    assert btc_up["family"] == "council"
    assert btc_up["score"] == 0.6
    assert btc_up["confidence"] == 0.8
    assert btc_up["contribution"] == pytest.approx(0.6 * 0.8)
    assert btc_up["entry_price"] == 100.0
    assert btc_up["entry_ts"] == T0
    assert btc_up["cycle_id"] == 7


def test_snapshot_includes_board_tilt():
    research = [_entry("BTC", 100.0, [_agent("Up", 0.6)])]
    board = {"BTC": SimpleNamespace(symbol="BTC", tilt=0.05, gate=0.9)}
    inputs, errors = sa.snapshot_engine_inputs(research, cycle_id=1, ts=T0,
                                               board=board)
    assert errors == []
    tilt = next(i for i in inputs if i["engine"] == "advisory_board")
    assert tilt["family"] == "advisory_board"
    assert tilt["score"] == pytest.approx(0.05)
    assert tilt["confidence"] == pytest.approx(0.9)
    assert tilt["symbol"] == "BTC"


def test_snapshot_skips_symbol_without_entry_price():
    research = [
        _entry("BTC", None, [_agent("Up", 0.6)]),
        _entry("ETH", 0.0, [_agent("Up", 0.6)]),
        _entry("SOL", 50.0, [_agent("Up", 0.6)]),
    ]
    inputs, errors = sa.snapshot_engine_inputs(research, cycle_id=1, ts=T0)
    assert {i["symbol"] for i in inputs} == {"SOL"}
    assert len(errors) == 2  # one per skipped symbol


def test_snapshot_tolerates_garbage():
    inputs, errors = sa.snapshot_engine_inputs(
        [{"nope": 1}, "garbage", None], cycle_id=1, ts=T0)
    assert inputs == []
    assert errors  # recorded, not raised


# ---------------------------------------------------------------------------
# 2. Signed moves + hits at fixed horizons (synthetic price series)
# ---------------------------------------------------------------------------

def _two_cycle(tmp_path, price_t0=100.0, price_t1=101.0, agents=None):
    base = str(tmp_path)
    agents = agents if agents is not None else [_agent("Up", 0.6), _agent("Down", -0.6)]
    r1 = [_entry("BTC", price_t0, agents)]
    p1 = sa.refresh(research=r1, cycle_id=1, now_ts=T0, base=base)
    r2 = [_entry("BTC", price_t1, agents)]
    p2 = sa.refresh(research=r2, cycle_id=2, now_ts=T0 + 3600, base=base)
    return base, p1, p2


def test_signed_move_and_hit_1h(tmp_path):
    # NOTE: the 1h horizon of the first cycle settles during the second
    # cycle's refresh (each refresh settles matured horizons) — the ledger
    # already carries the records; no extra settle call needed.
    base, _, _ = _two_cycle(tmp_path)
    rows = sa._read_jsonl(sa._ledger_path(base))
    assert len(rows) == 2  # 1h horizon only; 4h/24h not matured
    up = next(r for r in rows if r["engine"] == "Up")
    down = next(r for r in rows if r["engine"] == "Down")
    # (101-100)/100 * 10000 = +100 bps
    assert up["horizon"] == "1h"
    assert up["realized_return_bps"] == pytest.approx(100.0)
    assert up["realized_price"] == pytest.approx(101.0)
    assert up["direction"] == 1
    assert up["graded"] is True
    assert up["signed_return_bps"] == pytest.approx(100.0)
    assert up["hit"] is True
    assert up["flags"] == []
    assert down["direction"] == -1
    assert down["signed_return_bps"] == pytest.approx(-100.0)
    assert down["hit"] is False


def test_abstention_is_not_graded(tmp_path):
    base, _, _ = _two_cycle(tmp_path, agents=[_agent("Meh", 0.02)])
    rows = sa._read_jsonl(sa._ledger_path(base))
    assert len(rows) == 1
    rec = rows[0]
    assert rec["graded"] is False
    assert rec["hit"] is None
    assert rec["signed_return_bps"] is None
    assert "abstention" in rec["flags"]
    # abstentions never enter the rankings
    assert sa.rankings(base=base) == []


def test_ledger_record_schema(tmp_path):
    base, _, _ = _two_cycle(tmp_path)
    rec = sa._read_jsonl(sa._ledger_path(base))[0]
    for key in ("schema_version", "snapshot_id", "engine", "family", "symbol",
                "cycle_id", "entry_ts", "entry_price", "input", "horizon",
                "horizon_s", "realized_ts", "realized_price",
                "realized_return_bps", "direction", "graded",
                "signed_return_bps", "hit", "flags", "recorded_ts"):
        assert key in rec, f"missing key {key}"
    assert set(rec["input"]) == {"score", "confidence", "contribution"}


# ---------------------------------------------------------------------------
# 3. Decay math + 20-observation gating
# ---------------------------------------------------------------------------

def test_decay_math():
    ranks = sa.rankings([_graded("E", 100.0, True), _graded("E", -50.0, False)])
    assert len(ranks) == 1
    e = ranks[0]
    # n = 1*0.97 + 1 = 1.97 ; h = 1*0.97 + 0 = 0.97 ; s = 100*0.97 - 50 = 47
    assert e["observations"] == pytest.approx(1.97)
    assert e["ranked"] is False
    # unranked engines report no hit-rate (council_calibration neutrality rule)
    assert e["decayed_hit_rate"] is None
    assert e["decayed_mean_signed_bps"] is None


def test_min_observation_gating():
    # 20 raw records still leave DECAYED n (~15.2) under the 20-obs bar
    ranks = sa.rankings([_graded("G", 10.0, True) for _ in range(20)])
    assert ranks[0]["ranked"] is False
    # 40 raw records push decayed n (~23.5) over the bar -> ranked
    ranks = sa.rankings([_graded("G", 10.0, True) for _ in range(40)])
    g = ranks[0]
    assert g["ranked"] is True
    assert g["decayed_hit_rate"] == pytest.approx(1.0)
    assert g["decayed_mean_signed_bps"] == pytest.approx(10.0)


def test_rankings_sort_by_mean_signed_desc():
    rows = ([_graded("Loser", -5.0, False) for _ in range(40)]
            + [_graded("Winner", 8.0, True) for _ in range(40)])
    ranks = sa.rankings(rows)
    assert [r["engine"] for r in ranks] == ["Winner", "Loser"]
    assert ranks[0]["decayed_mean_signed_bps"] > ranks[1]["decayed_mean_signed_bps"]


def test_ungraded_rows_ignored_by_rankings():
    rows = [{"engine": "X", "family": "council", "graded": False,
             "signed_return_bps": None, "hit": None}]
    assert sa.rankings(rows) == []


# ---------------------------------------------------------------------------
# 4. Missing prices -> None, never invented
# ---------------------------------------------------------------------------

def test_missing_price_after_grace_settles_as_none(tmp_path):
    base = str(tmp_path)
    sa.refresh(research=[_entry("BTC", 100.0, [_agent("Up", 0.6)])],
               cycle_id=1, now_ts=T0, base=base)
    # no price observations at all; settle after the 24h horizon + full grace
    stats = sa.settle_matured(now_ts=T0 + 86400 + 48 * 3600 + 1, base=base)
    assert stats["settled_records"] == 3  # 1h, 4h, 24h — all as missing
    assert stats["pending_remaining"] == 0
    for rec in sa._read_jsonl(sa._ledger_path(base)):
        assert rec["realized_price"] is None
        assert rec["realized_return_bps"] is None
        assert rec["graded"] is False
        assert rec["hit"] is None
        assert rec["signed_return_bps"] is None
        assert "no_observation_after_grace" in rec["flags"]


def test_pending_survives_until_grace_expires(tmp_path):
    base = str(tmp_path)
    sa.refresh(research=[_entry("BTC", 100.0, [_agent("Up", 0.6)])],
               cycle_id=1, now_ts=T0, base=base)
    # 1h matured but grace not expired and no observation -> still pending
    stats = sa.settle_matured(now_ts=T0 + 3600 + 10, base=base)
    assert stats["settled_records"] == 0
    assert stats["pending_remaining"] == 1
    assert sa._read_jsonl(sa._ledger_path(base)) == []


def test_record_observations_skips_invalid_prices(tmp_path):
    base = str(tmp_path)
    n = sa.record_observations(
        [_entry("BTC", 100.0, []), _entry("ETH", 0.0, []),
         _entry("SOL", None, [])],
        ts=T0, base=base)
    assert n == 1
    obs = sa._load_observations(base)
    assert list(obs) == ["BTC"]


# ---------------------------------------------------------------------------
# 5. refresh() orchestration: never raises, env override, payload round-trip
# ---------------------------------------------------------------------------

def test_refresh_never_raises(tmp_path):
    base = str(tmp_path)
    p = sa.refresh(research=None, base=base)
    assert isinstance(p, dict) and p["enabled"] is True
    p = sa.refresh(research=[{"nope": 1}, "garbage", None], base=base)
    assert isinstance(p, dict) and p["stale"] is True  # errors recorded
    p = sa.refresh(research=None, cycle_id=None, board=None, base=base)
    assert p["schema_version"] == 1


def test_env_disable_skips_all_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_ATTRIBUTION_ENABLED", "0")
    base = str(tmp_path)
    p = sa.refresh(research=[_entry("BTC", 100.0, [_agent("Up", 0.6)])],
                   base=base)
    assert p["enabled"] is False
    assert not os.path.exists(sa._public_path(base))
    assert not os.path.exists(sa._ledger_path(base))


def test_public_payload_roundtrip(tmp_path):
    base = str(tmp_path)
    sa.refresh(research=[_entry("BTC", 100.0, [_agent("Up", 0.6)])],
               cycle_id=3, now_ts=T0, base=base)
    payload = sa.load_payload(base=base)
    assert payload["schema_version"] == 1
    assert payload["cycle_id"] == 3
    assert payload["snapshots_saved"] == 1
    assert "attribution is correlational" in payload["disclaimer"]


def test_load_payload_missing_is_empty(tmp_path):
    assert sa.load_payload(base=str(tmp_path)) == {}


def test_summary_for_status():
    payload = {
        "ts": "2026-09-19T00:00:00+00:00", "enabled": True,
        "ledger_records": 40, "pending_snapshots": 2, "stale": False,
        "errors": [],
        "rankings": [{
            "engine": "Up", "family": "council", "observations": 23.48,
            "ranked": True, "decayed_hit_rate": 0.8,
            "decayed_mean_signed_bps": 12.5}],
    }
    s = sa.summary_for_status(payload)
    assert s["available"] is True
    assert s["engines_ranked"] == 1
    assert s["top"][0] == {"engine": "Up", "hit_rate": 0.8,
                           "mean_signed_bps": 12.5}
    assert s["min_observations"] == 20
    assert sa.summary_for_status({}) == {"available": False}


# ---------------------------------------------------------------------------
# 6. main.py hook is fault-isolated
# ---------------------------------------------------------------------------

def _import_main(monkeypatch):
    """Import main.py offline: stub dotenv (absent from the bare test env)."""
    from types import ModuleType
    stub = ModuleType("dotenv")
    stub.load_dotenv = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "dotenv", stub)
    import main as main_mod  # noqa: E402
    return main_mod


def test_main_hook_fault_isolated(tmp_path, monkeypatch):
    main_mod = _import_main(monkeypatch)

    calls = []

    def boom(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("ledger exploded")

    monkeypatch.setattr(sa, "refresh", boom)
    firm = SimpleNamespace(cfg=SimpleNamespace(signal_attribution_enabled=True))
    # must not propagate even though the ledger write explodes
    main_mod._maybe_signal_attribution(
        firm, {"research": [], "cycle": 9, "board": {}})
    assert len(calls) == 1
    assert calls[0]["cycle_id"] == 9


def test_main_hook_respects_disabled_flag(tmp_path, monkeypatch):
    main_mod = _import_main(monkeypatch)

    def boom(**kwargs):
        raise AssertionError("refresh must not run when disabled")

    monkeypatch.setattr(sa, "refresh", boom)
    firm = SimpleNamespace(cfg=SimpleNamespace(signal_attribution_enabled=False))
    main_mod._maybe_signal_attribution(firm, {"research": []})  # no raise
    # missing flag defaults to disabled too
    main_mod._maybe_signal_attribution(
        SimpleNamespace(cfg=SimpleNamespace()), {"research": []})
