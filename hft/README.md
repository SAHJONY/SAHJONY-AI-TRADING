# HFT Lab v2 — research/paper high-frequency trading simulator

An offline, deterministic simulator for studying market-microstructure
mechanics: limit order books, matching engines, latency, quoting strategies,
pre-trade risk, audit trails, and event-driven backtesting. It runs on
synthetic data or on a fixed snapshot of real trade prints, with fixed
seeds, and **never touches a network, a broker, or real money** (the only
network code in the package is the paper-only Alpaca adapter, which fires
solely when explicitly called with user-supplied paper credentials).

This is a lab instrument, not a trading system. See **Limits** below.

## Architecture

```
 synthetic feed /           strategy              risk            venue
 real-trade replay
┌──────────────┐   ┌──────────────────┐   ┌──────────────┐   ┌──────────────┐
│ feed.py      │   │ strategies.py    │   │ risk.py      │   │ venue.py     │
│ SyntheticL2  │   │ Avellaneda-      │   │ Pre-trade    │   │ PaperVenue   │
│ Feed (seeded │   │ Stoikov market   │   │ gateway:     │   │ (in-memory   │
│ random walk) │   │ maker + adverse- │   │ notional /   │   │ matching     │
│              │   │ selection MM +   │   │ position /   │   │ engine),     │
│ replay.py    │   │ multi-level flow │   │ rate (global │   │ AlpacaPaper- │
│ ReplayFeed   │   │ strategy + micro-│   │ + per-symbol)│   │ Venue (paper │
│ (real Kraken │──▶│ structure signal;│──▶│ / per-minute │──▶│ endpoint    │
│ trade prints │   │ outputs ORDER    │   │ notional /   │   │ only),       │
│ + modeled    │   │ INTENTS only     │   │ open orders /│   │ LiveVenue   │
│ book)        │   │                  │   │ OTR / fat-   │   │ (stub: raises)│
└──────────────┘   └──────────────────┘   │ finger /     │   └──────────────┘
       │                    │            │ kill switch  │          │
       ▼                    ▼            └──────────────┘          │
┌──────────────┐   ┌──────────────────────────────────┐           │
│ book.py      │   │ backtest.py                      │           │
│ L2 limit     │◀──│ event loop: feed → strategy →    │           │
│ order book   │   │ risk → latency-delay → engine;   │           │
│ (price-time  │   │ fills → strategy/risk; metrics   │           │
│ priority)    │   │ (PnL, Sharpe, drawdown, fill    │           │
└──────────────┘   │ rate, markouts, inventory)       │           │
       ▲           └──────────────────────────────────┘           │
       │                          │                              │
┌──────────────┐          ┌──────────────┐              ┌──────────────┐
│ matching.py  │          │ latency.py   │              │ audit.py     │
│ matching     │          │ one-way delay│              │ append-only  │
│ engine:      │          │ + lognormal  │              │ JSONL log of │
│ limit/market/│          │ jitter (ns), │              │ intents, risk│
│ IOC/FOK/     │          │ tick-to-trade│              │ decisions,   │
│ post-only,   │          │ tracker      │              │ fills; secret│
│ queue-aware  │          └──────────────┘              │ redaction    │
│ fills, self- │                                       └──────────────┘
│ trade block  │
└──────────────┘
```

Data flow per sim event:

1. `SyntheticL2Feed` (or `ReplayFeed`) emits a `FeedEvent` (quote-level
   update or trade print).
2. The backtester applies it to the `L2OrderBook` / `MatchingEngine`
   (trade prints fill our resting orders via a queue-ahead estimate).
3. The strategy receives a `MarketSnapshot` (now including top-N
   `bid_depth`/`ask_depth`) and, on its decision schedule, returns
   `OrderIntent`s (never touching the book directly).
