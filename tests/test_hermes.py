"""Hermes guardian tests — no pytest, no network.

    python -m tests.test_hermes

Asserts the background agent:
  • quarantines hard data failures (bad price, NaN history, extreme jump) and
    forces their tilt to -1 so the Risk Officer blocks new risk,
  • flags soft issues (stale feed) without quarantining,
  • learns: consistently-correct council calls earn a positive bounded tilt,
    consistently-wrong ones a negative bounded tilt (|tilt| ≤ 0.10),
  • reports honest scorecard math (rising curve → positive Sharpe, no drawdown),
  • is fully disabled by HERMES_ENABLED=false,
  • never mutates anything but state['hermes'].
"""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-hermes-")

from config import load_config  # noqa: E402


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _row(sym, price, closes, direction="long"):
    return {"symbol": sym,
            "snap": SimpleNamespace(symbol=sym, price=price, closes=closes),
            "verdict": SimpleNamespace(direction=direction)}


def main() -> int:
    from intelligence.hermes import Hermes, _MAX_TILT, _MIN_OBS

    good_closes = [100 + i * 0.1 for i in range(60)]

    # ── 1) data integrity: quarantine hard failures, flag soft ones ──
    os.environ.pop("HERMES_ENABLED", None)
    h = Hermes(load_config())
    _check(h.enabled, "enabled by default")
    state = {}
    rep = h.review([
        _row("GOOD", 106.0, good_closes),
        _row("BADPX", 0.0, good_closes),                       # bad price
        _row("NANHIST", 100.0, good_closes[:-1] + [float("nan")]),  # NaN history
        _row("JUMPY", 200.0, good_closes),                     # ~89% jump vs last close
        _row("STALE", 100.0, [100.0] * 60),                    # flat feed → soft only
    ], state)
    _check(rep.used, "review runs when enabled")
    _check("GOOD" not in rep.quarantined and "GOOD" not in rep.issues, "clean feed passes untouched")
    for sym in ("BADPX", "NANHIST", "JUMPY"):
        _check(sym in rep.quarantined, f"{sym} quarantined (hard data failure)")
        _check(rep.tilt[sym] == -1.0, f"{sym} tilt forced to -1 (blocks new risk)")
    _check("STALE" not in rep.quarantined and "STALE" in rep.issues, "stale feed flagged but not quarantined")
    _check(abs(rep.data_ok_pct - 1 / 5) < 1e-9, f"data_ok_pct honest (got {rep.data_ok_pct})")

    # ── 1b) REGRESSION: NumPy-array closes must validate without crashing ──
    # Real broker adapters (Robinhood crypto, Alpaca) hand Hermes an np.ndarray
    # for closes. The old `getattr(snap,"closes",[]) or []` raised "truth value of
    # an array is ambiguous", which was caught and mis-scored as a HARD failure —
    # quarantining every crypto symbol so the desk never traded. Pin it.
    import numpy as np
    repnp = Hermes(load_config()).review([
        _row("NPGOOD", good_closes[-1], np.array(good_closes)),   # clean ndarray history
        _row("NPEMPTY", 50.0, np.array([])),                      # empty ndarray → soft only
    ], {})
    _check("NPGOOD" not in repnp.quarantined,
           "ndarray closes validate cleanly (no ambiguous-truth crash)")
    _check(not any("validator error" in " ".join(v) for v in repnp.issues.values()),
           "no validator error surfaced on ndarray history")

    # ── 2) self-improvement: correct calls → positive tilt; wrong → negative ──
    h2 = Hermes(load_config())
    st = {}
    price_up, price_dn = 100.0, 100.0
    for _ in range(_MIN_OBS + 4):
        h2.review([_row("WINNER", price_up, good_closes, "long"),
                   _row("LOSER", price_dn, good_closes, "long")], st)
        price_up *= 1.01   # WINNER: long call keeps being right
        price_dn *= 0.99   # LOSER: long call keeps being wrong
    rep2 = h2.review([_row("WINNER", price_up, good_closes, "long"),
                      _row("LOSER", price_dn, good_closes, "long")], st)
    _check(rep2.tilt["WINNER"] > 0, f"consistently-right calls earn positive tilt ({rep2.tilt['WINNER']})")
    _check(rep2.tilt["LOSER"] < 0, f"consistently-wrong calls earn negative tilt ({rep2.tilt['LOSER']})")
    _check(all(abs(t) <= _MAX_TILT for t in (rep2.tilt["WINNER"], rep2.tilt["LOSER"])),
           "calibration tilt bounded to ±0.10")
    _check(rep2.hit_rates["WINNER"] > 0.9 and rep2.hit_rates["LOSER"] < 0.1,
           "hit-rates reflect realized accuracy")
    _check(set(st.keys()) <= {"hermes", "hermes_events"},
           "only Hermes' own state keys are touched")

    # ── 3) sharp scores: honest scorecard math ──
    eq, curve = 100000.0, []
    for i in range(50):        # noisy uptrend: +0.3% / -0.1% alternating
        curve.append({"equity": eq})
        eq *= 1.003 if i % 2 == 0 else 0.999
    sc = Hermes.scorecard(curve)
    _check(sc["sharpe"] is not None and sc["sharpe"] > 0, f"rising noisy curve → positive Sharpe ({sc['sharpe']})")
    _check(sc["sortino"] is not None and sc["sortino"] > 0, f"Sortino computed ({sc['sortino']})")
    _check(sc["max_drawdown_pct"] <= 0 and sc["max_drawdown_pct"] > -1, "drawdown reflects the small dips")
    flat = Hermes.scorecard([{"equity": 100000.0}] * 10)
    _check(flat["sharpe"] is None, "zero-variance curve → Sharpe undefined (None), never fabricated")
    _check(Hermes.scorecard([])["sharpe"] is None, "empty curve → no fabricated stats")

    # ── 3b) strategy-level self-improvement: capital leans toward winning desks ──
    from intelligence.hermes import _W_MIN, _W_MAX
    h4 = Hermes(load_config())
    st4 = {}
    for _ in range(_MIN_OBS + 6):
        st4.setdefault("hermes_events", []).extend([
            {"strategy": "ladder", "realized": 25.0},    # ladder keeps winning
            {"strategy": "wheel", "realized": -12.0},    # wheel keeps losing
        ])
        rep4 = h4.review([_row("GOOD", 106.0, good_closes)], st4)
    _check(rep4.strategy_weights.get("ladder", 0) > 1.0,
           f"winning desk earns extra budget (ladder ×{rep4.strategy_weights.get('ladder')})")
    _check(rep4.strategy_weights.get("wheel", 1) < 1.0,
           f"losing desk gets trimmed (wheel ×{rep4.strategy_weights.get('wheel')})")
    _check(all(_W_MIN <= w <= _W_MAX for w in rep4.strategy_weights.values()),
           "strategy weights bounded — a desk is never switched off")
    _check(st4["hermes_events"] == [], "realized events consumed each review")

    # ── 4) kill switch ──
    os.environ["HERMES_ENABLED"] = "false"
    h3 = Hermes(load_config())
    _check(not h3.enabled, "HERMES_ENABLED=false disables the agent")
    rep3 = h3.review([_row("GOOD", 106.0, good_closes)], {})
    _check(not rep3.used and rep3.tilt == {}, "disabled agent returns a neutral report")
    os.environ.pop("HERMES_ENABLED", None)

    print("\nHERMES CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
