"""Sample backtest runner: ``python -m hft.sample_run`` (from the repo root).

Runs the Avellaneda-Stoikov-style market maker on the synthetic feed with
the reference parameters and prints the metrics table. Deterministic for a
fixed seed.
"""

from __future__ import annotations

import argparse

from .backtest import Backtest, BacktestConfig
from .feed import SyntheticL2Feed
from .latency import LatencyConfig, LatencyModel
from .risk import RiskGateway, RiskLimits
from .strategies import AvellanedaStoikovMarketMaker


def run_sample(seed: int = 7, sim_minutes: float = 30.0,
               taker_fee_bps: float = 5.0,
               one_way_latency_us: float = 250.0) -> dict:
    feed = SyntheticL2Feed(seed=seed, sim_seconds=sim_minutes * 60.0,
                           events_per_sec=2000)
    strategy = AvellanedaStoikovMarketMaker()
    # NOTE: the reference MM re-quotes every 50 ms sim (~40 orders/sec at
    # ~$500 notional each ≈ $1.2M/min), so the per-minute notional budget
    # is sized to the strategy. The default $100k/min cap is a sane
    # production-ish default (unit-tested) — it would throttle this
    # reference quoting loop, which is the guard working as designed.
    risk = RiskGateway(RiskLimits(max_order_notional=25_000.0,
                                  max_notional_per_minute=2_000_000.0,
                                  max_position=200,
                                  max_orders_per_sec=100,
                                  daily_loss_limit=1_000.0))
    latency = LatencyModel(LatencyConfig(
        one_way_ns=int(one_way_latency_us * 1_000),
        jitter_sigma=0.25, seed=seed))
    bt = Backtest(feed, strategy, risk,
                  BacktestConfig(seed=seed, taker_fee_bps=taker_fee_bps),
                  latency)
    result = bt.run()
    return result.metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="HFT Lab v1 sample backtest")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--taker-fee-bps", type=float, default=5.0)
    ap.add_argument("--latency-us", type=float, default=250.0,
                    help="one-way exchange latency in microseconds")
    args = ap.parse_args()

    metrics = run_sample(seed=args.seed, sim_minutes=args.minutes,
                         taker_fee_bps=args.taker_fee_bps,
                         one_way_latency_us=args.latency_us)
    print("HFT Lab v1 — sample backtest (paper simulator, synthetic feed)")
    print(f"seed={args.seed} minutes={args.minutes} "
          f"taker_fee={args.taker_fee_bps}bps latency_us={args.latency_us}")
    print("-" * 64)
    for key in sorted(metrics):
        print(f"{key:28s} {metrics[key]:>16.4f}")


if __name__ == "__main__":
    main()
