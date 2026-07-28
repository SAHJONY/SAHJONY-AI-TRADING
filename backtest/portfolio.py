"""Portfolio mode — the book as §0 of the playbook actually specifies it.

Running six strategies as six independent backtests, each on its own $100k with
its own daily loss stop, is not what the playbook describes and flatters the
result: it ignores that these strategies correlate 0.6–0.9 intraday, and it lets
six separate circuit breakers absorb what should be one.

Portfolio mode runs them on **one shared equity curve**, with:
  • one directional position at a time,
  • one portfolio-level daily loss stop and consecutive-loss size reduction,
  • the §0 regime-routing table deciding which strategies are even armed.

Not implemented: §0's exception allowing a second concurrent position when it is
the opposite methodology class and total notional stays under the cap. One at a
time is the conservative reading, and the correlation argument in §0 is the
reason the exception is narrow in the first place.

Note that a strategy which is not armed in the current regime is not polled at
all, so its internal state (S2's per-session budget, S6's per-leg budget, S9's
per-range budget) does not advance while it is stood down. That is intended — a
stood-down desk is not tracking setups it could not have taken.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from backtest.engine import Strategy

# Routing: ATR% bucket -> strategy ids, highest priority first.
#
# CORRECTED against §0's original table, which routed S3 to HIGH only. Measured:
# every S3 signal fires in LOW/NORMAL, so under the original table S3 was dead
# code. The cause is definitional, not statistical — ATR(14) is a *trailing*
# classifier, and a squeeze breakout fires while the average still reflects the
# compressed bars it is breaking out of. §0's table also contradicted the
# strategies' own "Optimal market regime" sections (S3: "transition from LOW to
# HIGH"). Each row below now follows the strategy's own section:
#
#   S1 ranging, LOW/NORMAL      S2 trend expansion, NORMAL/HIGH
#   S3 LOW->HIGH transition     S5 ranging + HIGH session opens
#   S6 trend, NORMAL/HIGH       S9 ranging, LOW/NORMAL
#
# Priority inside a bucket is by scarcity and time-criticality — a setup that
# fires rarely and must be taken on the signal bar outranks a frequent one —
# never by observed P&L, which would be fitting to the sample.
#
# S4/S7/S8/S10 need data this harness does not have, so EXTREME routes to
# nothing and the desk stands down, exactly as §0 intends.
ROUTING: List = [
    (0.0000, 0.0012, ["s3", "s9", "s1", "s5"]),                # LOW
    (0.0012, 0.0030, ["s3", "s2", "s6", "s5", "s1", "s9"]),    # NORMAL
    (0.0030, 0.0060, ["s2", "s6", "s5"]),                      # HIGH
    (0.0060, 9.9999, []),                                      # EXTREME — stand down
]

REGIME_NAMES = ["LOW", "NORMAL", "HIGH", "EXTREME"]


def regime_of(atr_pct: float) -> str:
    for i, (lo, hi, _) in enumerate(ROUTING):
        if lo <= atr_pct < hi:
            return REGIME_NAMES[i]
    return "EXTREME"


def router(strats: List[Strategy], enabled: bool = True) -> Callable:
    """Build the `arm(t, atr_pct)` callback that run_many() consults each bar."""
    idx_of = {s.id: i for i, s in enumerate(strats)}
    table = [[idx_of[sid] for sid in ids if sid in idx_of] for _, _, ids in ROUTING]
    all_idx = list(range(len(strats)))

    def arm(t: int, atr_pct: float) -> List[int]:
        if not enabled:
            return all_idx
        for i, (lo, hi, _) in enumerate(ROUTING):
            if lo <= atr_pct < hi:
                return table[i]
        return []

    return arm


def attribution(trades) -> Dict[str, Dict]:
    """Split a portfolio's trade list back out by strategy."""
    out: Dict[str, Dict] = {}
    for t in trades:
        d = out.setdefault(t.strategy, {"trades": 0, "net_pnl": 0.0, "total_r": 0.0,
                                        "wins": 0})
        d["trades"] += 1
        d["net_pnl"] += t.pnl
        d["total_r"] += t.r
        d["wins"] += 1 if t.r > 0 else 0
    for sid, d in out.items():
        d["net_pnl"] = round(d["net_pnl"], 2)
        d["total_r"] = round(d["total_r"], 2)
        d["hit_rate"] = round(d["wins"] / d["trades"], 3) if d["trades"] else 0.0
        d["expectancy_r"] = round(d["total_r"] / d["trades"], 4) if d["trades"] else 0.0
        del d["wins"]
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["trades"]))


def format_attribution(attr: Dict[str, Dict]) -> str:
    if not attr:
        return "  (no trades)"
    lines = ["  strategy  trades   hit_rate   expectancy_r   total_r   net_pnl"]
    for sid, d in attr.items():
        lines.append(f"  {sid:<10}{d['trades']:<9}{d['hit_rate']:<11}"
                     f"{d['expectancy_r']:<15}{d['total_r']:<10}{d['net_pnl']}")
    return "\n".join(lines)
