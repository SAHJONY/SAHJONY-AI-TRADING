"""Replay backtest runner: ``python -m hft.replay_run`` (from the repo root).

Runs the Avellaneda-Stoikov-style market maker on the TRADE-PRINT replay
feed (:mod:`hft.replay`) and prints the metrics table. Deterministic for a
fixed fixture + seed.

Units: the fixture prices are BTC/USD converted to integer cent-ticks
(tick_size=0.01 in the feed). Integer quantities are milli-BTC
(``ReplayFeed.QTY_PER_BTC`` = 1000). The backtest/strategy/risk stack
therefore uses tick_size=1e-5 USD per tick-unit, i.e. one tick of one unit =
$0.00001, so a quote at 8,540,000 ticks on 1 unit = $85.40 = 1 milli-BTC.
PnL is in USD. No network, no live orders — paper simulator only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import Backtest, BacktestConfig
from .latency import LatencyConfig, LatencyModel
from .replay import QTY_PER_BTC, ReplayFeed
from .risk import RiskGateway
from .strategies import AvellanedaStoikovMarketMaker

DEFAULT_FIXTURE = str(
    Path(__file__).resolve().parent / "data" / "btcusd-trades.jsonl"
)

#: USD per (tick * qty-unit). See module docstring for the unit arithmetic.
USD_TICK = 1e-5


def run_replay(seed: int = 7, fixture: str = DEFAULT_FIXTURE,
               taker_fee_bps: float = 5.0,
               one_way_latency_us: float = 250.0) -> dict:
    feed = ReplayFeed(fixture, seed=seed, levels=5, tick_size=0.01)
    strategy = AvellanedaStoikovMarketMaker(tick_size=USD_TICK)
    risk = RiskGateway(tick_size=USD_TICK)  # default limits
    latency = LatencyModel(LatencyConfig(
        one_way_ns=int(one_way_latency_us * 1_000),
        jitter_sigma=0.25, seed=seed))
    bt = Backtest(feed, strategy, risk,
                  BacktestConfig(seed=seed, taker_fee_bps=taker_fee_bps),
                  latency, tick_size=USD_TICK)
    result = bt.run()
    return {"metrics": result.metrics, "feed": feed, "notes": result.notes}


def main() -> None:
    ap = argparse.ArgumentParser(description="HFT Lab v2 replay backtest")
    ap.add_argument("--fixture", type=str, default=DEFAULT_FIXTURE)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--taker-fee-bps", type=float, default=5.0)
    ap.add_argument("--latency-us", type=float, default=250.0,
                    help="one-way exchange latency in microseconds")
    args = ap.parse_args()

    out = run_replay(seed=args.seed, fixture=args.fixture,
                     taker_fee_bps=args.taker_fee_bps,
                     one_way_latency_us=args.latency_us)
    metrics = out["metrics"]
    feed = out["feed"]
    print("HFT Lab v2 — replay backtest (paper simulator, real-trade replay)")
    print(f"fixture={args.fixture}")
    print(f"trades={feed.n_trades} sim_seconds={feed.sim_seconds:.1f} "
          f"seed={args.seed} taker_fee={args.taker_fee_bps}bps "
          f"latency_us={args.latency_us} qty_unit=1/{QTY_PER_BTC} BTC")
    print("-" * 64)
    for key in sorted(metrics):
        print(f"{key:28s} {metrics[key]:>16.4f}")


if __name__ == "__main__":
    main()
