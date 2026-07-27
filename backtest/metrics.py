"""Performance statistics for a backtest run.

Reported in R multiples wherever possible: with fixed-fractional sizing, R is
comparable across strategies and across volatility regimes in a way that dollar
P&L is not. Trade count is reported first and prominently — a strategy with 30
trades has no statistics worth reading.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from backtest.data import Bars
from backtest.engine import Trade

BARS_PER_YEAR = 365 * 24 * 12          # 5m bars, crypto trades every day


def _drawdown(eq: np.ndarray) -> float:
    e = eq[np.isfinite(eq)]
    if e.size == 0:
        return 0.0
    peak = np.maximum.accumulate(e)
    return float(np.min(e / peak - 1.0))


def _daily_returns(eq: np.ndarray, day_id: np.ndarray) -> np.ndarray:
    ok = np.isfinite(eq)
    eq, day_id = eq[ok], day_id[ok]
    if eq.size == 0:
        return np.array([])
    last_idx = np.searchsorted(day_id, np.unique(day_id), side="right") - 1
    closes = eq[last_idx]
    return np.diff(closes) / closes[:-1] if closes.size > 1 else np.array([])


def summarize(res: Dict, bars: Bars, equity0: float) -> Dict:
    trades: List[Trade] = res["trades"]
    eq = res["equity"]
    n = len(trades)
    out = {
        "strategy": res["strategy"], "name": res["name"], "trades": n,
        "skipped_leverage": res.get("skipped_leverage", 0),
        "skipped_edge": res.get("skipped_edge", 0),
        "skipped_halt": res.get("skipped_halt", 0),
    }
    if n == 0:
        out.update({"note": "no trades — filters never aligned on this sample"})
        return out

    r = np.array([t.r for t in trades])
    pnl = np.array([t.pnl for t in trades])
    fees = np.array([t.fees for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    days = max((bars.ts[-1] - bars.ts[0]) / 86_400_000.0, 1.0)
    dr = _daily_returns(eq, bars.day_id)

    gross_win = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())

    out.update({
        "trades_per_day": round(n / days, 2),
        "hit_rate": round(float((r > 0).mean()), 4),
        "expectancy_r": round(float(r.mean()), 4),
        "median_r": round(float(np.median(r)), 4),
        "avg_win_r": round(float(wins.mean()) if wins.size else 0.0, 3),
        "avg_loss_r": round(float(losses.mean()) if losses.size else 0.0, 3),
        "payoff_ratio": round(float(abs(wins.mean() / losses.mean()))
                              if wins.size and losses.size and losses.mean() else 0.0, 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else float("inf"),
        "total_r": round(float(r.sum()), 2),
        "net_pnl": round(float(pnl.sum()), 2),
        "return_pct": round(float(res["equity_final"] / equity0 - 1.0) * 100, 2),
        "max_dd_pct": round(_drawdown(eq) * 100, 2),
        "sharpe": round(float(dr.mean() / dr.std(ddof=0) * np.sqrt(365))
                        if dr.size > 2 and dr.std(ddof=0) > 0 else 0.0, 2),
        "sortino": round(float(dr.mean() / dr[dr < 0].std(ddof=0) * np.sqrt(365))
                         if (dr < 0).sum() > 2 and dr[dr < 0].std(ddof=0) > 0 else 0.0, 2),
        "fees_paid": round(float(fees.sum()), 2),
        "fees_pct_of_gross_win": round(float(fees.sum()) / gross_win * 100, 1) if gross_win else None,
        "avg_bars_held": round(float(np.mean([t.bars_held for t in trades])), 1),
        "mae_r_p50": round(float(np.percentile([t.mae_r for t in trades], 50)), 2),
        "mae_r_p90": round(float(np.percentile([t.mae_r for t in trades], 10)), 2),
        "worst_trade_r": round(float(r.min()), 2),
        "best_trade_r": round(float(r.max()), 2),
        "long_share": round(float(np.mean([t.side > 0 for t in trades])), 2),
    })

    by_reason: Dict[str, int] = {}
    for t in trades:
        by_reason[t.reason] = by_reason.get(t.reason, 0) + 1
    out["exit_reasons"] = dict(sorted(by_reason.items(), key=lambda kv: -kv[1]))

    # side split
    for lbl, mask in (("long", np.array([t.side > 0 for t in trades])),
                      ("short", np.array([t.side < 0 for t in trades]))):
        if mask.sum():
            out[f"{lbl}_n"] = int(mask.sum())
            out[f"{lbl}_expectancy_r"] = round(float(r[mask].mean()), 4)

    # regime-conditional expectancy (the playbook gates on exactly these buckets)
    ap = np.array([t.atr_pct for t in trades])
    buckets = (("LOW", ap < 0.0012), ("NORMAL", (ap >= 0.0012) & (ap < 0.0030)),
               ("HIGH", (ap >= 0.0030) & (ap < 0.0060)), ("EXTREME", ap >= 0.0060))
    out["by_regime"] = {lbl: {"n": int(m.sum()),
                              "expectancy_r": round(float(r[m].mean()), 3),
                              "hit_rate": round(float((r[m] > 0).mean()), 3)}
                        for lbl, m in buckets if m.sum() > 0}
    return out


def buy_hold(bars: Bars) -> Dict:
    ret = float(bars.close[-1] / bars.close[0] - 1.0)
    eq = bars.close / bars.close[0]
    dr = _daily_returns(eq, bars.day_id)
    return {"return_pct": round(ret * 100, 2),
            "max_dd_pct": round(_drawdown(eq) * 100, 2),
            "sharpe": round(float(dr.mean() / dr.std(ddof=0) * np.sqrt(365))
                            if dr.size > 2 and dr.std(ddof=0) > 0 else 0.0, 2)}


def format_table(rows: List[Dict]) -> str:
    cols = [("strategy", 9), ("trades", 7), ("hit_rate", 9), ("expectancy_r", 13),
            ("total_r", 9), ("return_pct", 11), ("max_dd_pct", 11),
            ("profit_factor", 14), ("sharpe", 7)]
    head = "".join(c.ljust(w) for c, w in cols)
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append("".join(str(r.get(c, "-")).ljust(w) for c, w in cols))
    return "\n".join(lines)
