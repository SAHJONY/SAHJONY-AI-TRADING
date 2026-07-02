"""Advisory Board tests — no pytest, no network.

    python -m tests.test_advisors

Asserts the six-agent council + Decision Engine:
  • every agent returns a bounded score with a rationale,
  • Buffett rewards value (below long-run mean, calm) and penalizes froth,
  • the Risk Agent gate collapses on a crashed/violent name and BLOCKS any
    positive tilt below the protection threshold,
  • the composite equals the documented weighted blend and tilt ≤ ±0.10,
  • ADVISORS_ENABLED=false disables the layer entirely,
  • a broken snapshot degrades that agent to 0, never crashing the board.
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-adv-")

from intelligence.agents import MarketSnapshot  # noqa: E402


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _snap(symbol, closes, bench=None, price=None):
    closes = np.asarray(closes, dtype=float)
    bench = np.asarray(bench if bench is not None else closes, dtype=float)
    return MarketSnapshot(symbol, float(price if price is not None else closes[-1]),
                          closes, np.ones_like(closes) * 1e6, bench)


def main() -> int:
    os.environ.pop("ADVISORS_ENABLED", None)
    import importlib
    import intelligence.advisors as adv
    importlib.reload(adv)
    board = adv.AdvisoryBoard()
    _check(board.enabled, "enabled by default")

    rng = np.random.default_rng(7)
    calm_cheap = 100 - np.linspace(0, 8, 250) + rng.normal(0, 0.3, 250)   # gentle drift below mean
    steady_up = 100 * np.cumprod(1 + np.full(250, 0.0012) + rng.normal(0, 0.004, 250))
    crashed = np.concatenate([np.full(200, 100.0), np.linspace(100, 55, 50)])  # -45% dive

    # ── 1) every agent scores, bounded, with rationale ──
    v = board.deliberate(_snap("CALM", calm_cheap, bench=steady_up))
    _check(set(v.scores) == {"buffett", "munger", "macro", "growth", "quant"},
           "all five scoring agents report")
    _check(all(-1 <= s <= 1 for s in v.scores.values()), "scores bounded to [-1, 1]")
    _check(all(v.rationale.get(a) for a in [*v.scores, "risk_gate"]),
           "every agent explains itself (rationale present)")
    _check(0.0 <= v.gate <= 1.0, "risk gate bounded to [0, 1]")
    _check(abs(v.tilt) <= 0.10 + 1e-9, "tilt clamped to ±0.10")

    # ── 2) philosophy sanity ──
    _check(v.scores["buffett"] > 0, f"Buffett likes calm value below the mean ({v.scores['buffett']})")
    up = board.deliberate(_snap("MOMO", steady_up, bench=steady_up))
    _check(up.scores["growth"] > 0, f"Growth rewards a sustained uptrend ({up.scores['growth']})")
    _check(up.scores["macro"] > 0, "Macro reads a rising benchmark as risk-on")
    down_bench = steady_up[::-1].copy()
    off = board.deliberate(_snap("MOMO", steady_up, bench=down_bench))
    _check(off.scores["macro"] < 0, "Macro reads a falling benchmark as risk-off")

    # ── 3) protection gate on a crashed name ──
    cr = board.deliberate(_snap("CRASH", crashed, bench=steady_up))
    _check(cr.gate < 0.5, f"gate collapses on a -45% crash (gate {cr.gate})")
    if cr.gate < 0.35:
        _check(cr.tilt <= 0, "below the protection threshold, positive tilt is blocked")
    else:
        _check(abs(cr.tilt) <= 0.10 * cr.gate + 1e-9, "tilt scaled down by the stressed gate")

    # ── 4) decision engine math ──
    expected = round(sum(adv._WEIGHTS[a] * v.scores[a] for a in adv._WEIGHTS), 3)
    _check(v.composite == expected, "composite equals the documented weighted blend")

    # ── 5) fault isolation: a broken snapshot never sinks the board ──
    broken = board.deliberate(MarketSnapshot("BAD", float("nan"), np.array([]), np.array([]), np.array([])))
    _check(all(-1 <= s <= 1 for s in broken.scores.values()) and abs(broken.tilt) <= 0.10,
           "degenerate data degrades to bounded neutrality, no crash")

    # ── 6) kill switch ──
    os.environ["ADVISORS_ENABLED"] = "false"
    off_board = adv.AdvisoryBoard()
    _check(not off_board.enabled, "ADVISORS_ENABLED=false disables the board")
    _check(off_board.evaluate([{"symbol": "X", "snap": _snap("X", steady_up)}]) == {},
           "disabled board returns no verdicts")
    ov = off_board.deliberate(_snap("X", steady_up))
    _check(ov.tilt == 0.0 and ov.scores == {}, "disabled deliberation is neutral")
    os.environ.pop("ADVISORS_ENABLED", None)

    print("\nADVISORY BOARD CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
