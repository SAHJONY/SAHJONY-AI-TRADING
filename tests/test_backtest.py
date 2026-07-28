"""Offline checks for the 5m BTC backtest harness (python -m tests.test_backtest).

These assert the *mechanics* — causality, fill priority, fee/slippage direction,
sizing, the leverage cap and the §0 edge gate. They deliberately assert nothing
about profitability: the harness runs on synthetic bars here, and a synthetic
P&L number is not evidence of anything.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from backtest import indicators as ta
from backtest import synth
from backtest.data import Bars, load_csv, save_csv
from backtest.engine import Backtester, CostModel, RiskConfig, Setup, Strategy
from backtest.strategies import REGISTRY

FAILURES = []


def _check(cond: bool, label: str) -> None:
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        FAILURES.append(label)


def _flat_bars(n=500, px=50_000.0) -> Bars:
    ts = np.arange(n, dtype=np.int64) * 300_000 + 1_735_689_600_000
    c = np.full(n, px)
    return Bars(ts, c.copy(), c + 50, c - 50, c.copy(), np.full(n, 10.0))


class _AlwaysLong(Strategy):
    """Fires once at a fixed bar so fills/fees/sizing can be asserted exactly."""
    id, name, warmup = "test", "test", 10

    def __init__(self, at=100, stop_off=-500.0, tp_off=1500.0):
        self.at, self.stop_off, self.tp_off = at, stop_off, tp_off

    def prepare(self, b):
        return {"atr": ta.atr(b.high, b.low, b.close, 14)}

    def signal(self, t, b, ind):
        if t != self.at:
            return None
        c = b.close[t]
        return Setup(side=1, entry_kind="close", stop=c + self.stop_off,
                     targets=[(c + self.tp_off, 1.0)])


def main() -> int:
    print("\n── indicators are causal ──")
    b = synth.make(days=20, seed=3)
    n = len(b)
    cut = n - 50
    full = ta.atr(b.high, b.low, b.close, 14)
    part = ta.atr(b.high[:cut], b.low[:cut], b.close[:cut], 14)
    _check(np.allclose(full[:cut][-20:], part[-20:], equal_nan=True),
           "ATR at bar t does not change when future bars are appended")
    r_full, r_part = ta.rsi(b.close, 2), ta.rsi(b.close[:cut], 2)
    _check(np.allclose(r_full[:cut][-20:], r_part[-20:], equal_nan=True),
           "RSI at bar t is unaffected by future bars")
    a_full, _, _ = ta.adx(b.high, b.low, b.close, 14)
    a_part, _, _ = ta.adx(b.high[:cut], b.low[:cut], b.close[:cut], 14)
    _check(np.allclose(a_full[:cut][-20:], a_part[-20:], equal_nan=True),
           "ADX at bar t is unaffected by future bars")

    fh, fl, fhi, fli = ta.fractals(b.high, b.low, 3)
    ages = [t - int(fhi[t]) for t in range(300, n) if fhi[t] >= 0]
    _check(min(ages) >= 3, "a fractal is never visible before its right shoulder closes")

    dc_hi, _ = ta.donchian(b.high, b.low, 20)
    t0 = 300
    _check(abs(dc_hi[t0] - b.high[t0 - 20:t0].max()) < 1e-9,
           "Donchian excludes the current bar (no self-comparison on breakouts)")

    print("\n── fills, fees and slippage all point against the trade ──")
    flat = _flat_bars()
    zero = CostModel(taker_bps=0.0, maker_bps=0.0, base_slip_bps=0.0)
    risk = RiskConfig(equity0=100_000.0, risk_pct=0.01, min_edge_mult=0.0)
    res = Backtester(flat, zero, risk).run(_AlwaysLong(at=100))
    tr = res["trades"][0]
    _check(abs(tr.entry_px - 50_000.0) < 1e-9, "zero-cost fill lands exactly on the close")
    _check(abs(tr.qty - (100_000.0 * 0.01) / 500.0) < 1e-6,
           "qty = risk_$ / stop_distance (fixed-fractional off the stop)")

    costed = CostModel(taker_bps=4.5, maker_bps=1.5, base_slip_bps=0.8)
    res2 = Backtester(flat, costed, risk).run(_AlwaysLong(at=100))
    tr2 = res2["trades"][0]
    _check(tr2.entry_px > 50_000.0, "a long pays slippage upward on entry")
    _check(tr2.fees > 0 and tr2.pnl < res["trades"][0].pnl,
           "adding fees strictly reduces the trade's P&L")

    print("\n── pessimistic intrabar resolution ──")
    n2 = 300
    ts = np.arange(n2, dtype=np.int64) * 300_000
    c = np.full(n2, 50_000.0)
    hi, lo = c + 50, c - 50
    hi[101], lo[101] = 52_000.0, 49_000.0     # bar straddles both stop and target
    bars2 = Bars(ts, c.copy(), hi, lo, c.copy(), np.full(n2, 10.0))
    res3 = Backtester(bars2, zero, risk).run(_AlwaysLong(at=100, stop_off=-500.0,
                                                        tp_off=1500.0))
    _check(res3["trades"][0].reason == "stop",
           "when one bar covers stop and target, the stop is taken")
    _check(res3["trades"][0].r < 0, "…and the trade books a loss, not a win")

    print("\n── risk controls ──")
    tight = Backtester(flat, zero, RiskConfig(equity0=100_000.0, risk_pct=0.01,
                                              leverage_cap=1.0, min_edge_mult=0.0))
    res4 = tight.run(_AlwaysLong(at=100, stop_off=-50.0, tp_off=1500.0))
    _check(len(res4["trades"]) == 0 and res4["skipped_leverage"] == 1,
           "a setup breaching the leverage cap is skipped, never resized into it")

    gated = Backtester(flat, costed, RiskConfig(equity0=100_000.0, risk_pct=0.01,
                                               min_edge_mult=3.0))
    res5 = gated.run(_AlwaysLong(at=100, stop_off=-500.0, tp_off=20.0))
    _check(len(res5["trades"]) == 0 and res5["skipped_edge"] == 1,
           "§0 edge gate rejects a target that cannot clear round-trip cost")

    print("\n── every strategy runs end to end ──")
    b2 = synth.make(days=60, seed=11)
    for sid, cls in REGISTRY.items():
        r = Backtester(b2).run(cls())
        ok = all(np.isfinite(t.pnl) and np.isfinite(t.r) for t in r["trades"])
        _check(ok and np.isfinite(r["equity_final"]),
               f"{sid}: {len(r['trades'])} trades, finite equity")

    print("\n── funnel instrumentation is observation-only ──")
    for sid, cls in REGISTRY.items():
        plain = Backtester(b2).run(cls())
        instr = Backtester(b2, funnel=True).run(cls())
        same = (len(plain["trades"]) == len(instr["trades"])
                and all(abs(x.pnl - y.pnl) < 1e-9 and x.entry_ts == y.entry_ts
                        for x, y in zip(plain["trades"], instr["trades"])))
        _check(same, f"{sid}: --funnel does not change any trade")
    f = Backtester(b2, funnel=True).run(REGISTRY["s9"]())["funnel"]
    rows = f.rows()
    _check(bool(rows) and all(r["reached"] >= r["passed"] for r in rows),
           "funnel rows are internally consistent (passed <= reached)")
    _check(all(rows[i]["reached"] >= rows[i + 1]["reached"]
               for i in range(len(rows) - 1) if rows[i + 1]["reached"] <= rows[i]["passed"]),
           "gate ordering is monotone where the funnel is sequential")

    print("\n── portfolio mode ──")
    from backtest import portfolio as pf
    strats = [cls() for cls in REGISTRY.values()]
    bt = Backtester(b2)
    port = bt.run_many(strats, arm=pf.router(strats))
    solo = {sid: Backtester(b2).run(cls()) for sid, cls in REGISTRY.items()}
    solo_n = sum(len(r["trades"]) for r in solo.values())
    _check(len(port["trades"]) <= solo_n,
           "one position at a time cannot produce more trades than running solo")
    _check(np.isfinite(port["equity_final"]) and port["strategy"] == "portfolio",
           "portfolio run returns a single shared equity curve")
    seen = {t.strategy for t in port["trades"]}
    _check(seen.issubset(set(REGISTRY)), "every portfolio trade is attributed to a strategy")

    one = Backtester(b2).run_many([REGISTRY["s9"]()])
    ref = Backtester(b2).run(REGISTRY["s9"]())
    _check(len(one["trades"]) == len(ref["trades"])
           and abs(one["equity_final"] - ref["equity_final"]) < 1e-9,
           "run() is exactly the N=1 case of run_many()")

    # The bug this catches: §0 originally routed S3 to HIGH only, but every S3
    # signal fires in LOW/NORMAL — ATR(14) is a trailing classifier and a squeeze
    # breaks out while the average still reflects the compressed bars. A strategy
    # routed only to regimes it never signals in is dead code.
    b3 = synth.make(days=180, seed=7)
    ts_at = {int(t): i for i, t in enumerate(b3.ts)}
    for sid, cls in REGISTRY.items():
        st = cls()
        r = Backtester(b3).run(st)
        if not r["trades"]:
            continue
        ind = st.prepare(b3)
        ap = ind["atr"] / b3.close
        fires_in = {pf.regime_of(float(ap[ts_at[t.entry_ts]])) for t in r["trades"]}
        armed_in = {pf.REGIME_NAMES[i] for i, (_, _, ids) in enumerate(pf.ROUTING)
                    if sid in ids}
        _check(bool(fires_in & armed_in),
               f"{sid}: routed to a regime it actually signals in "
               f"(fires {sorted(fires_in)}, armed {sorted(armed_in)})")

    print("\n── self-improvement: parameterisation ──")
    from backtest import optimize as opt
    for sid, cls in REGISTRY.items():
        base = Backtester(b2).run(cls())
        same = Backtester(b2).run(cls(**{}))
        _check(len(base["trades"]) == len(same["trades"]),
               f"{sid}: constructing with no overrides reproduces the spec")
    try:
        REGISTRY["s6"](not_a_real_param=1)
        _check(False, "unknown parameters are rejected")
    except ValueError:
        _check(True, "unknown parameters are rejected")

    print("\n── self-improvement: the guards discriminate ──")
    rng = np.random.default_rng(0)
    # (a) one parameter set genuinely best in every block -> PBO must be ~0
    good = np.tile(np.linspace(0.1, 1.0, 10)[:, None], (1, 8)) + rng.normal(0, .01, (10, 8))
    p_good = opt.pbo(good, seed=1)["pbo"]
    _check(p_good is not None and p_good <= 0.1,
           f"PBO ~0 when one parameter set really is best (got {p_good})")
    # (b) pure noise -> PBO must land near 0.5, i.e. the search learned nothing
    noise = rng.normal(0, 1, (30, 8))
    p_noise = opt.pbo(noise, seed=1)["pbo"]
    _check(p_noise is not None and 0.25 <= p_noise <= 0.75,
           f"PBO ~0.5 on pure noise (got {p_noise})")
    _check(p_noise > p_good, "PBO separates a real winner from a lucky one")

    # deflated Sharpe must charge for the number of trials
    rets = rng.normal(0.12, 1.0, 500)
    d1 = opt.deflated_sharpe(rets, n_trials=1)["dsr"]
    d500 = opt.deflated_sharpe(rets, n_trials=5000)["dsr"]
    _check(d1 is not None and d500 is not None and d1 > d500,
           f"the same Sharpe is worth less after more trials ({d1} -> {d500})")
    _check(opt.deflated_sharpe(rng.normal(0, 1, 10), n_trials=1)["dsr"] is None,
           "deflated Sharpe refuses to opine on a tiny sample")

    # stability: a plateau scores high, a spike scores low
    space = {"x": [1, 2, 3]}
    plateau = {json.dumps({"x": v}, sort_keys=True): 1.0 for v in (1, 2, 3)}
    spike = {json.dumps({"x": 1}, sort_keys=True): 0.05,
             json.dumps({"x": 2}, sort_keys=True): 1.0,
             json.dumps({"x": 3}, sort_keys=True): 0.05}
    _check(opt.stability(space, plateau, {"x": 2})["stability"] >= 0.9,
           "a plateau optimum is reported stable")
    _check(opt.stability(space, spike, {"x": 2})["stability"] <= 0.2,
           "a spike optimum is reported unstable")

    # the gate defaults to refusing
    empty = {"strategy": "sX", "oos_trades": [], "folds": [], "param_drift": {}}
    dec = opt.promote(empty, {"pbo": None}, {"dsr": None}, {"stability": None})
    _check(not dec["promoted"] and len(dec["failed_checks"]) >= 5,
           "promotion gate refuses by default and says why")

    print("\n── data round-trip ──")
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        p = save_csv(b2.slice(0, 200), os.path.join(d, "bars.csv"))
        back = load_csv(p)
        _check(len(back) == 200 and abs(back.close[-1] - b2.close[199]) < 1e-6,
               "CSV save → load preserves bars")

    print()
    if FAILURES:
        print(f"BACKTEST HARNESS CHECKS FAILED ✗ ({len(FAILURES)})")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("BACKTEST HARNESS CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
