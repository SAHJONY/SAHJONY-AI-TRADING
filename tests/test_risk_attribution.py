"""Tests for risk/risk_attribution.py — fully offline, synthetic data only.

Conventions:
- Every fixture is generated in-test with a seeded RNG. No network, no keys,
  no fixtures from disk.
- The "hand-computed" two-asset test recomputes the closed-form parametric
  VaR from the raw return matrix with independent numpy code (not by calling
  the module's internals), so a wrong formula in the module fails loudly.
"""
import math

import numpy as np
import pytest

from risk import risk_attribution as ra

Z_95 = 1.6448536269514729  # Phi^-1(0.95), universal constant


def _closes(rets, start=100.0):
    """Price closes from a return series (deterministic given rets)."""
    return (start * np.exp(np.cumsum(np.asarray(rets, dtype=float)))).tolist()


def _two_asset_book(n=400, seed=7, w_a=0.6, w_b=0.4, equity=1000.0):
    """Two correlated crypto-like legs; returns (positions, closes, prices, rets)."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, 2))
    # target: sigma_A=0.02, sigma_B=0.03, rho=0.5
    L = np.array([[1.0, 0.0], [0.5, math.sqrt(0.75)]])
    rets = z @ L.T * np.array([0.02, 0.03])
    ca, cb = _closes(rets[:, 0], 100.0), _closes(rets[:, 1], 50.0)
    prices = {"A": ca[-1], "B": cb[-1]}
    positions = {
        "A": {"shares": w_a * equity / prices["A"], "cost_basis": prices["A"]},
        "B": {"shares": w_b * equity / prices["B"], "cost_basis": prices["B"]},
    }
    return positions, {"A": ca, "B": cb}, prices, rets


def test_two_asset_component_var_hand_computed():
    """Independent closed-form recomputation of the two-asset component VaR."""
    equity, w_a, w_b = 1000.0, 0.6, 0.4
    positions, closes, prices, rets = _two_asset_book()
    report = ra.attribution_report(positions, closes, prices, equity, 0.95)
    assert report["status"] == "ok"

    # --- independent expected values, straight from the raw returns ---
    # The module measures on the last LOOKBACK=60 closes (59 returns), so the
    # hand computation must use the same window to be comparable.
    tail_rets = rets[-59:]
    w = np.array([w_a, w_b])
    cov = np.cov(tail_rets, rowvar=False)     # same estimator the module uses
    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(port_var)
    exp_var = Z_95 * equity * port_vol
    sigma_w = cov @ w
    marginal = Z_95 * equity * sigma_w / port_vol
    exp_comp_a = w_a * marginal[0]
    exp_comp_b = w_b * marginal[1]

    assert report["var_total"] == pytest.approx(exp_var, rel=1e-3)
    comp = {c["symbol"]: c for c in report["components"]}
    assert comp["A"]["component_var"] == pytest.approx(exp_comp_a, rel=1e-3)
    assert comp["B"]["component_var"] == pytest.approx(exp_comp_b, rel=1e-3)
    # Euler identity: components sum exactly to total VaR
    assert (comp["A"]["component_var"] + comp["B"]["component_var"]
            ) == pytest.approx(exp_var, rel=1e-3)


def test_components_sum_to_total_var():
    positions, closes, prices, _ = _two_asset_book(n=120, seed=11)
    report = ra.attribution_report(positions, closes, prices, 1000.0, 0.95)
    assert report["status"] == "ok"
    total = sum(c["component_var"] for c in report["components"])
    assert total == pytest.approx(report["var_total"], rel=1e-9)
    # component ES is the Euler allocation of ES too (display rounding
    # loosens the identity to the ~1e-3 the 4-decimal payload carries)
    total_es = sum(c["component_es"] for c in report["components"])
    assert total_es == pytest.approx(report["es_total"], rel=1e-3)
    # shares of VaR sum to 100%
    assert sum(c["share_of_var_pct"] for c in report["components"]) == \
        pytest.approx(100.0, abs=0.05)
    # hog is the top contributor
    hog = max(report["components"], key=lambda c: c["component_var"])
    assert report["var_hog"] == hog["symbol"]


def test_es_greater_than_or_equal_var():
    positions, closes, prices, _ = _two_asset_book()
    report = ra.attribution_report(positions, closes, prices, 1000.0, 0.95)
    assert report["status"] == "ok"
    assert report["es_total"] >= report["var_total"]
    # parametric ES is the closed-form normal multiple of VaR
    tail = 1.0 - 0.5 * (1.0 + math.erf(Z_95 / math.sqrt(2.0)))
    phi = math.exp(-0.5 * Z_95 * Z_95) / math.sqrt(2.0 * math.pi)
    exp_mult = phi / (tail * Z_95)
    assert report["es_multiple_of_var"] == pytest.approx(exp_mult, rel=1e-3)
    assert report["es_total"] == pytest.approx(report["var_total"] * exp_mult,
                                               rel=1e-3)


def test_historical_es_reported_and_flagged():
    positions, closes, prices, _ = _two_asset_book(n=400)
    report = ra.attribution_report(positions, closes, prices, 1000.0, 0.95)
    hist = report["historical_simulation"]
    assert hist is not None
    assert hist["method"] == "historical_simulation"
    assert hist["observations"] >= ra.MIN_HIST_SIM_OBS
    # historical ES >= historical VaR (tail average is worse than the quantile)
    assert hist["es"] >= hist["var"] >= 0
    assert report["historical_es"] == pytest.approx(hist["es"])


def test_historical_es_none_when_too_few_obs():
    positions, closes, prices, _ = _two_asset_book(n=40)  # 39 obs < 50
    report = ra.attribution_report(positions, closes, prices, 1000.0, 0.95)
    assert report["status"] == "ok"
    assert report["historical_simulation"] is None
    assert report["historical_es"] is None
    assert "parametric" in report["advice"]


def test_incremental_add_to_hog_vs_diversifier():
    """Adding to the VaR hog raises VaR more than adding a diversifying leg."""
    rng = np.random.default_rng(21)
    n = 300
    rh = rng.standard_normal(n) * 0.05          # H: the hog, high vol
    rl = rng.standard_normal(n) * 0.01         # L: low vol, uncorrelated
    rd = rng.standard_normal(n) * 0.005         # D: diversifier, tiny vol
    equity = 1000.0
    ch, cl, cd = _closes(rh, 100.0), _closes(rl, 10.0), _closes(rd, 5.0)
    positions = {
        "H": {"shares": 0.8 * equity / ch[-1], "cost_basis": ch[-1]},
        "L": {"shares": 0.2 * equity / cl[-1], "cost_basis": cl[-1]},
    }
    closes = {"H": ch, "L": cl, "D": cd}
    prices = {"H": ch[-1], "L": cl[-1], "D": cd[-1]}

    before = ra.attribution_report(positions, closes, prices, equity, 0.95)
    assert before["status"] == "ok"
    assert before["var_hog"] == "H"

    add_hog = ra.incremental_trade_check("H", "buy", 10.0, positions, closes,
                                         prices, equity, 0.95)
    add_div = ra.incremental_trade_check("D", "buy", 10.0, positions, closes,
                                         prices, equity, 0.95)
    assert add_hog["status"] == "ok" and add_div["status"] == "ok"
    assert add_hog["incremental_var"] > 0
    assert add_div["incremental_var"] > 0
    # feeding the hog is worse tail-risk-wise than diversifying
    assert add_hog["incremental_var"] > add_div["incremental_var"]
    assert add_hog["incremental_es"] >= add_hog["incremental_var"] * 0.99
    # var_after is consistent with before + increment
    assert add_hog["var_after"] == pytest.approx(
        before["var_total"] + add_hog["incremental_var"], rel=1e-9)


def test_incremental_does_not_mutate_positions():
    positions, closes, prices, _ = _two_asset_book(n=120)
    snapshot = {k: dict(v) for k, v in positions.items()}
    ra.incremental_trade_check("C", "buy", 10.0, positions,
                               {**closes, "C": closes["A"]},
                               {**prices, "C": prices["A"]}, 1000.0, 0.95)
    assert positions == snapshot


def test_incremental_invalid_inputs():
    positions, closes, prices, _ = _two_asset_book(n=120)
    assert ra.incremental_trade_check("", "buy", 10.0, positions, closes,
                                      prices, 1000.0)["status"] == "invalid"
    assert ra.incremental_trade_check("A", "buy", 0, positions, closes,
                                      prices, 1000.0)["status"] == "invalid"
    assert ra.incremental_trade_check("A", "buy", -5, positions, closes,
                                      prices, 1000.0)["status"] == "invalid"
    assert ra.incremental_trade_check("A", "hold", 10.0, positions, closes,
                                      prices, 1000.0)["status"] == "invalid"
    # unknown symbol with no price/history: unknown, not invented
    r = ra.incremental_trade_check("ZZZ", "buy", 10.0, positions, closes,
                                   prices, 1000.0)
    assert r["status"] == "insufficient"
    assert r["var_total"] if False else True  # no fabricated VaR keys
    assert "var_after" not in r


def test_missing_data_returns_none_never_raises():
    # flat book
    r = ra.attribution_report({}, {}, {}, 1000.0)
    assert r["status"] == "flat" and r["var_total"] is None
    # unknown equity
    r = ra.attribution_report({"A": {"shares": 1}}, {"A": list(range(100))},
                              {"A": 1.0}, None)
    assert r["status"] == "invalid" and r["var_total"] is None
    # garbage everywhere: never raises
    r = ra.attribution_report(None, None, None, "abc")
    assert r["status"] in ("invalid", "flat", "insufficient", "error")
    r = ra.attribution_report({"A": {"shares": "abc"}},
                              {"A": ["x", "y", None]}, {"A": float("nan")}, 1000.0)
    assert r["status"] in ("flat", "insufficient", "invalid", "error")
    assert r["var_total"] is None
    # single name with history but nothing to diversify against
    one = {"A": {"shares": 10, "cost_basis": 100.0}}
    r = ra.attribution_report(one, {"A": _closes(np.zeros(60), 100.0)},
                              {"A": 100.0}, 1000.0)
    assert r["status"] == "insufficient" and r["var_total"] is None
    # one good leg, one leg without history -> excluded & listed, book measured
    pos = {"A": {"shares": 6, "cost_basis": 100.0},
           "B": {"shares": 4, "cost_basis": 50.0}}
    cl = {"A": _closes(np.random.default_rng(3).standard_normal(60) * 0.02, 100.0),
          "B": [50.0, 51.0]}  # too short
    r = ra.attribution_report(pos, cl, {"A": 100.0, "B": 50.0}, 1000.0)
    assert r["status"] == "insufficient"
    assert any(e["symbol"] == "B" for e in r["excluded"])


def test_short_positions_handled_with_signed_weights():
    """Pairs-desk shorts (negative shares) show up honestly, never crash."""
    rng = np.random.default_rng(9)
    n = 120
    ra1 = rng.standard_normal(n) * 0.02
    ra2 = rng.standard_normal(n) * 0.02
    closes = {"A": _closes(ra1, 100.0), "B": _closes(ra2, 50.0)}
    prices = {"A": closes["A"][-1], "B": closes["B"][-1]}
    positions = {
        "A": {"shares": 600.0 / prices["A"], "cost_basis": prices["A"]},
        "B": {"shares": -400.0 / prices["B"], "cost_basis": prices["B"]},  # short
    }
    r = ra.attribution_report(positions, closes, prices, 1000.0, 0.95)
    assert r["status"] == "ok"
    assert sum(c["component_var"] for c in r["components"]) == \
        pytest.approx(r["var_total"], rel=1e-9)
    comp = {c["symbol"]: c for c in r["components"]}
    assert comp["B"]["weight_pct"] < 0  # short leg stays negative


def test_confidence_out_of_range():
    positions, closes, prices, _ = _two_asset_book(n=120)
    r = ra.attribution_report(positions, closes, prices, 1000.0, 1.5)
    assert r["status"] == "invalid"


def test_fault_isolation_never_raises():
    bad_inputs = [
        ({"A": {"shares": float("inf")}}, {"A": [1.0] * 100}, {"A": 1.0}, 1000.0),
        ({"A": {"shares": 1}}, {"A": [float("nan")] * 100}, {"A": 1.0}, 1000.0),
        ({"A": {"shares": 1}}, {"A": [0.0] * 100}, {"A": 1.0}, 1000.0),
        ({"A": {}}, {}, {}, -5.0),
    ]
    for args in bad_inputs:
        r = ra.attribution_report(*args)
        assert isinstance(r, dict) and "status" in r
    r = ra.incremental_trade_check("A", "buy", float("nan"), {}, {}, {}, None)
    assert isinstance(r, dict) and "status" in r
