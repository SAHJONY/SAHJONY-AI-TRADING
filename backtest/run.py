"""CLI for the 5m BTC backtests.

Real data (what you want):
    python -m backtest.run --source binance-vision --months 2026-01:2026-06 \
        --cache backtest/data/BTCUSDT-5m.csv --out backtest/results/report.md
    python -m backtest.run --csv path/to/BTCUSDT-5m.csv --out report.md

Harness self-test (proves the plumbing, proves nothing about edge):
    python -m backtest.run --synth 180

Walk-forward split (report in/out-of-sample separately):
    python -m backtest.run --csv bars.csv --split 0.6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

from backtest import metrics
from backtest.data import (Bars, DataUnavailable, desk_coverage, fetch,
                           load_csv, load_desk_db)
from backtest.engine import Backtester, CostModel, RiskConfig
from backtest import portfolio as pf
from backtest.strategies import REGISTRY


def _months(spec: str) -> List[str]:
    """'2026-01:2026-06' -> ['2026-01', ..., '2026-06']; also accepts a CSV list."""
    if ":" not in spec:
        return [s.strip() for s in spec.split(",") if s.strip()]
    a, b = spec.split(":", 1)
    y0, m0 = (int(x) for x in a.split("-"))
    y1, m1 = (int(x) for x in b.split("-"))
    out = []
    while (y0, m0) <= (y1, m1):
        out.append(f"{y0:04d}-{m0:02d}")
        m0 += 1
        if m0 == 13:
            y0, m0 = y0 + 1, 1
    return out


def _load(args) -> Bars:
    if args.desk_db:
        return load_desk_db(args.desk_db, symbol=args.desk_symbol,
                            interval_m=args.desk_interval,
                            min_ticks=args.desk_min_ticks)
    if args.csv:
        return load_csv(args.csv)
    if args.synth:
        from backtest import synth
        return synth.make(days=args.synth, seed=args.seed)
    return fetch(source=args.source, symbol=args.symbol,
                 months=_months(args.months) if args.months else [],
                 cache=args.cache)


def run_all(bars: Bars, ids: List[str], costs: CostModel, risk: RiskConfig,
            entry_mode: str, funnel: bool = False):
    bt = Backtester(bars, costs, risk, entry_mode=entry_mode, funnel=funnel)
    rows, funnels = [], []
    for sid in ids:
        cls = REGISTRY.get(sid)
        if cls is None:
            print(f"  ! unknown strategy '{sid}' (have: {', '.join(REGISTRY)})")
            continue
        res = bt.run(cls())
        row = metrics.summarize(res, bars, risk.equity0)
        if res.get("funnel") is not None:
            row["funnel"] = res["funnel"].rows()
            funnels.append(res["funnel"])
        rows.append(row)
    return rows, funnels


def run_portfolio(bars: Bars, ids: List[str], costs: CostModel, risk: RiskConfig,
                  args):
    """Run the selected strategies as a single book on one equity curve."""
    strats = [REGISTRY[s]() for s in ids if s in REGISTRY]
    bt = Backtester(bars, costs, risk, entry_mode=args.entry, funnel=args.funnel)
    res = bt.run_many(strats, arm=pf.router(strats, enabled=not args.no_routing))
    row = metrics.summarize(res, bars, risk.equity0)
    attr = pf.attribution(res["trades"])
    row["attribution"] = attr
    row["routing"] = "off" if args.no_routing else "§0 regime table"
    return [row], res.get("funnels", []), attr


def _report(bars: Bars, rows: List[Dict], bh: Dict, args, label: str,
            funnels=()) -> str:
    lines = [f"# Backtest — {label}", "",
             f"- **Data:** {bars.describe()}",
             f"- **Entry mode:** {args.entry}",
             f"- **Costs:** taker {args.taker}bps / maker {args.maker}bps per side, "
             f"base slip {args.slip}bps (vol-scaled, x2 on stops)",
             f"- **Sizing:** {args.risk_pct * 100:.2f}% equity per trade, "
             f"leverage cap {args.leverage}x, daily loss stop {args.daily_stop * 100:.1f}%",
             f"- **Edge gate (§0):** TP1 >= {args.min_edge}x round-trip cost",
             f"- **Buy & hold reference:** {bh['return_pct']}% return, "
             f"{bh['max_dd_pct']}% max DD, Sharpe {bh['sharpe']}", "",
             "## Summary", "", "```", metrics.format_table(rows), "```", ""]
    for r in rows:
        lines += [f"### {r['strategy'].upper()} — {r['name']}", "", "```json",
                  json.dumps(r, indent=2), "```", ""]
    if funnels:
        lines += ["## Signal funnels", "",
                  "Each row is evaluations that reached that gate *and* passed it; "
                  "the drop to the next row is what the gate costs.", "", "```"]
        for f in funnels:
            lines += [f.report(), ""]
        lines += ["```", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backtest the OHLCV-only 5m BTC strategies")
    src = p.add_argument_group("data")
    src.add_argument("--csv", help="path to a 5m OHLCV CSV")
    src.add_argument("--source", default="binance-vision",
                     choices=["binance-vision", "binance", "bybit", "public-btc-5m", "public-btc-1h", "sp500-65y", "sp500-1d", "nasdaq-1d"])
    src.add_argument("--symbol", default="BTCUSDT")
    src.add_argument("--months", help="e.g. 2026-01:2026-06 (binance-vision)")
    src.add_argument("--cache", help="CSV cache path for fetched bars")
    src.add_argument("--synth", type=int, metavar="DAYS",
                     help="synthetic bars — harness self-test only, NOT evaluation")
    src.add_argument("--seed", type=int, default=7)
    src.add_argument("--desk-db", metavar="SQLITE",
                     help="bars recorded from the desk's own live feed "
                          "(utils/bar_recorder.py) — real prices, real timestamps")
    src.add_argument("--desk-symbol", default="",
                     help="e.g. BTC/USD; default = the symbol with the most bars")
    src.add_argument("--desk-interval", type=int, default=0,
                     help="bar interval in the recorder DB; default = the busiest")
    src.add_argument("--desk-min-ticks", type=int, default=2,
                     help="drop bars observed fewer times than this (default 2: a "
                          "1-observation bar has no measured range)")
    src.add_argument("--desk-coverage", action="store_true",
                     help="report what the recorder has accumulated, then exit")

    p.add_argument("--strategies", default="s1,s2,s3,s5,s6,s9")
    p.add_argument("--entry", default="spec", choices=["spec", "next_open"],
                   help="'next_open' forces market entries to the next bar's open")
    p.add_argument("--split", type=float, default=0.0,
                   help="fraction for an in-sample / out-of-sample split, e.g. 0.6")
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--risk-pct", type=float, default=0.0035)
    p.add_argument("--leverage", type=float, default=5.0)
    p.add_argument("--daily-stop", type=float, default=0.02)
    p.add_argument("--taker", type=float, default=4.5)
    p.add_argument("--maker", type=float, default=1.5)
    p.add_argument("--slip", type=float, default=0.8)
    p.add_argument("--min-edge", type=float, default=3.0,
                   help="playbook §0 gate: TP1 must clear round-trip cost by this "
                        "multiple. Lower it only to measure sensitivity.")
    p.add_argument("--funding-bps", type=float, default=0.0,
                   help="perp funding per 8h, charged pro-rata on hold time")
    p.add_argument("--portfolio", action="store_true",
                   help="run the selected strategies as one book: shared equity, "
                        "one position at a time, portfolio-level circuit breakers")
    p.add_argument("--no-routing", action="store_true",
                   help="portfolio mode without the §0 regime-routing table "
                        "(all strategies armed in every regime)")
    p.add_argument("--funnel", action="store_true",
                   help="report, per strategy, how many evaluations each entry "
                        "condition passed — shows which gate kills the signals")
    p.add_argument("--out", help="write a markdown report here")
    p.add_argument("--json", dest="json_out", help="write raw stats JSON here")
    args = p.parse_args(argv)

    if args.desk_coverage:
        if not args.desk_db:
            print("--desk-coverage needs --desk-db", file=sys.stderr)
            return 2
        try:
            cov = desk_coverage(args.desk_db)
        except DataUnavailable as exc:
            print(f"DATA UNAVAILABLE: {exc}", file=sys.stderr)
            return 2
        print(f"{'symbol':<12}{'iv':>4}{'bars':>8}{'days':>8}{'ticks/bar':>11}"
              f"{'1-tick %':>10}{'expected':>10}")
        for c in cov:
            print(f"{c['symbol']:<12}{c['interval_m']:>4}{c['bars']:>8}"
                  f"{c['span_days']:>8.2f}{c['ticks_per_bar']:>11.2f}"
                  f"{c['single_tick_pct']:>10.1f}{c['expected_bars']:>10}")
        print("\n'1-tick %' is the share of bars with open==high==low==close. Those "
              "have a price but no range;\nATR, wicks and intrabar stop tests are "
              "meaningless on them. High values mean the recorder\ninterval is "
              "finer than the desk's poll cadence.")
        return 0

    try:
        bars = _load(args)
    except DataUnavailable as exc:
        print(f"DATA UNAVAILABLE: {exc}", file=sys.stderr)
        return 2

    if args.desk_db:
        print("note: recorded-feed bars carry a TICK COUNT in the volume column, "
              "not traded volume.\n      Volume gates (s2 vol_mult, s15, s1's "
              "capitulation filter) measure sampling\n      frequency here, not "
              "participation. Read their results accordingly.")

    if args.synth:
        print("!" * 78)
        print("! SYNTHETIC DATA — this validates the harness, not any strategy edge.")
        print("!" * 78)

    costs = CostModel(taker_bps=args.taker, maker_bps=args.maker,
                      base_slip_bps=args.slip, funding_bps_per_8h=args.funding_bps)
    risk = RiskConfig(equity0=args.equity, risk_pct=args.risk_pct,
                      leverage_cap=args.leverage, daily_loss_stop_pct=args.daily_stop,
                      min_edge_mult=args.min_edge)
    ids = [s.strip() for s in args.strategies.split(",") if s.strip()]

    print(bars.describe())
    segments = [("full sample", bars)]
    if args.split and 0.1 < args.split < 0.9:
        k = int(len(bars) * args.split)
        segments = [("in-sample", bars.slice(0, k)),
                    ("out-of-sample", bars.slice(k, len(bars)))]

    all_rows, chunks = {}, []
    for label, seg in segments:
        if args.portfolio:
            rows, funnels, attr = run_portfolio(seg, ids, costs, risk, args)
        else:
            rows, funnels = run_all(seg, ids, costs, risk, args.entry, args.funnel)
            attr = None
        bh = metrics.buy_hold(seg)
        all_rows[label] = rows
        print(f"\n=== {label} — {seg.describe()}")
        print(metrics.format_table(rows))
        print(f"buy&hold: {bh['return_pct']}% ret, {bh['max_dd_pct']}% DD, "
              f"Sharpe {bh['sharpe']}")
        if attr:
            print("\n-- attribution (shared equity, one position at a time) --")
            print(pf.format_attribution(attr))
        if funnels:
            print("\n-- signal funnels --")
            for f in funnels:
                print(f.report())
                print()
        chunks.append(_report(seg, rows, bh, args, label, funnels))

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        header = ("> **Synthetic data — harness validation only. Not evidence of "
                  "edge.**\n\n") if args.synth else ""
        with open(args.out, "w") as fh:
            fh.write(header + "\n\n".join(chunks) + "\n")
        print(f"\nreport -> {args.out}")
    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump({"data": bars.describe(), "synthetic": bool(args.synth),
                       "segments": all_rows}, fh, indent=2)
        print(f"json   -> {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