4. `RiskGateway` checks each intent fail-closed (kill switch, sanity,
   duplicates, global + per-symbol rate, per-order and per-minute
   notional, open-order cap, order-to-trade ratio, fat-finger price
   sanity, position, daily loss). Decisions are appended to the audit log.
5. `LatencyModel.apply()` delays the order by one sampled one-way latency
   before `MatchingEngine.submit()` executes it.
6. Fills flow back to the strategy (position/cash) and the risk gateway
   (equity vs. daily loss limit, OTR accounting).

## What's new in v2

**Smarter strategies** (`hft/strategies.py`):
* `MultiLevelFlowStrategy` — short-horizon signal combining signed
  trade-flow imbalance with **multi-level book imbalance** (bid vs ask
  quantity summed over the top N depth levels), threshold-based
  long/short/flat with passive entries and aggressive exits.
* `AdverseSelectionMarketMaker` — extends the Avellaneda-Stoikov quoter:
  pauses quoting (cancels live quotes, emits nothing) when rolling
  midprice volatility exceeds `vol_pause_threshold`; widens the spread by
  `adverse_widen_factor` and shifts the reservation price when order-flow
  imbalance and microprice move against inventory.
* Inventory control — `inventory_target` (reservation price skews toward
  the target: `r = mid − γσ²T(q − target)`), opt-in `size_shrink` (quote
  size decays as inventory nears the cap). Hard one-sided quoting at
  `max_inventory` is preserved; the risk gateway enforces the cap too.
* `MarketSnapshot` now carries optional `bid_depth` / `ask_depth`
  (populated by the backtester from `book.depth(5)`).

**Tougher risk + security** (`hft/risk.py`, `hft/venue.py`, `hft/audit.py`):
* New pre-trade checks: per-symbol order rate, notional per rolling
  minute, max open orders (tracked via `note_order_closed`), an
  order-to-trade ratio guard (via `note_fill`, inactive until a minimum
  fill count), and a fat-finger check rejecting limit prices too far from
  the reference mid.
* `kill(reason)` trips the kill switch **and** returns the open order ids
  so a driver can cancel them (the gateway never touches the engine).
* `hft/audit.py` — append-only JSONL log of order intents, risk
  decisions, and fills, with secret/token/key redaction. A logging failure
  can never change a risk decision.
