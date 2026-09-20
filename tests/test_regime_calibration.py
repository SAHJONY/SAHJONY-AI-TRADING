"""Tests for intel/regime_calibration.py — regime-aware council calibration.

All tests are deterministic, offline (no network), secret-free, and use
synthetic fixtures only. The trading loop is never touched.
"""
from __future__ import annotations

import math
import os
import random
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from intel.council_calibration import CouncilCalibration  # noqa: E402
from intel.regime_calibration import RegimeCalibration, current_regime  # noqa: E402


def _closes(n, start=100.0, vol=0.002, drift=0.0, seed=7):
    """Synthetic price series. Low vol -> calm, high vol -> stressed."""
    rng = random.Random(seed)
    px, out = start, [start]
    for _ in range(n - 1):
        px *= math.exp(drift + rng.gauss(0.0, vol))
        out.append(px)
    return out


def _snap(closes, price=None, regime_tag=None):
    closes = list(closes)
    s = SimpleNamespace(closes=closes, price=price if price is not None else (closes[-1] if closes else 0.0))
    if regime_tag is not None:
        s._regime_tag = regime_tag
    return s


def _research(sym, closes, agents_scores, price=None, regime_tag=None):
    verdicts = [SimpleNamespace(name=n, score=s, confidence=0.8)
                for n, s in agents_scores.items()]
    verdict = SimpleNamespace(verdicts=verdicts)
    return {"symbol": sym, "snap": _snap(closes, price, regime_tag), "verdict": verdict}


def _pin_regime(monkeypatch, label=None):
    """Deterministically control current_regime in tests.

    The real regime_model's hard state depends on the last bar, so synthetic
    series cannot reliably force a label; pin it instead and tag snaps.
    """
    import intel.regime_calibration as rc
    if label is None:
        monkeypatch.setattr(rc, "current_regime",
                            lambda snap: getattr(snap, "_regime_tag", "calm"))
    else:
        monkeypatch.setattr(rc, "current_regime", lambda snap: label)


class TestCurrentRegime:
    def test_returns_valid_label_for_real_series(self):
        label = current_regime(_snap(_closes(120, vol=0.01)))
        assert label in ("calm", "stressed")

    def test_deterministic_for_same_series(self):
        c = _closes(120, vol=0.01)
        assert current_regime(_snap(c)) == current_regime(_snap(c))

    def test_unknown_on_malformed_input(self):
        assert current_regime(None) is None
        assert current_regime(SimpleNamespace()) is None
        assert current_regime(_snap([])) == "calm"  # <10 returns -> state 0


class TestNeutralUntilMinObs:
    def test_neutral_until_min_obs_per_cell(self):
        cal = RegimeCalibration()
        state = {"regime_cal": {"acc": {
            "calm": {"A": {"n": 19.0, "h": 19.0}},
            "stressed": {"A": {"n": 100.0, "h": 100.0}},
        }}}
        w_calm = cal.weights_for_regime(state, "calm")
        w_stressed = cal.weights_for_regime(state, "stressed")
        assert w_calm["A"] == 1.0            # 19 < 20 -> neutral
        assert w_stressed["A"] == 1.5        # 100 >= 20 -> full weight
        # the two cells are independent
        assert w_calm != w_stressed

    def test_missing_cell_is_neutral(self):
        cal = RegimeCalibration()
        state = {"regime_cal": {"acc": {"calm": {}}}}
        assert cal.weights_for_regime(state, "stressed") == {}


class TestBounded:
    def test_weights_bounded(self):
        cal = RegimeCalibration()
        state = {"regime_cal": {"acc": {"calm": {
            "perfect": {"n": 100.0, "h": 100.0},
            "terrible": {"n": 100.0, "h": 0.0},
            "coinflip": {"n": 100.0, "h": 50.0},
        }}}}
        w = cal.weights_for_regime(state, "calm")
        assert w["perfect"] == 1.5
        assert w["terrible"] == 0.5
        assert w["coinflip"] == 1.0
        for v in w.values():
            assert 0.5 <= v <= 1.5


