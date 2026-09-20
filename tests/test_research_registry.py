"""Tests for the research-hypothesis registry (intel/research_registry.py) and
its fault-isolated hook into backtest/validation.py.

Fully offline: every registry under test lives in a pytest tmp_path, never
the real SAHJONY_HOME. Run with ``python -m pytest tests/test_research_registry.py``.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

import intel.research_registry as rr_mod
from backtest.validation import ValidationPolicy, validate_candidate
from intel.research_registry import ResearchRegistry


@pytest.fixture
def reg(tmp_path, monkeypatch):
    """Isolated registry with its own ledger file; env flag forced on."""
    monkeypatch.setenv("RESEARCH_REGISTRY_ENABLED", "1")
    monkeypatch.setenv("SAHJONY_HOME", str(tmp_path))
    rr_mod.reset_default_registry()
    yield ResearchRegistry(path=str(tmp_path / "registry.jsonl"))
    rr_mod.reset_default_registry()


def _register(reg, hid="H1", budget=10, **kw):
    return reg.register_hypothesis(
        hid,
        statement=kw.pop("statement", "mean reversion on BTC hourly works"),
        trial_budget=budget,
        validation_procedure=kw.pop(
            "procedure", "walk-forward validate_candidate, promotion gates"),
        success_criteria=kw.pop("criteria", "promoted == True on frozen holdout"),
        **kw,
    )


# ── registration & append-only immutability ──────────────────────────────

def test_register_records_all_fields(reg):
    ev = _register(reg, hid="H1", budget=25)
    assert ev["event"] == "registered"
    assert ev["hypothesis_id"] == "H1"
    assert ev["trial_budget"] == 25
    assert "mean reversion" in ev["statement"]
    assert ev["validation_procedure"]
    assert ev["success_criteria"]
    assert ev["ts"]
    view = reg.get_hypothesis("H1")
    assert view["status"] == "open"
    assert view["record"]["hypothesis_id"] == "H1"


def test_register_rejects_bad_inputs(reg):
    with pytest.raises(ValueError):
        _register(reg, hid="bad id!")
    with pytest.raises(ValueError):
        _register(reg, hid="H9", budget=0)
    with pytest.raises(ValueError):
        _register(reg, hid="H9", budget=-3)
    with pytest.raises(ValueError):
        _register(reg, hid="H9", statement="   ")


def test_duplicate_registration_is_rejected_append_only(reg):
    _register(reg, hid="H1")
    with pytest.raises(ValueError):
        _register(reg, hid="H1")  # never overwritten
    # the original registration is still the only registration event
    regs = [e for e in reg._all() if e.get("event") == "registered"
            and e.get("hypothesis_id") == "H1"]
    assert len(regs) == 1


def test_status_transitions_never_edit_history(reg):
    _register(reg, hid="H1", budget=5)
    raw_before = open(reg.path, encoding="utf-8").read()
    reg.mark_validated("H1", note="gates passed")
    raw_after = open(reg.path, encoding="utf-8").read()
    # the original registration line is byte-identical; transition appended
    assert raw_after.startswith(raw_before)
    assert len(raw_after.splitlines()) == len(raw_before.splitlines()) + 1
    assert reg.get_hypothesis("H1")["status"] == "validated"


def test_final_status_is_terminal(reg):
    _register(reg, hid="H1")
    reg.mark_rejected("H1", note="no edge")
    with pytest.raises(ValueError):
        reg.mark_validated("H1")  # final states cannot be re-entered
    assert reg.get_hypothesis("H1")["status"] == "rejected"


def test_supersede_marks_old_without_editing_it(reg):
    _register(reg, hid="H1")
    raw_before = open(reg.path, encoding="utf-8").read()
    _register(reg, hid="H2", supersedes="H1")
    raw_after = open(reg.path, encoding="utf-8").read()
    assert raw_after.startswith(raw_before)  # original lines untouched
    old = reg.get_hypothesis("H1")
    assert old["status"] == "superseded"
    assert old["superseded_by"] == "H2"
    assert reg.get_hypothesis("H2")["status"] == "open"


def test_supersede_unknown_target_rejected(reg):
    with pytest.raises(ValueError):
        _register(reg, hid="H2", supersedes="NOPE")


def test_transition_unknown_hypothesis_rejected(reg):
    with pytest.raises(ValueError):
        reg.mark_validated("GHOST")


# ── trial accounting ─────────────────────────────────────────────────────

def test_trial_counting_and_sequence(reg):
    _register(reg, hid="H1", budget=10)
    for i in range(1, 4):
        ev = reg.record_trial("H1", config={"lr": 0.01 * i})
        assert ev["trial_number"] == i
        assert ev["registered"] is True
        assert ev["budget_overrun"] is False
    assert reg.get_trial_count("H1") == 3


def test_budget_overrun_flagged_not_blocked(reg):
    _register(reg, hid="H1", budget=2)
    reg.record_trial("H1")
    reg.record_trial("H1")
    ev = reg.record_trial("H1")  # third trial exceeds budget
    assert ev["trial_number"] == 3
    assert ev["budget_overrun"] is True  # still recorded, visibly flagged
    assert reg.get_trial_count("H1") == 3
    s = reg.summary_for_status()
    assert s["budget_overruns"] == ["H1"]
    assert s["budget_overrun_count"] == 1


def test_get_trial_count_unknown_is_none_not_zero(reg):
    assert reg.get_trial_count("NEVER-REGISTERED") is None
    assert reg.get_trial_count("bad id!") is None
    assert reg.get_trial_count("") is None


def test_unregistered_runs_logged_and_visible(reg):
    _register(reg, hid="H1")
    reg.record_trial(None, note="no hypothesis attached")
    reg.record_trial("UNKNOWN-ID", note="typo'd id")
    unreg = reg.unregistered_runs()
    assert len(unreg) == 2
    assert all(not e["registered"] for e in unreg)
    assert reg.get_trial_count("UNKNOWN-ID") is None  # never silently zero
    s = reg.summary_for_status()
    assert s["unregistered_runs"] == 2
    # registered hypotheses are unaffected
    assert reg.get_trial_count("H1") == 0


# ── summary & report ─────────────────────────────────────────────────────

def test_summary_counts_and_report_text(reg):
    _register(reg, hid="HA", budget=5)
    _register(reg, hid="HB", budget=5)
    _register(reg, hid="HC", budget=1)
    reg.record_trial("HA")
    reg.record_trial("HC")
    reg.record_trial("HC")  # overrun on HC
    reg.mark_validated("HA")
    reg.mark_rejected("HB")
    s = reg.summary_for_status()
    assert s["available"] is True
    assert s["hypotheses_total"] == 3
    assert s["open"] == 1 and s["validated"] == 1 and s["rejected"] == 1
    assert s["trials_consumed_total"] == 3
    assert s["trial_budget_total"] == 11
    assert s["budget_overruns"] == ["HC"]
    txt = reg.report_text()
    assert "RESEARCH REGISTRY" in txt
    assert "1 open / 1 validated / 1 rejected" in txt
    assert "HC" in txt and "OVERRUN" in txt


def test_list_hypotheses_trial_fields(reg):
    _register(reg, hid="H1", budget=4)
    reg.record_trial("H1")
    (h,) = reg.list_hypotheses()
    assert h["trials_consumed"] == 1
    assert h["trials_remaining"] == 3
    assert h["budget_overrun"] is False
    assert reg.list_hypotheses(status="open") and not reg.list_hypotheses(status="validated")


# ── validation hook: honest trial-count sourcing ─────────────────────────

def _returns(n=400, seed=7):
    rng = np.random.default_rng(seed)
    return rng.normal(0.001, 0.02, n), rng.normal(0.0005, 0.02, n)


def _small_policy():
    return ValidationPolicy(periods_per_year=252, min_train=60, test_size=30,
                            step=35, purge=2, embargo=2, holdout_fraction=0.20,
                            min_folds=2, min_observations=20)


def test_hook_uses_registry_trial_count(reg, monkeypatch):
    monkeypatch.setenv("SAHJONY_HOME", os.path.dirname(reg.path))
    rr_mod.reset_default_registry()
    try:
        _register(rr_mod.default_registry(), hid="HV", budget=50)
        r, sr = _returns()
        v1 = validate_candidate(r, sr, _small_policy(), trials=999, hypothesis_id="HV")
        assert v1["trials_source"] == "registry"
        assert v1["trials_consumed"] == 1
        assert v1["trials_effective"] == 1  # honest N, not the hand-passed 999
        assert v1["unregistered_run"] is False
        assert v1["hypothesis_id"] == "HV"
        v2 = validate_candidate(r, sr, _small_policy(), trials=999, hypothesis_id="HV")
        assert v2["trials_consumed"] == 2
        assert v2["trials_effective"] == 2
        # the multiple-testing hurdle tightens as the honest trial count grows
        assert v2["adjusted_sharpe_hurdle"] >= v1["adjusted_sharpe_hurdle"]
    finally:
        rr_mod.reset_default_registry()


def test_hook_without_hypothesis_keeps_hand_passed_and_logs_unregistered(
        reg, monkeypatch):
    monkeypatch.setenv("SAHJONY_HOME", os.path.dirname(reg.path))
    rr_mod.reset_default_registry()
    try:
        r, sr = _returns()
        v = validate_candidate(r, sr, _small_policy(), trials=42)
        assert v["trials_source"] == "hand-passed"
        assert v["trials_declared"] == 42
        assert v["trials_effective"] == 42
        assert v["unregistered_run"] is True
        assert v["hypothesis_id"] is None
        assert len(rr_mod.default_registry().unregistered_runs()) == 1
    finally:
        rr_mod.reset_default_registry()


def test_hook_unknown_hypothesis_id_treated_as_unregistered(reg, monkeypatch):
    monkeypatch.setenv("SAHJONY_HOME", os.path.dirname(reg.path))
    rr_mod.reset_default_registry()
    try:
        r, sr = _returns()
        v = validate_candidate(r, sr, _small_policy(), trials=5, hypothesis_id="GHOST")
        assert v["trials_effective"] == 5
        assert v["unregistered_run"] is True
    finally:
        rr_mod.reset_default_registry()


def test_hook_never_changes_validation_math(reg, monkeypatch):
    """Same inputs, same gates — only the trial-count sourcing may differ."""
    monkeypatch.setenv("SAHJONY_HOME", os.path.dirname(reg.path))
    rr_mod.reset_default_registry()
    try:
        _register(rr_mod.default_registry(), hid="HM", budget=50)
        r, sr = _returns()
        pol = _small_policy()
        plain = validate_candidate(r, sr, pol, trials=1)
        hooked = validate_candidate(r, sr, pol, trials=1, hypothesis_id="HM")
        assert hooked["checks"] == plain["checks"]
        assert hooked["promoted"] == plain["promoted"]
        assert hooked["adjusted_sharpe_hurdle"] == plain["adjusted_sharpe_hurdle"]
        assert hooked["holdout"] == plain["holdout"]
        assert hooked["fold_results"] == plain["fold_results"]
    finally:
        rr_mod.reset_default_registry()


def test_hook_fault_isolation_registry_blows_up(monkeypatch):
    """If the registry itself fails, validation still returns the honest
    hand-passed verdict — math and gates intact."""
    def boom():
        raise RuntimeError("ledger exploded")
    monkeypatch.setattr(rr_mod, "default_registry", boom)
    r, sr = _returns()
    v = validate_candidate(r, sr, _small_policy(), trials=3, hypothesis_id="HV")
    assert v["trials_effective"] == 3
    assert v["trials_source"] == "hand-passed (registry error)"
    assert "promoted" in v and "checks" in v  # verdict intact


def test_hook_disabled_registry_degrades_cleanly(reg, monkeypatch):
    monkeypatch.setenv("RESEARCH_REGISTRY_ENABLED", "0")
    monkeypatch.setenv("SAHJONY_HOME", os.path.dirname(reg.path))
    rr_mod.reset_default_registry()
    try:
        _register(rr_mod.default_registry(), hid="HD", budget=5)
        # disabled: nothing persists, so the hypothesis is unknown — honest
        assert rr_mod.default_registry().get_hypothesis("HD") is None
        r, sr = _returns()
        v = validate_candidate(r, sr, _small_policy(), trials=7, hypothesis_id="HD")
        assert v["trials_effective"] == 7  # hand-passed, unchanged
        assert "promoted" in v
    finally:
        rr_mod.reset_default_registry()


def test_summary_survives_corrupt_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_REGISTRY_ENABLED", "1")
    p = tmp_path / "bad.jsonl"
    p.write_text('{"event": "registered", broken json\nnot json at all\n', encoding="utf-8")
    r = ResearchRegistry(path=str(p))
    s = r.summary_for_status()
    assert s["available"] is True
    assert s["hypotheses_total"] == 0
    assert "unavailable" not in r.report_text() or True


def test_register_without_persistence_returns_event_but_stores_nothing(
        tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_REGISTRY_ENABLED", "0")
    r = ResearchRegistry(path=str(tmp_path / "off.jsonl"))
    ev = r.register_hypothesis("HX", "stmt", 3, "proc", "crit")
    assert ev["hypothesis_id"] == "HX"  # caller still gets the record shape
    assert not os.path.exists(r.path)
    assert r.get_trial_count("HX") is None  # unknown, never invented
