"""CLI for the self-improvement loop.

    python -m backtest.improve --csv bars.csv --strategy s6
    python -m backtest.improve --csv bars.csv --strategy s1 --folds 5 --blocks 8
    python -m backtest.improve --synth 400 --strategy s9 --out proposals/

Runs walk-forward parameter search, then the overfitting controls, then the
promotion gate — and writes a JSON *proposal*. It never edits a live config.

The search spaces below are deliberately small. A wide grid is not a more
thorough search, it is a larger multiple-testing penalty: every extra trial
raises the Sharpe you would expect from luck alone, which `deflated_sharpe`
charges you for. Search the parameters the funnels flagged, not all of them.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Dict

import numpy as np

from backtest import optimize as opt
from backtest.data import DataUnavailable, load_csv, load_desk_db
from backtest.engine import CostModel, RiskConfig
from backtest.strategies import REGISTRY

# Parameters worth searching, per strategy — chosen from the funnel diagnostics
# (docs/btc_futures_5m_backtest.md), not by enumerating every constant.
SPACES: Dict[str, Dict] = {
    "s1": {"min_score": [1.0, 0.8, 0.6], "band_sigma": [2.0, 2.5],
           "adx_max": [20.0, 25.0], "vol_mult": [1.2, 1.5]},
    "s2": {"width_min_atr": [0.3, 0.4, 0.6], "width_max_atr": [2.0, 2.5, 3.5],
           "vol_mult": [1.1, 1.3], "close_frac": [0.55, 0.6, 0.7]},
    "s3": {"min_run": [4.0, 6.0, 9.0], "bw_pct_max": [0.15, 0.20, 0.30],
           "vol_mult": [1.2, 1.4]},
    "s5": {"sweep_atr": [0.10, 0.15, 0.25], "min_level_age": [8.0, 12.0, 20.0],
           "reclaim_range_atr": [0.6, 0.8, 1.0]},
    "s6": {"zone_mode": ["both", "fib", "ema"], "retr_lo": [0.30, 0.382],
           "retr_hi": [0.618, 0.70], "adx_min": [20.0, 22.0, 25.0]},
    "s9": {"width_min_atr": [2.5, 3.0, 4.0], "width_max_atr": [7.0, 8.0, 10.0],
           "vol_mult": [1.0, 1.2], "bw_pct_min": [0.20, 0.30]},
    "s11": {"entry_n": [15.0, 20.0, 40.0], "exit_n": [8.0, 10.0, 20.0],
            "stop_atr": [1.5, 2.0, 3.0]},
    "s12": {"rsi_lo": [3.0, 5.0, 10.0], "trend_sma": [100.0, 200.0],
            "stop_atr": [1.5, 2.0, 3.0], "tp_atr": [1.5, 2.5, 4.0]},
    "s13": {"pb_lo": [0.0, 0.05, 0.10], "bb_k": [2.0, 2.5],
            "trend_sma": [100.0, 200.0], "stop_atr": [1.0, 1.5, 2.0]},
    "s14": {"lookback": [4.0, 7.0, 10.0], "stop_atr": [0.8, 1.0, 1.5],
            "tp1_atr": [1.0, 1.5, 2.5]},
    "s15": {"vol_mult": [2.0, 3.0, 5.0], "range_atr": [1.0, 1.2, 1.8],
            "close_frac": [0.65, 0.75, 0.85]},
    "s16": {"channel_n": [10.0, 20.0, 40.0], "body_ratio": [1.0, 1.5],
            "tp1_r": [1.0, 1.5, 2.5]},
    "s17": {"start_min": [420.0, 780.0, 840.0], "end_min": [600.0, 960.0, 1020.0],
            "mom_bars": [6.0, 12.0, 24.0], "mom_atr": [0.5, 0.75, 1.25]},
    "s18": {"htf_bars": [6.0, 12.0], "htf_fast": [8.0, 12.0], "htf_slow": [21.0, 26.0],
            "stop_atr": [1.0, 1.5, 2.0]},
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Walk-forward search + overfitting controls")
    p.add_argument("--csv", help="5m OHLCV CSV")
    p.add_argument("--desk-db", metavar="SQLITE",
                   help="bars recorded from the desk's own live feed")
    p.add_argument("--desk-symbol", default="")
    p.add_argument("--desk-interval", type=int, default=0)
    p.add_argument("--desk-min-ticks", type=int, default=2)
    p.add_argument("--source", choices=["public-btc-5m", "public-btc-1h",
                                        "sp500-65y", "sp500-1d", "nasdaq-1d"],
                   help="a bundled/public dataset instead of --csv")
    p.add_argument("--synth", type=int, metavar="DAYS",
                   help="synthetic bars — exercises the machinery, proves nothing")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--strategy", required=True, choices=sorted(SPACES))
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--mode", default="anchored", choices=["anchored", "rolling"])
    p.add_argument("--blocks", type=int, default=8, help="CSCV time blocks (even)")
    p.add_argument("--max-combos", type=int, default=200)
    p.add_argument("--min-trades", type=int, default=30,
                   help="objective floor per training window")
    p.add_argument("--min-oos-trades", type=int, default=300,
                   help="promotion floor on concatenated out-of-sample trades")
    p.add_argument("--taker", type=float, default=4.5)
    p.add_argument("--risk-pct", type=float, default=0.0035)
    p.add_argument("--out", help="directory to write the JSON proposal into")
    args = p.parse_args(argv)

    if args.desk_db:
        try:
            bars = load_desk_db(args.desk_db, symbol=args.desk_symbol,
                                interval_m=args.desk_interval,
                                min_ticks=args.desk_min_ticks)
        except DataUnavailable as exc:
            print(f"DATA UNAVAILABLE: {exc}", file=sys.stderr)
            return 2
    elif args.csv:
        try:
            bars = load_csv(args.csv)
        except DataUnavailable as exc:
            print(f"DATA UNAVAILABLE: {exc}", file=sys.stderr)
            return 2
    elif args.source:
        from backtest.data import fetch as _fetch
        bars = _fetch(source=args.source, symbol=args.source)
    elif args.synth:
        from backtest import synth
        bars = synth.make(days=args.synth, seed=args.seed)
        print("!" * 78)
        print("! SYNTHETIC DATA — this exercises the search machinery. Any parameter")
        print("! it 'finds' is fitted to a random process and means nothing.")
        print("!" * 78)
    else:
        print("need --desk-db, --csv, --source or --synth", file=sys.stderr)
        return 2

    cls = REGISTRY[args.strategy]
    space = SPACES[args.strategy]
    costs = CostModel(taker_bps=args.taker)
    risk = RiskConfig(risk_pct=args.risk_pct)
    objective = opt.Objective(min_trades=args.min_trades)

    print(f"{bars.describe()}")
    print(f"strategy: {cls.id} — searching {sorted(space)}")

    # 1. walk-forward
    wf = opt.walk_forward(bars, cls, space, folds=args.folds, mode=args.mode,
                          costs=costs, risk=risk, objective=objective,
                          max_combos=args.max_combos, seed=args.seed)
    print(f"\nwalk-forward ({wf['mode']}, {args.folds} folds, "
          f"{wf['combos_tried']} parameter sets per fold)")
    for i, f in enumerate(wf["folds"]):
        print(f"  fold {i}: train[{f.train[0]}:{f.train[1]}] "
              f"test[{f.test[0]}:{f.test[1]}]  IS={f.is_score:>8.3f}  "
              f"OOS n={f.oos_trades:<4} exp_r={f.oos_expectancy_r:>7.3f}  "
              f"{f.best_params}")
    oos = wf["oos_trades"]
    r = np.array([t.r for t in oos]) if oos else np.array([])
    print(f"  concatenated OOS: {len(oos)} trades, "
          f"expectancy {r.mean() if r.size else 0:.4f}R, total {r.sum() if r.size else 0:.2f}R")
    print(f"  parameter drift (cross-fold CV): {wf['param_drift']}")

    # 2. CSCV / PBO over the same grid on the full sample
    combos = opt.build_grid(space, max_combos=args.max_combos, seed=args.seed)
    M, counts = opt.block_performance(bars, cls, combos, blocks=args.blocks,
                                      costs=costs, risk=risk)
    pbo_res = opt.pbo(M, seed=args.seed)
    print(f"\nPBO (CSCV, {args.blocks} blocks): {pbo_res}")

    # 3. deflated Sharpe on the out-of-sample record
    per_combo_sr = []
    for i in range(M.shape[0]):
        row = M[i][counts[i] > 0]
        if row.size > 1 and row.std(ddof=1) > 0:
            per_combo_sr.append(row.mean() / row.std(ddof=1))
    trial_sd = float(np.std(per_combo_sr)) if len(per_combo_sr) > 1 else None
    dsr_res = opt.deflated_sharpe(r, n_trials=len(combos), trial_sr_std=trial_sd)
    print(f"deflated Sharpe: {dsr_res}")

    # 4. stability of the last fold's winner on the full-sample grid
    scores = {}
    for params in combos:
        res = opt.run_params(bars, cls, params, costs, risk)
        scores[json.dumps(params, sort_keys=True, default=str)] = objective(res["trades"])
    best = wf["folds"][-1].best_params if wf["folds"] else {}
    stab = opt.stability(space, scores, best)
    print(f"parameter stability: {stab}")

    # 5. promotion gate
    crit = opt.PromotionCriteria(min_oos_trades=args.min_oos_trades)
    decision = opt.promote(wf, pbo_res, dsr_res, stab, crit)
    print("\n── promotion gate ──")
    for c in decision["checks"]:
        print(f"  {'PASS' if c['pass'] else 'FAIL'}  {c['name']:<18}"
              f"{str(c['value']):<12} (need {c['requirement']})")
    print(f"\n  VERDICT: {'PROMOTE' if decision['promoted'] else 'REJECT'}"
          + ("" if decision["promoted"] else
             f" — failed {', '.join(decision['failed_checks'])}"))
    print(f"  {decision['note']}")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{cls.id}_proposal.json")
        payload = {
            "strategy": cls.id, "data": bars.describe(),
            "synthetic": bool(args.synth),
            "search_space": {k: list(v) for k, v in space.items()},
            "walk_forward": {
                "mode": wf["mode"], "combos_tried": wf["combos_tried"],
                "param_drift": wf["param_drift"],
                "folds": [{"train": f.train, "test": f.test,
                           "best_params": f.best_params, "is_score": f.is_score,
                           "oos_trades": f.oos_trades,
                           "oos_expectancy_r": f.oos_expectancy_r} for f in wf["folds"]],
                "oos_total_trades": len(oos),
                "oos_expectancy_r": float(r.mean()) if r.size else 0.0,
            },
            "pbo": pbo_res, "deflated_sharpe": dsr_res, "stability": stab,
            "decision": decision,
        }
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
        print(f"\nproposal -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