class TestDecay:
    def test_decay_applies_per_cell(self, monkeypatch):
        _pin_regime(monkeypatch, "calm")
        cal = RegimeCalibration()
        state = {}
        # cycle 1: record a long call in a calm series
        closes = _closes(120, vol=0.001)
        r1 = _research("SYM", closes, {"Agent": 0.8})
        cal.grade_and_record(state, [r1])
        # nothing graded yet (first cycle only records) -> no cells at all
        assert state["regime_cal"]["acc"] == {}
        # cycle 2: price moved up -> correct grade
        up = closes[-1] * 1.02
        r2 = _research("SYM", closes, {"Agent": 0.8}, price=up)
        cal.grade_and_record(state, [r2])
        cell = state["regime_cal"]["acc"]["calm"]["Agent"]
        assert cell["n"] == pytest.approx(1.0)
        assert cell["h"] == pytest.approx(1.0)
        # cycle 3: price moved down -> wrong grade, decayed memory
        down = closes[-1] * 0.98
        r3 = _research("SYM", closes, {"Agent": 0.8}, price=down)
        cal.grade_and_record(state, [r3])
        cell = state["regime_cal"]["acc"]["calm"]["Agent"]
        assert cell["n"] == pytest.approx(0.97 + 1.0)
        assert cell["h"] == pytest.approx(0.97 + 0.0)  # recent miss decays the hit

    def test_deadband_abstention_not_graded(self, monkeypatch):
        _pin_regime(monkeypatch, "calm")
        cal = RegimeCalibration()
        state = {}
        closes = _closes(120, vol=0.001)
        cal.grade_and_record(state, [_research("SYM", closes, {"Agent": 0.01})])  # |score| < deadband
        cal.grade_and_record(state, [_research("SYM", closes, {"Agent": 0.01},
                                              price=closes[-1] * 1.05)])
        assert state["regime_cal"]["acc"] == {}  # abstention -> no call, no grade


class TestFallback:
    def test_unknown_regime_falls_back_to_global(self):
        cal = RegimeCalibration()
        state = {"council_cal": {"acc": {"A": {"n": 100.0, "h": 100.0}}},
                 "regime_cal": {"acc": {"calm": {"A": {"n": 100.0, "h": 0.0}}}}}
        expected = CouncilCalibration().weights(state)
        assert expected == {"A": 1.5}
        assert cal.weights_for_regime(state, None) == expected
        assert cal.weights_for_regime(state, "bogus") == expected
        assert cal.weights_for_regime(state, 123) == expected

    def test_weights_delegates_to_global(self):
        cal = RegimeCalibration()
        state = {"council_cal": {"acc": {"A": {"n": 100.0, "h": 0.0}}}}
        assert cal.weights(state) == {"A": 0.5}
        assert cal.accuracy(state) == {"A": 0.0}

    def test_global_grading_unchanged(self):
        """The wrapper must not alter the global memory the fallback reads."""
        base, wrap = CouncilCalibration(), RegimeCalibration()
        s1, s2 = {}, {}
        closes = _closes(120, vol=0.001)
        r1 = _research("SYM", closes, {"A": 0.9})
        r2 = _research("SYM", closes, {"A": 0.9}, price=closes[-1] * 1.03)
        base.grade_and_record(s1, [r1]); base.grade_and_record(s1, [r2])
        wrap.grade_and_record(s2, [r1]); wrap.grade_and_record(s2, [r2])
        assert s1["council_cal"] == s2["council_cal"]
        assert wrap.weights(s2) == base.weights(s1)


