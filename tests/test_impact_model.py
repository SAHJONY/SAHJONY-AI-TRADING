"""Tests for intel/impact_model.py — fully offline, no network, no state."""
from __future__ import annotations

import copy
import math

import pytest

from intel.impact_model import (
    K_SQRT,
    batch_estimate,
    estimate_impact,
    what_if_size,
)


# ── formula correctness against hand-computed values ──────────────────────

def test_formula_matches_hand_computation():
    # σ=2%/day, Q=1_000 shares, ADV=1_000_000 → participation 0.001
    # impact = 1.0 * 0.02 * sqrt(0.001) = 0.0006324555… → 6.3246 bps
    r = estimate_impact("TEST", 1_000, 1_000_000, 0.02)
    assert r is not None
    assert r["expected_impact_bps"] == pytest.approx(6.3246, abs=1e-3)
    assert r["participation_rate"] == pytest.approx(0.001)
    assert r["inputs"] == {
        "qty": 1000.0, "adv": 1_000_000.0, "sigma_daily": 0.02,
        "k": K_SQRT, "price": None,
    }
    assert r["data_quality"] == "complete"
    assert r["model"] == "square_root_law"


def test_dollar_cost_conversion():
    # same inputs at $50 → cost = 0.0006324555 * 50 * 1000 ≈ $31.62
    r = estimate_impact("TEST", 1_000, 1_000_000, 0.02, price=50.0)
    assert r["est_cost_usd"] == pytest.approx(31.6228, abs=0.01)
    r2 = estimate_impact("TEST", 1_000, 1_000_000, 0.02)
    assert r2["est_cost_usd"] is None  # price unknown → not invented


def test_tiny_retail_order_impact_is_zero():
    # $10 order ≈ 1 share of a $10 stock, ADV 5M, σ=2% → impact ~ 0.0009 bps
    r = estimate_impact("RET", 1, 5_000_000, 0.02)
    assert r is not None
    assert r["expected_impact_bps"] < 1.0  # sub-1 bps ≈ 0: execution is not the bottleneck


def test_sqrt_scaling_quadrupling_size_doubles_impact():
    base = estimate_impact("TEST", 1_000, 1_000_000, 0.02)["expected_impact_bps"]
    quad = estimate_impact("TEST", 4_000, 1_000_000, 0.02)["expected_impact_bps"]
    assert quad == pytest.approx(2.0 * base, abs=1e-3)
    half_vol = estimate_impact("TEST", 1_000, 4_000_000, 0.02)["expected_impact_bps"]
    assert half_vol == pytest.approx(0.5 * base, abs=1e-3)  # 4x ADV → half the impact
    double_sig = estimate_impact("TEST", 1_000, 1_000_000, 0.04)["expected_impact_bps"]
    assert double_sig == pytest.approx(2.0 * base, abs=1e-3)  # linear in σ


# ── input honesty: unknown = None, never invented ─────────────────────────

@pytest.mark.parametrize("kw", [
    {"qty": None}, {"adv": None}, {"sigma_daily": None},
    {"qty": 0}, {"adv": 0},                      # non-physical
    {"qty": -5}, {"adv": -1_000_000}, {"sigma_daily": -0.01},
    {"qty": float("nan")}, {"adv": float("inf")},
    {"qty": "abc"}, {"adv": "abc"},              # non-numeric
])
def test_missing_or_bad_inputs_return_none(kw):
    base = {"qty": 100, "adv": 1_000_000, "sigma_daily": 0.02}
    base.update(kw)
    assert estimate_impact("TEST", **base) is None


def test_zero_volatility_is_valid_and_zero_impact():
    r = estimate_impact("TEST", 100, 1_000_000, 0.0)
    assert r is not None
    assert r["expected_impact_bps"] == 0.0


def test_bad_k_is_rejected():
    assert estimate_impact("TEST", 100, 1_000_000, 0.02, k=float("nan")) is None
    assert estimate_impact("TEST", 100, 1_000_000, 0.02, k=-1.0) is None
    r = estimate_impact("TEST", 100, 1_000_000, 0.02, k=2.0)
    assert r["inputs"]["k"] == 2.0
    assert r["expected_impact_bps"] == pytest.approx(
        2.0 * estimate_impact("TEST", 100, 1_000_000, 0.02)["expected_impact_bps"])


# ── what-if stress probe ──────────────────────────────────────────────────

def test_what_if_monotonic_and_hypothetical():
    small = what_if_size("TEST", 1_000, 1_000_000, 0.02)
    big = what_if_size("TEST", 16_000, 1_000_000, 0.02)
    assert small is not None and big is not None
    assert big["expected_impact_bps"] > small["expected_impact_bps"]
    assert big["expected_impact_bps"] == pytest.approx(4.0 * small["expected_impact_bps"], abs=1e-3)
    assert big["hypothetical"] is True
    assert "never feed sizing" in big["note"]


def test_what_if_matches_estimate_at_same_size():
    a = what_if_size("TEST", 1_000, 1_000_000, 0.02)
    b = estimate_impact("TEST", 1_000, 1_000_000, 0.02)
    assert a["expected_impact_bps"] == b["expected_impact_bps"]


def test_what_if_bad_inputs_return_none():
    assert what_if_size("TEST", None, 1_000_000, 0.02) is None
    assert what_if_size("TEST", -100, 1_000_000, 0.02) is None
    assert what_if_size("TEST", 100, 0, 0.02) is None


# ── purity: no network, no mutation, deterministic ────────────────────────

def test_functions_are_pure_no_mutation():
    entry = {"symbol": "A", "qty": 100, "adv": 1_000_000, "sigma_daily": 0.02}
    snapshot = copy.deepcopy(entry)
    estimate_impact("A", 100, 1_000_000, 0.02)
    what_if_size("A", 500, 1_000_000, 0.02)
    batch_estimate([entry])
    assert entry == snapshot  # caller data untouched
    r1 = estimate_impact("A", 100, 1_000_000, 0.02)
    r2 = estimate_impact("A", 100, 1_000_000, 0.02)
    assert r1 == r2  # deterministic


def test_no_network_or_stateful_imports():
    import intel.impact_model as m
    import inspect
    src = inspect.getsource(m)
    for forbidden in ("socket", "requests", "urllib", "http.client",
                      "open(", "os.environ", "global "):
        assert forbidden not in src


def test_batch_estimate_per_symbol_none_on_missing():
    out = batch_estimate([
        {"symbol": "GOOD", "qty": 100, "adv": 1_000_000, "sigma_daily": 0.02},
        {"symbol": "NOADV", "qty": 100, "adv": None, "sigma_daily": 0.02},
        {"symbol": "BAD", "qty": -5, "adv": 1_000_000, "sigma_daily": 0.02},
    ])
    assert out["GOOD"]["expected_impact_bps"] == pytest.approx(2.0, abs=1e-3)
    assert out["NOADV"] is None
    assert out["BAD"] is None


def test_provenance_echoed():
    r = estimate_impact("TEST", 100, 1_000_000, 0.02, provenance="estimated")
    assert r["provenance"] == "estimated"
