"""Focused tests for intel/tca.py — Perold implementation-shortfall decomposition.

All tests are deterministic, offline, and secret-free. Synthetic orders with
hand-computed legs; every assertion below was derived by hand (see comments),
not copied from the implementation.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from intel.tca import TCALedger  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────
def make_ledger(monkeypatch, **kw):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    tmp.close()
    monkeypatch.setenv("TCA_ENABLED", "1")
    return TCALedger(path=tmp.name, **kw), tmp.name


def fake_impact(pre_bps: float):
    """Stand-in for intel.impact_model.estimate_impact (square-root law)."""
    def _fn(symbol, qty, adv, sigma_daily, **kwargs):
        if adv is None or sigma_daily is None:
            return None
        return {"expected_impact_bps": pre_bps}
    return _fn


def close(module_name):
    sys.modules.pop(module_name, None)


# ── 1. legs sum to total (hand-computed) ─────────────────────────────────────
def test_legs_sum_to_total_shortfall(monkeypatch):
    # BUY Q=10, Pd=100.00, Pa=100.50, fill 6 @ 100.60, fees $0.05,
    # U=4, Pafter=101.00, pre-trade impact estimate 2.0 bps.
    #   delay   = 10 * (100.50-100.00)            = 5.00
    #   impact  = 2/10000 * 100.50 * 6            = 0.1206
    #   timing  = 6 * (100.60-100.50) - 0.1206    = 0.4794
    #   opport. = 4 * (101.00-100.50)             = 2.00
    #   fees                                        0.05
    #   total                                     = 7.65
    close("intel.impact_model")
    led, _ = make_ledger(monkeypatch, impact_fn=fake_impact(2.0))
    led.record_decision("o1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.00, adv=1_000_000, sigma_daily=0.02)
    led.record_arrival("o1", 100.50)
    led.record_fill("o1", 100.60, fill_qty=6, fees_usd=0.05)
    rec = led.finalize_order("o1", reference_price_after=101.00)

    legs = rec["legs"]
    assert legs["delay"]["usd"] == pytest.approx(5.00)
    assert legs["delay"]["bps"] == pytest.approx(50.0)
    assert legs["market_impact"]["usd"] == pytest.approx(0.1206)
    assert legs["market_impact"]["bps"] == pytest.approx(1.206)
    assert legs["timing"]["usd"] == pytest.approx(0.4794)
    assert legs["timing"]["bps"] == pytest.approx(4.794)
    assert legs["opportunity"]["usd"] == pytest.approx(2.00)
    assert legs["opportunity"]["bps"] == pytest.approx(20.0)
    assert legs["fees"]["usd"] == pytest.approx(0.05)
    assert legs["fees"]["bps"] == pytest.approx(0.5)
    assert rec["total_shortfall_usd"] == pytest.approx(7.65)
    assert rec["total_shortfall_bps"] == pytest.approx(76.5)
    # every leg carries the fill rate
    assert rec["fill_rate"] == pytest.approx(0.6)
    assert all(v["fill_rate"] == pytest.approx(0.6) for v in legs.values())
    assert rec["legs_complete"] is True
    # pre-trade vs realized honesty
    assert rec["pre_trade_impact_bps"] == pytest.approx(2.0)
    assert rec["realized_impact_bps"] == pytest.approx(9.9502)
    assert rec["estimate_error_bps"] == pytest.approx(7.9502)
    assert rec["opportunity_estimated"] is True


def test_sell_side_sign_convention(monkeypatch):
    # SELL Q=10, Pd=50.00, Pa=49.80 (adverse for seller), fill 10 @ 49.70,
    # no impact model → impact leg None, timing carries full arrival→fill.
    #   delay  = -1 * 10 * (49.80-50.00) = 2.00  (bps: -1*(-0.20)/50*1e4 = 40)
    #   timing = -1 * 10 * (49.70-49.80) = 1.00
    #   total = 3.00, legs incomplete (impact unknown)
    monkeypatch.setitem(sys.modules, "intel.impact_model", None)
    led, _ = make_ledger(monkeypatch)  # default: guarded import finds nothing
    assert led._impact_fn is None
    led.record_decision("s1", symbol="ETH", side="sell", qty=10,
                        decision_price=50.00)
    led.record_arrival("s1", 49.80)
    led.record_fill("s1", 49.70, fill_qty=10)
    rec = led.finalize_order("s1", reference_price_after=49.70)

    legs = rec["legs"]
    assert legs["delay"]["usd"] == pytest.approx(2.00)
    assert legs["delay"]["bps"] == pytest.approx(40.0)
    assert legs["market_impact"]["usd"] is None
    assert "unavailable" in (legs["market_impact"]["reason"] or "")
    assert legs["timing"]["usd"] == pytest.approx(1.00)
    assert "impact leg unavailable" in (legs["timing"]["reason"] or "")
    assert legs["opportunity"]["usd"] == pytest.approx(0.0)
    assert rec["total_shortfall_usd"] == pytest.approx(3.00)
    assert rec["legs_complete"] is False
    assert rec["total_basis"].startswith("partial")


# ── 2. missing prices → None legs with reasons ───────────────────────────────
def test_missing_prices_yield_none_legs(monkeypatch):
    close("intel.impact_model")
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    # no decision price at all (live path records decision at release)
    led.record_decision("m1", symbol="SOL", side="buy", qty=5)
    led.record_arrival("m1", 100.50)
    led.record_fill("m1", 100.60, fill_qty=5)
    rec = led.finalize_order("m1")  # no reference price either

    legs = rec["legs"]
    assert legs["delay"]["usd"] is None
    assert legs["delay"]["reason"] and "decision price" in legs["delay"]["reason"]
    assert legs["market_impact"]["usd"] is None
    # timing still computable from arrival → fill
    assert legs["timing"]["usd"] == pytest.approx(0.50)
    assert legs["opportunity"]["usd"] == pytest.approx(0.0)  # fully filled
    assert rec["total_shortfall_usd"] == pytest.approx(0.50)
    assert rec["legs_complete"] is False


def test_no_arrival_no_fill_legs(monkeypatch):
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("m2", symbol="SOL", side="buy", qty=5,
                        decision_price=100.0)
    led.note_unfilled("m2", reason="risk blocked before release")
    rec = led.finalize_order("m2")  # no arrival, no fills, no reference
    assert rec["legs"]["delay"]["usd"] is None
    assert rec["legs"]["timing"]["usd"] is None
    assert rec["legs"]["opportunity"]["usd"] is None
    assert "reference_price_after" in (rec["legs"]["opportunity"]["reason"] or "")
    assert rec["total_shortfall_usd"] == pytest.approx(0.0)
    assert rec["legs_complete"] is False


# ── 3. unfilled quantity → opportunity cost (marked estimated) ────────────────
def test_unfilled_opportunity_cost(monkeypatch):
    # BUY Q=10, Pd=100, Pa=100.50, ZERO fills, Pafter=102.00
    #   delay = 10*0.50 = 5.00 ; opportunity = 10*(102-100.50) = 15.00
    #   total = 20.00 — the biggest leg, usually ignored. Marked estimated.
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("u1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.00)
    led.record_arrival("u1", 100.50)
    led.note_unfilled("u1", reason="expired unfilled")
    rec = led.finalize_order("u1", reference_price_after=102.00)

    assert rec["fill_rate"] == pytest.approx(0.0)
    assert rec["legs"]["opportunity"]["usd"] == pytest.approx(15.00)
    assert rec["legs"]["opportunity"]["bps"] == pytest.approx(150.0)
    assert rec["opportunity_estimated"] is True
    assert rec["total_shortfall_usd"] == pytest.approx(20.00)
    assert rec["unfilled_qty"] == pytest.approx(10.0)


# ── 4. pre-trade vs realized estimate-error tracking ─────────────────────────
def test_estimate_error_stats(monkeypatch):
    led, _ = make_ledger(monkeypatch, impact_fn=fake_impact(2.0))
    # order A: realized 9.9502 bps vs pre 2.0 → error +7.9502 (under-estimate)
    led.record_decision("e1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.00, adv=1e6, sigma_daily=0.02)
    led.record_arrival("e1", 100.50)
    led.record_fill("e1", 100.60, fill_qty=10)
    led.finalize_order("e1", reference_price_after=100.60)
    # order B: realized (99.90-100.50)/100.50*1e4 = -59.7015 vs pre 2.0
    #   → error -61.7015 (over-estimate)
    led.record_decision("e2", symbol="BTC", side="buy", qty=10,
                        decision_price=100.00, adv=1e6, sigma_daily=0.02)
    led.record_arrival("e2", 100.50)
    led.record_fill("e2", 99.90, fill_qty=10)
    led.finalize_order("e2", reference_price_after=99.90)

    stats = led.estimate_error_stats()
    assert stats["comparisons"] == 2
    assert stats["mean_error_bps"] == pytest.approx((7.9502 - 61.7015) / 2, abs=1e-3)
    assert stats["under_estimates"] == 1
    assert stats["over_estimates"] == 1
    assert "verdict" in stats


def test_estimate_error_empty():
    led = TCALedger(path=os.path.join(tempfile.mkdtemp(), "t.jsonl"),
                    impact_fn=None)
    stats = led.estimate_error_stats()
    assert stats["comparisons"] == 0
    assert "untested" in stats["note"] or "no orders" in stats["note"]


# ── 5. impact model present vs absent ─────────────────────────────────────────
def test_impact_model_present_via_guarded_import(monkeypatch):
    # Simulate the sibling branch being merged: intel/impact_model importable.
    mod = types.ModuleType("intel.impact_model")
    mod.estimate_impact = fake_impact(3.5)
    monkeypatch.setitem(sys.modules, "intel.impact_model", mod)
    led, _ = make_ledger(monkeypatch)  # default constructor → guarded import
    assert led._impact_fn is not None
    led.record_decision("p1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.0, adv=1e6, sigma_daily=0.02)
    order = led._pending["p1"]
    assert order["pre_trade_impact_bps"] == pytest.approx(3.5)
    assert order["pre_trade_reason"] is None
    close("intel.impact_model")


def test_impact_model_absent_reason_recorded(monkeypatch):
    monkeypatch.setitem(sys.modules, "intel.impact_model", None)
    led, _ = make_ledger(monkeypatch)
    assert led._impact_fn is None
    led.record_decision("p2", symbol="BTC", side="buy", qty=10,
                        decision_price=100.0, adv=1e6, sigma_daily=0.02)
    order = led._pending["p2"]
    assert order["pre_trade_impact_bps"] is None
    assert "unavailable" in (order["pre_trade_reason"] or "")


def test_impact_model_missing_inputs_reason(monkeypatch):
    # Model present but adv/sigma missing → None with reason, never invented.
    mod = types.ModuleType("intel.impact_model")
    mod.estimate_impact = fake_impact(3.5)
    monkeypatch.setitem(sys.modules, "intel.impact_model", mod)
    led, _ = make_ledger(monkeypatch)
    led.record_decision("p3", symbol="BTC", side="buy", qty=10,
                        decision_price=100.0)  # no adv / sigma_daily
    order = led._pending["p3"]
    assert order["pre_trade_impact_bps"] is None
    assert order["pre_trade_reason"] is not None
    close("intel.impact_model")


# ── 6. latency attribution: present vs absent ─────────────────────────────────
def test_latency_attribution_pro_rata(monkeypatch):
    # Fake telemetry.latency with a current-cycle recorder.
    lat = types.ModuleType("telemetry.latency")

    class _Rec:
        durations = {"risk_checks": 2.0, "order_submission": 3.0}

    lat._active = lambda: _Rec()
    monkeypatch.setitem(sys.modules, "telemetry.latency", lat)

    led, _ = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("l1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.00,
                        decision_ts="2026-09-19T20:00:00+00:00")
    led.record_arrival("l1", 100.50, arrival_ts="2026-09-19T20:00:10+00:00")
    led.record_fill("l1", 100.60, fill_qty=10)
    rec = led.finalize_order("l1", reference_price_after=100.60)

    attr = rec["latency_attribution"]
    assert attr is not None
    assert attr["estimated"] is True
    assert attr["segments_usd"]["risk_checks"] == pytest.approx(2.0)
    assert attr["segments_usd"]["order_submission"] == pytest.approx(3.0)
    # pro-rata shares sum back to the delay leg (delay = 10*0.50 = 5.00)
    assert sum(attr["segments_usd"].values()) == pytest.approx(
        rec["legs"]["delay"]["usd"])
    close("telemetry.latency")


def test_latency_attribution_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "telemetry.latency", None)
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("l2", symbol="BTC", side="buy", qty=10,
                        decision_price=100.00)
    led.record_arrival("l2", 100.50)
    led.record_fill("l2", 100.60, fill_qty=10)
    rec = led.finalize_order("l2", reference_price_after=100.60)
    assert rec["latency_attribution"] is None
    assert rec["latency_attribution_reason"] is not None


# ── 7. fault isolation ───────────────────────────────────────────────────────
def test_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("TCA_ENABLED", "0")
    led = TCALedger(path=os.path.join(tempfile.mkdtemp(), "t.jsonl"),
                    impact_fn=None)
    assert led.enabled is False
    led.record_decision("d1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.0)
    led.record_arrival("d1", 100.5)
    led.record_fill("d1", 100.6, fill_qty=10)
    assert led.finalize_order("d1") is None
    assert led.summary_for_status()["orders_measured"] == 0


def test_garbage_inputs_never_raise(monkeypatch):
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("g1", symbol="BTC", side="buy", qty=0)      # bad qty
    led.record_decision("g2", symbol="BTC", side="buy", qty=-3)     # bad qty
    led.record_decision("g3", symbol="BTC", side="buy", qty=float("nan"))
    assert led._pending == {}
    assert led.record_fill("unknown-id", 100.0) is None
    assert led.record_fill("unknown-id", float("nan")) is None
    assert led.finalize_order("unknown-id") is None
    led.note_unfilled("unknown-id", reason="x")
    # finalize a real order with absurd inputs still never raises
    led.record_decision("g4", symbol="BTC", side="buy", qty=10)
    led.record_fill("g4", -5.0, fill_qty=-2, fees_usd=float("inf"))
    rec = led.finalize_order("g4", reference_price_after=float("nan"))
    assert rec is None or isinstance(rec, dict)


# ── 8. JSONL ledger round-trip ────────────────────────────────────────────────
def test_jsonl_round_trip(monkeypatch):
    led, path = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("j1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.0)
    led.record_arrival("j1", 100.5)
    led.record_fill("j1", 100.6, fill_qty=10)
    led.finalize_order("j1", reference_price_after=100.6)

    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["order_id"] == "j1"
    assert row["module"] == "tca"
    assert "legs" in row

    # a fresh instance reads the same ledger back
    led2 = TCALedger(path=path, impact_fn=None)
    summary = led2.summary_for_status()
    assert summary["orders_measured"] == 1
    assert summary["avg_fill_rate"] == pytest.approx(1.0)


# ── 9. summary + period report ────────────────────────────────────────────────
def test_summary_for_status_and_period_report(monkeypatch):
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    for i, sym in enumerate(("BTC", "ETH")):
        oid = f"r{i}"
        led.record_decision(oid, symbol=sym, side="buy", qty=10,
                            decision_price=100.0)
        led.record_arrival(oid, 100.5)
        led.record_fill(oid, 100.6, fill_qty=10)
        led.finalize_order(oid, reference_price_after=100.6)

    s = led.summary_for_status()
    assert s["orders_measured"] == 2
    # per order: delay 5.00 + timing 1.00 = 6.00
    assert s["avg_total_shortfall_usd"] == pytest.approx(6.00)
    assert s["legs_avg_usd"]["delay"] == pytest.approx(5.00)
    assert s["legs_avg_usd"]["timing"] == pytest.approx(1.00)
    assert s["avg_fill_rate"] == pytest.approx(1.0)
    assert s["orders_with_incomplete_legs"] == 2  # impact leg None

    rep = led.period_report(days=30)
    assert rep["orders"] == 2
    assert rep["total_shortfall_usd"] == pytest.approx(12.00)
    assert set(rep["by_symbol"]) == {"BTC", "ETH"}
    assert rep["lines"] and all(isinstance(x, str) for x in rep["lines"])

    rep_btc = led.period_report(days=30, symbol="BTC")
    assert rep_btc["orders"] == 1
    assert rep_btc["total_shortfall_usd"] == pytest.approx(6.00)


def test_partial_fills_accumulate(monkeypatch):
    led, _ = make_ledger(monkeypatch, impact_fn=None)
    led.record_decision("pf1", symbol="BTC", side="buy", qty=10,
                        decision_price=100.0)
    led.record_arrival("pf1", 100.0)
    led.record_fill("pf1", 100.10, fill_qty=4)
    led.record_fill("pf1", 100.20, fill_qty=6)
    rec = led.finalize_order("pf1", reference_price_after=100.20)
    # avg fill = (4*100.10 + 6*100.20)/10 = 100.16
    assert rec["avg_fill_price"] == pytest.approx(100.16)
    assert rec["fill_rate"] == pytest.approx(1.0)
    # timing = 10*(100.16-100.00) = 1.60 ; delay = 0 ; total = 1.60
    assert rec["legs"]["timing"]["usd"] == pytest.approx(1.60)
    assert rec["total_shortfall_usd"] == pytest.approx(1.60)
