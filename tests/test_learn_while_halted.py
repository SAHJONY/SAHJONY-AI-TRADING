"""Tests for the learn-while-halted guarantee (intel/shadow_learning.py).

When the desk is halted or stood down to dry-run (kill switch, daily circuit
breaker, self-heal circuit breaker / 3-strike escalation, cadence guard, LIVE
reconciliation failure), order emission is suppressed — but the brain must keep
learning. These tests assert, fully offline with synthetic fixtures:

  (a) calibration grading (council + regime) still runs on halted cycles;
  (b) suppressed entry intents are recorded as shadow (paper) decisions;
  (c) shadow decisions are later graded against synthetic price moves;
  (d) NO real order can be emitted through the shadow path;
  (e) live/unhalted behavior is unchanged (no shadow records when not halted).

The trading loop's risk envelope is never touched here: tests never place
orders outside the offline simulator, never touch credentials, and never
promise profit.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from intel.shadow_learning import (  # noqa: E402
    ShadowLearning,
    _FORBIDDEN_TOKENS,
    _SIDE_SIGN,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _env(monkeypatch, tmp_path, **overrides):
    monkeypatch.setenv("SAHJONY_HOME", str(tmp_path))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("ROBINHOOD_LIVE", "false")
    monkeypatch.setenv("LIVE_TRADING_ACK", "")
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)


def _load_cfg():
    from config import load_config
    return load_config()


def _make_firm(cfg, tmp_path):
    from database import Database
    from utils.alpaca_client import AlpacaClient
    from workforce import Firm
    db = Database(str(tmp_path / "t.db"))
    client = AlpacaClient(cfg)  # no credentials -> offline-sim, no real orders
    firm = Firm(cfg, client, db)
    return firm, client, db


def _entry_intent(symbol="AAPL", side="buy", qty=10.0):
    from strategies.base import OrderIntent
    return OrderIntent(symbol=symbol, strategy="ladder", kind="equity",
                       purpose="ladder_entry", reason="test entry rationale",
                       side=side, qty=qty, est_notional=1000.0, risk_check=True)


# ── (d1) the shadow module cannot emit orders — static guarantee ─────────────

def test_shadow_module_has_no_order_emission_path():
    src_path = os.path.join(REPO, "intel", "shadow_learning.py")
    with open(src_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    # the tokens are named once, in the self-declared forbidden list; they must
    # appear NOWHERE else (no call site, no import, no client wiring).
    import re
    src_wo_guard = re.sub(r"_FORBIDDEN_TOKENS\s*=\s*\([^)]*\)", "", src)
    for tok in _FORBIDDEN_TOKENS:
        assert tok not in src_wo_guard, \
            f"forbidden order-emission token outside the guard list: {tok}"
    # the module must not import any broker/venue client at all
    assert "alpaca" not in src_wo_guard.lower()
    assert "robinhood" not in src_wo_guard.lower()
    assert "ccxt" not in src_wo_guard.lower()
    # and the recorder/grader never reference a client attribute
    assert "self.client" not in src_wo_guard


# ── (b)+(d2) halted execute(): suppressed intent recorded, nothing emitted ────

def test_halted_execute_records_shadow_and_emits_nothing(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, TRADING_HALT="true")
    cfg = _load_cfg()
    assert cfg.trading_halt is True
    firm, client, _db = _make_firm(cfg, tmp_path)

    def _boom(*a, **k):
        raise AssertionError("REAL ORDER EMISSION ATTEMPTED through halted path")
    monkeypatch.setattr(client, "submit_equity_order", _boom)
    monkeypatch.setattr(client, "submit_option_order", _boom)

    from utils.state_store import default_state
    state = default_state()
    state["_shadow_halt"] = {"halted": True, "reason": "test kill switch"}
    state["_shadow_ctx"] = {"AAPL": {"conviction": 0.7, "tilts": {"stacked": 0.05},
                                     "direction": "long", "regime": "calm",
                                     "strategy": "ladder"}}

    done, _deployed = firm.execution.execute(
        [_entry_intent()], state, 7, 10_000.0, 0.0, 0.75, allow_new_risk=False)

    assert done == [], "halted execute() must emit nothing"
    # ^ would have raised AssertionError above if any submit was attempted
    sl = firm.shadow_learning
    assert sl is not None and sl.enabled
    assert sl.pending_count() == 1
    dec = sl._decisions[-1]
    assert dec["symbol"] == "AAPL"
    assert dec["side"] == "buy"
    assert dec["qty"] == 10.0
    assert dec["price"] > 0, "arrival price captured at suppression time"
    assert dec["conviction"] == pytest.approx(0.75)
    assert dec["halt"]["halted"] is True
    assert dec["halt"]["reason"] == "test kill switch"
    assert dec["scores"]["direction"] == "long"
    assert dec["scores"]["regime"] == "calm"
    assert dec["rationale"] == "test entry rationale"
    assert dec["graded"] is False
    # durable JSONL trail
    rows = [json.loads(l) for l in open(sl.path, encoding="utf-8")]
    assert len(rows) == 1 and rows[0]["id"] == dec["id"]


# ── (e1) unhalted execute(): orders flow, shadow ledger stays empty ────────────

def test_unhalted_execute_emits_and_records_nothing(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, TRADING_HALT="false")
    cfg = _load_cfg()
    firm, client, _db = _make_firm(cfg, tmp_path)

    submitted = []
    orig_eq = client.submit_equity_order
    def _spy(symbol, qty, side):
        submitted.append((symbol, qty, side))
        return orig_eq(symbol, qty, side)
    monkeypatch.setattr(client, "submit_equity_order", _spy)

    from utils.state_store import default_state
    state = default_state()
    done, _deployed = firm.execution.execute(
        [_entry_intent()], state, 3, 10_000.0, 0.0, 0.75, allow_new_risk=True)

    assert submitted, "unhalted path must still reach the broker/sim client"
    assert len(done) >= 1
    assert firm.shadow_learning.pending_count() == 0
    assert not os.path.exists(firm.shadow_learning.path), \
        "no shadow ledger file when nothing was ever suppressed"


# ── (e2) env kill-switch disables recording entirely ──────────────────────────

def test_shadow_disabled_by_env_records_nothing(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, TRADING_HALT="true", SHADOW_LEARNING_ENABLED="0")
    cfg = _load_cfg()
    assert cfg.shadow_learning_enabled is False  # env gates cfg flag too
    firm, _client, _db = _make_firm(cfg, tmp_path)
    # Firm never constructs the module when the flag is off ...
    assert firm.shadow_learning is None
    assert firm.execution.shadow_learning is None  # getattr-guarded: no crash

    from utils.state_store import default_state
    state = default_state()
    state["_shadow_halt"] = {"halted": True, "reason": "test"}
    done, _d = firm.execution.execute(
        [_entry_intent()], state, 1, 10_000.0, 0.0, 0.75, allow_new_risk=False)
    assert done == []  # the halt block itself still suppresses normally


def test_shadow_disabled_by_cfg_flag(monkeypatch, tmp_path):
    # env ON (module itself would enable) but the cfg flag off: Firm must not
    # construct or wire the module, and the halt path must stay crash-free.
    _env(monkeypatch, tmp_path, TRADING_HALT="true", SHADOW_LEARNING_ENABLED="1")
    import dataclasses
    cfg = dataclasses.replace(_load_cfg(), shadow_learning_enabled=False)
    firm, _client, _db = _make_firm(cfg, tmp_path)
    assert firm.shadow_learning is None
    assert firm.execution.shadow_learning is None  # getattr-guarded: no crash

    from utils.state_store import default_state
    state = default_state()
    state["_shadow_halt"] = {"halted": True, "reason": "test"}
    done, _d = firm.execution.execute(
        [_entry_intent()], state, 1, 10_000.0, 0.0, 0.75, allow_new_risk=False)
    assert done == []


# ── (c) grading against synthetic price moves ─────────────────────────────────

def test_shadow_grading_against_synthetic_moves(tmp_path):
    sl = ShadowLearning(path=str(tmp_path / "shadow.jsonl"))
    state: dict = {}

    sl.record_shadow(intent=_entry_intent(symbol="AAA", side="buy"), state={},
                     cycle=1, conviction=0.8,
                     halt={"halted": True, "reason": "t"},
                     get_price=lambda s: 100.0, mode="offline-sim")
    sl.record_shadow(intent=_entry_intent(symbol="BBB", side="sell"), state={},
                     cycle=1, conviction=0.6,
                     halt={"halted": True, "reason": "t"},
                     get_price=lambda s: 100.0, mode="offline-sim")
    assert sl.pending_count() == 2

    # AAA rallies to 110 (buy correct), BBB rallies to 110 (sell wrong)
    out = sl.grade_pending(state, lambda s: {"AAA": 110.0, "BBB": 110.0}[s],
                           current_cycle=2)
    assert len(out["graded"]) == 2 and out["skipped"] == 0
    by_sym = {g["symbol"]: g for g in out["graded"]}
    assert by_sym["AAA"]["correct"] is True
    assert by_sym["AAA"]["fwd_return"] == pytest.approx(0.10)
    assert by_sym["BBB"]["correct"] is False
    assert by_sym["BBB"]["fwd_return"] == pytest.approx(-0.10)
    assert sl.pending_count() == 0

    # grading is idempotent — a second pass re-grades nothing
    out2 = sl.grade_pending(state, lambda s: 999.0, current_cycle=3)
    assert out2["graded"] == [] and out2["skipped"] == 0

    # same-cycle decisions are NOT graded early (no forward move observed yet)
    sl.record_shadow(intent=_entry_intent(symbol="CCC", side="buy"), state={},
                     cycle=3, conviction=0.5,
                     halt={"halted": True, "reason": "t"},
                     get_price=lambda s: 50.0, mode="offline-sim")
    out3 = sl.grade_pending(state, lambda s: 60.0, current_cycle=3)
    assert out3["graded"] == [] and sl.pending_count() == 1

    # unpriceable symbols are skipped, not failed
    out4 = sl.grade_pending(state, lambda s: 0.0, current_cycle=4)
    assert out4["graded"] == [] and out4["skipped"] == 1


def test_side_sign_map_covers_all_intent_sides():
    assert _SIDE_SIGN["buy"] == 1.0
    assert _SIDE_SIGN["buy_to_open"] == 1.0
    assert _SIDE_SIGN["sell_to_close"] == 1.0
    assert _SIDE_SIGN["sell"] == -1.0
    assert _SIDE_SIGN["sell_to_open"] == -1.0
    assert _SIDE_SIGN["buy_to_close"] == -1.0


# ── (a)+(b)+(d3) full halted cycles: learning continues, nothing emitted ───────

def test_halted_cycle_keeps_learning_and_emits_nothing(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, TRADING_HALT="true")
    cfg = _load_cfg()
    firm, client, _db = _make_firm(cfg, tmp_path)

    def _boom(*a, **k):
        raise AssertionError("REAL ORDER EMISSION ATTEMPTED during halted cycle")
    monkeypatch.setattr(client, "submit_equity_order", _boom)
    monkeypatch.setattr(client, "submit_option_order", _boom)

    from utils.state_store import default_state
    state = default_state()

    for _ in range(2):  # two cycles: grade last cycle's calls on the second
        result = firm.run_cycle(state, trade=True)
        assert result["halt"]["halted"] is True
        assert result["executed"] == [], "halted cycle must execute zero orders"
        # the main.py grading hook path, exercised directly:
        graded = firm.shadow_learning.grade_pending(
            state, client.get_price, int(state.get("cycle", 0) or 0))
        client.advance_sim(1)

    # (a) calibration grading STILL RAN while halted (not gated on the halt)
    acc = (state.get("council_cal") or {}).get("acc") or {}
    assert acc, "council calibration graded nothing during the halt"
    assert any((m.get("n") or 0) > 0 for m in acc.values()), \
        "no graded agent observations accumulated while halted"
    assert "regime_cal" in state, "regime calibration memory missing after halted cycles"
    # self-review / trade-memory wiring intact (nightly pieces still scheduled)
    assert firm.self_review is not None
    assert firm.trade_memory is not None

    # (b) suppressed entries were recorded as shadow decisions ...
    assert firm.shadow_learning.pending_count() + len(
        (state.get("shadow_learn") or {}).get("graded_ids") or []) > 0, \
        "no shadow decisions recorded across two halted cycles"
    # ... and the earlier cycle's decisions got graded against realized moves
    graded_ids = (state.get("shadow_learn") or {}).get("graded_ids") or []
    assert len(graded_ids) > 0, "shadow decisions were never graded"
    grades = (state.get("shadow_learn") or {}).get("grades") or []
    assert all("correct" in g and "fwd_return" in g for g in grades)

    # (d3) the would-be orders never reached any submit path (else _boom raised)


# ── wiring: main.py grading hook exists and is flag-gated ─────────────────────

def test_main_py_grading_hook_present_and_gated():
    with open(os.path.join(REPO, "main.py"), "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "grade_pending" in src
    assert 'getattr(firm.cfg, "shadow_learning_enabled", False)' in src
    # the hook runs AFTER the trading pipeline ...
    assert src.index("firm.run_cycle(state, trade=trade)") < src.index("grade_pending")
    # ... and never touches order emission or the halt decision
    hook = src[src.index("Shadow-learning grading"):]
    hook = hook[:hook.index("status = build_status")]
    assert "submit" not in hook
    assert "trading_halt" not in hook.replace("shadow_learning_enabled", "")
