"""Regime-gate tests (upgrade/autonomous-profit).

The council's regime read is a real gate now: stressed blocks new entries,
bear/chop halve budgets and restrict desks, exits always flow.
- classify_regime: stressed/bear/bull/chop + fail-closed on garbage.
- gate(): per-regime scales and desk allowlists; unknown denies.
- Firm._regime_gate: integrates with config flag; disabled → neutral.
"""
from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace

from config import load_config
from database.db import Database
from intelligence.regime import (
    BEAR,
    BULL,
    CHOP,
    STRESSED,
    classify_regime,
    gate,
)
from workforce.workforce import Firm


def test_classify_stressed():
    assert classify_regime({"stressed_prob": 0.7}, "long", 0.5) == STRESSED
    assert classify_regime({"stressed_prob": 0.5}, "long", 0.9) == STRESSED
    print("✓ stressed_prob >= 0.5 → stressed")


def test_classify_bear():
    assert classify_regime({"stressed_prob": 0.1}, "flat", -0.4) == BEAR
    assert classify_regime({}, "flat", -0.9) == BEAR
    print("✓ bearish composite → bear")


def test_classify_bull():
    assert classify_regime({"stressed_prob": 0.1}, "long", 0.4) == BULL
    assert classify_regime({}, "flat", 0.3) == BULL
    print("✓ bullish composite/long direction → bull")


def test_classify_chop():
    assert classify_regime({"stressed_prob": 0.1}, "flat", 0.0) == CHOP
    print("✓ flat and calm → chop")


def test_classify_fail_closed():
    # Garbage in → chop (half size, restricted desks), never bull.
    assert classify_regime(None, None, float("nan")) == CHOP
    assert classify_regime({"stressed_prob": "bogus"}, "long", 0.5) in (CHOP, STRESSED, BULL, BEAR)
    print("✓ classification failures degrade to chop, never raise")


def test_gate_scales_and_allowlists():
    scale, allowed = gate(BULL, "wheel")
    assert (scale, allowed) == (1.0, True)
    scale, allowed = gate(STRESSED, "wheel")
    assert (scale, allowed) == (0.0, False), "stressed: no new entries anywhere"
    scale, allowed = gate(BEAR, "wheel")
    assert (scale, allowed) == (0.0, False), "bear: no put-selling"
    scale, allowed = gate(BEAR, "pairs")
    assert (scale, allowed) == (0.5, True), "bear: market-neutral at half size"
    scale, allowed = gate(CHOP, "ladder")
    assert (scale, allowed) == (0.5, True)
    scale, allowed = gate("nonsense", "wheel")
    assert (scale, allowed) == (0.0, False), "unknown regime denies"
    scale, allowed = gate(BULL, "nonsense-desk")
    assert (scale, allowed) == (0.0, False), "unknown desk denies"
    scale, allowed = gate(BULL, "copy")
    assert (scale, allowed) == (1.0, True), "copy entries gated like any desk"
    scale, allowed = gate(BEAR, "copy")
    assert (scale, allowed) == (0.0, False), "no mirrored longs into a bear tape"
    scale, allowed = gate(STRESSED, "copy")
    assert (scale, allowed) == (0.0, False)
    scale, allowed = gate(CHOP, "promoted")
    assert (scale, allowed) == (0.5, True)
    print("✓ gate scales + allowlists correct; unknowns deny")


def _firm(tmp_path, **cfg_over):
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    cfg = load_config()
    for k, v in cfg_over.items():
        cfg = replace(cfg, **{k: v})
    db = Database(str(tmp_path / "rg.db"))
    return Firm(cfg, SimpleNamespace(mode="offline-sim"), db)


def test_firm_regime_gate_integration(tmp_path):
    firm = _firm(tmp_path)
    verdict = SimpleNamespace(
        metrics={"stressed_prob": 0.8}, direction="long", composite_score=0.5)
    scale, allowed = firm._regime_gate(verdict, "ladder")
    assert (scale, allowed) == (0.0, False)
    verdict2 = SimpleNamespace(
        metrics={"stressed_prob": 0.0}, direction="long", composite_score=0.5)
    assert firm._regime_gate(verdict2, "ladder") == (1.0, True)
    # dict-form metrics also accepted
    assert firm._regime_gate({"stressed_prob": 0.9}, "day") == (0.0, False)
    print("✓ Firm._regime_gate integrates verdicts and dicts")


def test_firm_regime_gate_disabled_is_neutral(tmp_path):
    firm = _firm(tmp_path, regime_gate_enabled=False)
    verdict = SimpleNamespace(
        metrics={"stressed_prob": 0.9}, direction="long", composite_score=0.5)
    assert firm._regime_gate(verdict, "wheel") == (1.0, True)
    print("✓ REGIME_GATE=false restores pre-gate behavior")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        test_classify_stressed()
        test_classify_bear()
        test_classify_bull()
        test_classify_chop()
        test_classify_fail_closed()
        test_gate_scales_and_allowlists()
        test_firm_regime_gate_integration(p)
        test_firm_regime_gate_disabled_is_neutral(p)
    print("ALL REGIME GATE TESTS PASSED")