* `AlpacaPaperVenue` — `PAPER_ONLY` constant plus a runtime assertion in
  `_request()` refusing any non-paper endpoint (defense in depth on top
  of the constructor's `ValueError`); explicit-only credentials, never
  logged; no network at import/construction.

**Real market replay** (`hft/replay.py`, `hft/data/`, `hft/replay_run.py`):
* `ReplayFeed` implements the same interface as `SyntheticL2Feed`
  (iterates `FeedEvent`s, exposes `sim_seconds`) and plugs straight into
  `Backtest`.
* Fixture: **13,024 real Kraken XBTUSD trade prints**
  (`hft/data/btcusd-trades.jsonl`, ~1 MB), 2026-09-22 02:12:25Z →
  06:10:55Z UTC. One-time build-time snapshot; the simulator never
  fetches at runtime. Provenance in `hft/data/SOURCE.md`.
* Be explicit: this is **trade-print replay, NOT full L2 depth replay**.
  Print prices, sizes, aggressor tags, and inter-trade timing are real;
  every quote around them (spread, depth, queue position, cancellations)
  is synthesized by a seeded RNG. Deterministic for a fixed fixture +
  seed.

## How to run

From the repo root:

```bash
# full test suite (offline, deterministic): 123 tests
python3 -m unittest discover -s tests -p "test_hft_*.py"

# sample backtest, synthetic feed: seed 7, 30 sim-minutes, 5 bps taker, 250 us
python3 -m hft.sample_run --seed 7 --minutes 30 --taker-fee-bps 5 --latency-us 250

# sample backtest, real-trade replay feed (Kraken XBTUSD fixture)
python3 -m hft.replay_run --seed 7 --taker-fee-bps 5 --latency-us 250
```

Programmatic use:

```python
from hft.replay import ReplayFeed
from hft.strategies import AdverseSelectionMarketMaker
from hft.risk import RiskGateway, RiskLimits
from hft.audit import AuditLog
from hft.latency import LatencyModel, LatencyConfig
from hft.backtest import Backtest, BacktestConfig

feed = ReplayFeed("hft/data/btcusd-trades.jsonl", seed=7)
audit = AuditLog("/tmp/hft-audit.jsonl")
risk = RiskGateway(RiskLimits(), audit=audit)
bt = Backtest(feed, AdverseSelectionMarketMaker(), risk,
              BacktestConfig(taker_fee_bps=5.0),
              LatencyModel(LatencyConfig(one_way_ns=250_000, seed=7)))
result = bt.run()
print(result.metrics)
audit.close()
```

## Parameters

| Component | Key parameters |
|---|---|
| `SyntheticL2Feed` | `seed`, `sim_seconds`, `events_per_sec` (default 2000), `start_mid_ticks`, `tick_vol`, `trade_fraction`, `depth_levels` |
| `ReplayFeed` | `fixture_path`, `seed`, `levels` (modeled depth levels per side), `tick_size` |
| `AvellanedaStoikovMarketMaker` | `gamma`, `kappa`, `horizon`, `order_size`, `max_inventory`, `quote_interval_ns`, `vol_window`, `inventory_target`, `size_shrink` |
| `AdverseSelectionMarketMaker` | all of the above, plus `vol_pause_threshold`, `adverse_widen_factor`, `adverse_shift_ticks` |
| `MultiLevelFlowStrategy` | `window`, `depth_levels`, `entry_threshold`, `w_flow`, `w_book`, `max_position`, `order_size`, `decide_interval_ns` |
| `MicrostructureSignalStrategy` | `window`, `entry_threshold`, `w_ofi`, `w_mp`, `max_position`, `order_size`, `decide_interval_ns` |
| `RiskGateway` / `RiskLimits` | `max_order_notional`, `max_notional_per_minute`, `max_position`, `max_orders_per_sec`, `max_orders_per_sec_per_symbol`, `max_open_orders`, `max_order_to_trade_ratio`, `max_price_deviation_bps`, `daily_loss_limit`, `allow_shorts` |
| `LatencyModel` / `LatencyConfig` | `one_way_ns` (default 250 000 = 250 µs), `jitter_sigma` (lognormal), `seed` |
| `BacktestConfig` | `taker_fee_bps` (default 5.0), `maker_fee_bps` (default 0.0), `decide_interval_ns`, `equity_sample_every` |

Conventions: prices are integer **ticks** (`tick_size`, default $0.01);
quantities are integer units; timestamps are integer **nanoseconds**.
Sides: `BUY = 1`, `SELL = -1`. The replay runner uses `tick_size=1e-5`
with cent-tick prices and milli-BTC quantities so PnL prints in real USD.

Metrics collected: total PnL (marked to market, net of fees), per-sample
Sharpe (documented in code — samples are evenly spaced in *event count*),
max drawdown, fill rate, adverse selection via 1s/10s markouts of aggressive
fills, average absolute inventory, orders/sec, tick-to-trade latency stats.

## Alpaca paper venue

`hft.venue.AlpacaPaperVenue` routes orders to Alpaca's **paper trading**
endpoint only (stocks/ETFs):

* the live Alpaca endpoint (or any non-paper URL) is refused at
  construction, and `_request()` asserts the paper endpoint at runtime;
* API key/secret must be passed explicitly — never read from env/disk here,
  never logged;
* no network activity at import or construction; HTTPS (stdlib `urllib`)
  fires only when `submit`/`cancel` are called;
* `close()` drops the in-memory credential references.

It is a paper-trading adapter, not an HFT venue: Alpaca paper is a
simulated matching service over the public internet and cannot support
microsecond-scale strategies.

## Paper runner

`python3 -m hft.paper_run` connects the lab's signal strategy to Alpaca
**PAPER** via `AlpacaPaperVenue` + the v2 `RiskGateway` + the JSONL audit
log. It is a slow, signal-based poller (default: one decision every 60
seconds) — not an HFT quoting loop, which Alpaca paper could not support
(~200 requests/min, no L2 feed).

What it does
* polls recent minute bars from the Alpaca data API, feeds them to
  `MultiLevelFlowStrategy`, and routes the resulting intents through
  every v2 risk check *before* submission;
* caps the run at `--max-orders` (default 5) paper orders of at most
  `--max-notional` dollars each (default $25);
* logs every intent, risk decision, submission, error, and account
  snapshot to the JSONL audit log (keys are never logged);
* fails closed: missing env keys abort before any network; a data-fetch
  failure places no orders; a non-paper URL is refused at startup;
* Ctrl-C or a `--daily-loss` breach (default $50) cancels open paper
  orders via the venue and stops.

What it does NOT do
* It is not HFT and does not validate any strategy — the signal is the
  lab's demonstration plumbing, and nothing here claims an edge or
  profitability.
* Paper fills are simulated by Alpaca, not real executions.
* It cannot place live orders: the live endpoint is refused at
  construction and asserted again at request time.

Credentials (paper keys only, environment only — never files, chat, or
the repo): `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`.

```bash
# read-only account check (DEFAULT mode; places no orders)
APCA_API_KEY_ID=... APCA_API_SECRET_KEY=... python3 -m hft.paper_run --mode account

# signal loop, dry-run (default in trade mode: logs intents, submits nothing)
APCA_API_KEY_ID=... APCA_API_SECRET_KEY=... python3 -m hft.paper_run --mode trade --symbol SPY

# actually submit to Alpaca PAPER (max 5 orders, $25 each, risk-checked)
APCA_API_KEY_ID=... APCA_API_SECRET_KEY=... python3 -m hft.paper_run --mode trade --symbol SPY --dry-run=false
```

Audit log: `hft/paper-run-audit.jsonl` (override with `--audit-path`).

## Limits — read this before drawing conclusions

1. **Simulator, not a market.** Any PnL, Sharpe, or fill-rate number
   describes strategy behavior against *a feed*, not against a real
   market. The synthetic feed is a seeded random walk; the replay feed
   wraps real trade prints in a modeled book. Change the seed, the
   fixture, or the generator's parameters and the numbers change.
2. **Replay is trade-print replay, not market replay.** Real prints,
   sizes, aggressor tags, and timing are genuine; every quote around them
   — spread, depth, queue position, hidden liquidity, cancellations — is
   synthesized. Fill estimates against that modeled queue validate
   plumbing, not live fill rates or adverse selection.
3. **Not live HFT, and not close.** Real high-frequency trading requires
   exchange membership and clearing, colocated servers with kernel-bypass
   networking, direct L2 market-data feeds, microsecond time sync, and
   compliance-reviewed risk controls. `venue.LiveVenue` raises
   `NotImplementedError` on purpose — this package will never place a
   live order.
4. **Retail venues cannot do true HFT.** REST/web order entry with
   hundred-millisecond-plus round trips and no real L2 feed is structurally
   incapable of microsecond market making. The Alpaca paper adapter exists
   for paper order-routing experiments only.
5. **Simplifications in v2:** the market-data latency leg is assumed zero
   (only our actions are delayed); the queue-ahead fill model is a simple
   estimate, not a calibrated queue model; the synthetic feed has no
   informed flow, no latency arbitrageurs, and no regime changes;
   end-of-run inventory is marked to market, not liquidated; Sharpe is per
   event-sample, not annualized; the adverse-selection heuristics are
   uncalibrated.
6. **Nothing here is investment advice**, and no result from this package
   should be read as evidence a strategy would make money live. It is a
   tool for learning microstructure mechanics.
