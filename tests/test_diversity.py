"""Tests for intel/diversity.py — fully offline, no network, no credentials.

Verifies:
- perfectly correlated persona votes -> covariance share ~1, effective bets ~1
- independent persona votes -> low covariance share, effective bets ~N
- exponential decay of the vote history (recent cycles weigh more)
- empty / single-vote / degenerate edge cases
- fault isolation: garbage input never raises, degrades to recorded status
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from intel import diversity as div


class V:
    """Minimal stand-in for AgentVerdict."""
    def __init__(self, name, score):
        self.name = name
        self.score = score


NAMES = [f"agent-{i:02d}" for i in range(12)]


def _feed_cycles(state, symbol, n_cycles, score_fn):
    """Feed n_cycles of synthetic votes into the decayed history."""
    for t in range(n_cycles):
        verdicts = [V(n, float(score_fn(n, t))) for n in NAMES]
        div.record_votes(state, symbol, verdicts)


# ── covariance-share decomposition ───────────────────────────────────────────
def test_perfectly_correlated_votes_covariance_share_near_one():
    state: dict = {}
    # All 12 personas emit the SAME score every cycle -> one crowded bet.
    _feed_cycles(state, "BTC", 12, lambda n, t: math.sin(t * 0.7))
    corr, meta = div.vote_correlation_matrix(state, "BTC")
    assert corr is not None and meta["status"] == "ok"
    dec = div.covariance_share(corr)
    assert dec["n_agents"] == 12
    assert dec["covariance_share"] is not None
    # theoretical max for M=12 perfectly correlated votes is (M-1)/M
    assert dec["covariance_share"] == pytest.approx(11 / 12, abs=0.01)
    assert dec["covariance_share"] >= 0.9
    assert abs(dec["covariance_share"] + dec["variance_share"] - 1.0) < 1e-6


def test_independent_votes_low_covariance_share():
    rng = np.random.default_rng(42)
    state: dict = {}
    # Independent votes per persona per cycle.
    scores = rng.uniform(-1, 1, size=(20, 12))
    for t in range(20):
        verdicts = [V(n, float(scores[t, i])) for i, n in enumerate(NAMES)]
        div.record_votes(state, "ETH", verdicts)
    corr, meta = div.vote_correlation_matrix(state, "ETH")
    assert corr is not None and meta["status"] == "ok"
    dec = div.covariance_share(corr)
    assert dec["covariance_share"] is not None
    assert dec["covariance_share"] < 0.25


def test_mixed_bloc_two_bets():
    # Two independent 6-persona blocs -> council is ~2 bets, not 12.
    rng = np.random.default_rng(7)
    state: dict = {}
    bloc_a = rng.uniform(-1, 1, size=15)
    bloc_b = rng.uniform(-1, 1, size=15)
    for t in range(15):
        verdicts = ([V(NAMES[i], float(bloc_a[t])) for i in range(6)] +
                    [V(NAMES[i], float(bloc_b[t])) for i in range(6, 12)])
        div.record_votes(state, "SOL", verdicts)
    corr, _ = div.vote_correlation_matrix(state, "SOL")
    dec = div.covariance_share(corr)
    assert 0.25 < dec["covariance_share"] < 0.95


# ── decay behaviour ──────────────────────────────────────────────────────────
def test_decay_weights_recent_cycles_more():
    state: dict = {}
    _feed_cycles(state, "BTC", 10, lambda n, t: 0.0)
    hist = state["diversity"]["votes"]["BTC"]
    ws = [h["w"] for h in hist]
    # newest entry has weight 1.0; older ones are decayed
    assert ws[-1] == pytest.approx(1.0)
    assert ws[0] < ws[-1]
    assert all(b >= a for a, b in zip(ws, ws[1:]))  # monotone increasing


def test_decay_switches_correlation_after_regime_change():
    # Long history of correlated votes, then a burst of independent votes
    # with decay=1.0-less... we verify record respects the decay parameter
    # by checking weights shrink when decay < 1.
    state: dict = {}
    _feed_cycles(state, "BTC", 5, lambda n, t: 0.5)
    div.record_votes(state, "BTC", [V(n, 0.5) for n in NAMES], decay=0.5)
    hist = state["diversity"]["votes"]["BTC"]
    assert hist[-1]["w"] == pytest.approx(1.0)
    assert hist[-2]["w"] == pytest.approx(0.5)


def test_prune_below_min_weight():
    state: dict = {}
    _feed_cycles(state, "BTC", 60, lambda n, t: 0.1)
    hist = state["diversity"]["votes"]["BTC"]
    assert len(hist) <= div._MAX_SYMBOLS
    assert all(h["w"] >= div._MIN_W for h in hist)


# ── edge cases ───────────────────────────────────────────────────────────────
def test_empty_state_insufficient():
    corr, meta = div.vote_correlation_matrix({}, "BTC")
    assert corr is None
    assert meta["status"] == "insufficient"
    assert meta["obs"] == 0


def test_too_few_cycles_insufficient():
    state: dict = {}
    _feed_cycles(state, "BTC", 2, lambda n, t: 0.3)
    corr, meta = div.vote_correlation_matrix(state, "BTC")
    assert corr is None
    assert meta["status"] == "insufficient"


def test_covariance_share_degenerate():
    assert div.covariance_share(None)["covariance_share"] is None
    assert div.covariance_share(np.array([]))["covariance_share"] is None
    assert div.covariance_share(np.ones((1, 1)))["covariance_share"] is None
    # zero-variance votes (all constant) -> undefined share, not a crash
    dec = div.covariance_share(np.ones((12, 12)))
    assert dec["covariance_share"] is None or 0.0 <= dec["covariance_share"] <= 1.0


def test_effective_bets_perfect_correlation():
    rho = np.ones((4, 4))
    out = div.effective_bets({f"s{i}": 1.0 for i in range(4)}, rho)
    assert out["status"] == "ok"
    assert out["effective_bets"] == pytest.approx(1.0)
    assert out["nominal"] == 4


def test_effective_bets_independent():
    rho = np.eye(5)
    out = div.effective_bets({f"s{i}": 1.0 for i in range(5)}, rho)
    assert out["status"] == "ok"
    assert out["effective_bets"] == pytest.approx(5.0)


def test_effective_bets_single_position_is_one_bet():
    # A single position is definitionally exactly one bet — the function
    # handles n=1 correctly; the book-level report marks <2 as insufficient.
    out = div.effective_bets({"BTC": 1.0}, np.ones((1, 1)))
    assert out["status"] == "ok"
    assert out["effective_bets"] == pytest.approx(1.0)
    assert out["nominal"] == 1


def test_effective_bets_empty():
    out = div.effective_bets({}, None)
    assert out["status"] == "insufficient"
    assert out["nominal"] == 0


# ── fault isolation: nothing raises ──────────────────────────────────────────
@pytest.mark.parametrize("bad", [None, {}, [], "garbage", {"a": object()}])
def test_fault_isolation_report_never_raises(bad):
    rep = div.diversity_report(bad, bad, bad, bad, bad)
    assert isinstance(rep, dict)
    assert "status" in rep


def test_fault_isolation_garbage_votes():
    state: dict = {}
    rep = div.diversity_report(
        state,
        [{"symbol": "BTC", "verdict": object()}, {"symbol": "ETH"}],
        positions={"BTC": {"shares": "not-a-number"}},
        closes_by_symbol={"BTC": [float("nan")] * 50},
        prices={"BTC": float("inf")},
    )
    assert isinstance(rep, dict)
    assert rep["status"] in ("ok", "error")


def test_risk_officer_read_is_pure():
    state: dict = {}
    ro = div.risk_officer_read(state)
    assert ro["effective_bets"] is None
    ro2 = div.risk_officer_read(None)
    assert ro2["effective_bets"] is None
    # a stored report is readable
    state["_diversity_last"] = {"cycle": 7,
                                "book": {"effective_bets": 2.5,
                                         "nominal": 6,
                                         "concentration_index": 0.583}}
    ro3 = div.risk_officer_read(state)
    assert ro3["effective_bets"] == 2.5 and ro3["cycle"] == 7


# ── end-to-end synthetic report: crowded council gets flagged ─────────────────
def test_crowded_council_flagged_in_plain_language():
    state: dict = {}
    verdicts = [V(n, 0.8) for n in NAMES]  # everyone bullish together
    _feed_cycles(state, "BTC", 12, lambda n, t: 0.8 + 0.01 * math.sin(t))
    rep = div.diversity_report(
        state,
        [{"symbol": "BTC", "verdict": type("Vd", (), {"verdicts": verdicts})()}],
        positions={},
    )
    sym = rep["symbols"]["BTC"]
    assert sym["status"] == "ok"
    assert sym["covariance_share"] is not None
    assert sym["covariance_share"] >= 0.9
    assert sym["crowded"] is True
    assert any("crowded" in f for f in rep["flags"])


def test_diversified_council_no_flag():
    rng = np.random.default_rng(123)
    state: dict = {}
    scores = rng.uniform(-1, 1, size=(15, 12))
    verdicts = [V(n, float(scores[-1, i])) for i, n in enumerate(NAMES)]
    for t in range(15):
        div.record_votes(state, "BTC",
                         [V(n, float(scores[t, i])) for i, n in enumerate(NAMES)])
    rep = div.diversity_report(
        state,
        [{"symbol": "BTC", "verdict": type("Vd", (), {"verdicts": verdicts})()}],
        positions={},
    )
    sym = rep["symbols"]["BTC"]
    assert sym["covariance_share"] is not None
    assert sym["covariance_share"] < 0.5
    assert sym["crowded"] is False


def test_disabled_flag():
    rep = div.diversity_report({}, [], enabled=False)
    assert rep["status"] == "disabled"


def test_book_effective_bets_correlated_assets():
    # Two assets whose returns move in lockstep -> ENB ~ 1
    rng = np.random.default_rng(9)
    base = np.cumsum(rng.normal(0, 0.01, 60)) + 5
    closes = {"A": (100 * np.exp(base)).tolist(),
              "B": (50 * np.exp(base * 1.0)).tolist()}
    positions = {"A": {"shares": 1.0}, "B": {"shares": 2.0}}
    rep = div.diversity_report({}, [], positions=positions,
                               closes_by_symbol=closes,
                               prices={"A": closes["A"][-1], "B": closes["B"][-1]})
    book = rep["book"]
    assert book["status"] == "ok"
    assert book["nominal"] == 2
    assert book["effective_bets"] is not None
    assert book["effective_bets"] < 1.5  # nearly one bet
    assert any("independent bets" in f for f in rep["flags"])