class TestDivergentWeights:
    def test_good_in_calm_bad_in_stress_diverges(self, monkeypatch):
        _pin_regime(monkeypatch)  # regime comes from each snap's _regime_tag
        cal = RegimeCalibration()
        state = {}
        calm = _closes(120, vol=0.001, seed=11)
        stressed = _closes(120, vol=0.05, seed=12)
        # 40 calm cycles, agent always right (long into an up move).
        # One symbol per iteration so the re-recorded entry is never
        # spuriously re-graded by the next iteration's price.
        for i in range(40):
            c = _closes(120, vol=0.001, seed=100 + i)
            sym = f"C{i}"
            cal.grade_and_record(state, [_research(sym, c, {"Trend": 0.9},
                                                  regime_tag="calm")])
            cal.grade_and_record(state, [_research(sym, c, {"Trend": 0.9},
                                                  price=c[-1] * 1.01, regime_tag="calm")])
        # 40 stressed cycles, agent always wrong (long into a down move)
        for i in range(40):
            c = _closes(120, vol=0.05, seed=200 + i)
            sym = f"S{i}"
            cal.grade_and_record(state, [_research(sym, c, {"Trend": 0.9},
                                                  regime_tag="stressed")])
            cal.grade_and_record(state, [_research(sym, c, {"Trend": 0.9},
                                                  price=c[-1] * 0.99,
                                                  regime_tag="stressed")])
        w_calm = cal.weights_for_regime(state, "calm")
        w_stressed = cal.weights_for_regime(state, "stressed")
        assert w_calm["Trend"] > 1.0
        assert w_stressed["Trend"] < 1.0
        assert w_calm["Trend"] - w_stressed["Trend"] > 0.5  # clearly divergent
        assert all(0.5 <= v <= 1.5 for v in list(w_calm.values()) + list(w_stressed.values()))

    def test_mean_reversion_agent_opposite_pattern(self):
        cal = RegimeCalibration()
        state = {"regime_cal": {"acc": {
            "calm": {"MR": {"n": 30.0, "h": 6.0}},      # 20% in calm
            "stressed": {"MR": {"n": 30.0, "h": 27.0}},  # 90% in stress
        }}}
        w_calm = cal.weights_for_regime(state, "calm")
        w_stressed = cal.weights_for_regime(state, "stressed")
        assert w_calm["MR"] < 1.0 < w_stressed["MR"]


class TestNeverRaises:
    @pytest.mark.parametrize("state,research", [
        ({}, []),
        ({}, None),
        (None, []),
        ({}, [{"symbol": None}]),
        ({}, [{"symbol": "X", "snap": None, "verdict": None}]),
        ({"regime_cal": None}, [{"symbol": "X"}]),
        ({"regime_cal": {"acc": {"calm": {"A": float("nan")}}}}, []),
    ])
    def test_grade_and_record_never_raises(self, state, research):
        cal = RegimeCalibration()
        assert isinstance(cal.grade_and_record(state, research), dict)

    @pytest.mark.parametrize("state,regime", [
        (None, "calm"), ({}, None), ({"regime_cal": "junk"}, "calm"),
        ({"regime_cal": {"acc": {"calm": "junk"}}}, "calm"),
    ])
    def test_weights_for_regime_never_raises(self, state, regime):
        cal = RegimeCalibration()
        assert isinstance(cal.weights_for_regime(state, regime), dict)


class TestMemoryBounded:
    def test_pred_store_capped(self):
        cal = RegimeCalibration()
        state = {}
        closes = _closes(60, vol=0.001)
        research = [_research(f"S{i}", closes, {"A": 0.9}) for i in range(300)]
        cal.grade_and_record(state, research)
        assert len(state["regime_cal"]["pred"]) <= 128


class TestResearchDeskHook:
    def _desk(self, cal_weights, by_regime):
        from workforce.workforce import ResearchDesk
        desk = ResearchDesk(client=None, council=None)
        desk.cal_weights = cal_weights
        desk.cal_weights_by_regime = by_regime
        return desk

    def test_regime_map_selected_when_known(self, monkeypatch):
        _pin_regime(monkeypatch)
        desk = self._desk({"A": 1.5}, {"calm": {"A": 0.6}, "stressed": {"A": 1.4}})
        assert desk._cal_weights_for(_snap(_closes(120, vol=0.001),
                                           regime_tag="calm")) == {"A": 0.6}
        assert desk._cal_weights_for(_snap(_closes(120, vol=0.05),
                                           regime_tag="stressed")) == {"A": 1.4}

    def test_falls_back_to_global_when_unknown(self):
        desk = self._desk({"A": 1.5}, None)
        assert desk._cal_weights_for(_snap(_closes(120, vol=0.05))) == {"A": 1.5}
        desk2 = self._desk({"A": 1.5}, {})
        assert desk2._cal_weights_for(_snap(_closes(120, vol=0.05))) == {"A": 1.5}
        desk3 = self._desk({"A": 1.5}, {"calm": {"A": 0.6}})
        # malformed snap -> regime unknown -> exact global map
        assert desk3._cal_weights_for(None) == {"A": 1.5}
