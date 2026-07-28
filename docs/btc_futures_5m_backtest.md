# BTC 5m Backtest — harness, findings, and the data blocker

Companion to `docs/btc_futures_5m_playbook.md`. Covers the six **OHLCV-only**
strategies: S1, S2, S3, S5, S6, S9.

---

## Status: no real-data results yet

**The backtest has not been run on real BTC data.** This session's egress policy
denies every market-data host that was tried:

```
data.binance.vision      403   api.binance.com         403
api.bybit.com            403   data.alpaca.markets     403
api.exchange.coinbase.com 403  api.kraken.com          403
min-api.cryptocompare.com 403  query1.finance.yahoo.com 403
```

The repo has no cached bars either. Per `/root/.ccr/README.md`, a proxy 403 is an
organization policy denial to report, not to route around — so no numbers in this
document come from real BTC price history, and none should be read as evidence
that any strategy works.

**To get real results**, run one of these from a machine with market-data access
(or after allow-listing `data.binance.vision`):

```bash
# 6 months of 5m USD-M futures klines, cached to CSV
python -m backtest.run --source binance-vision --months 2026-01:2026-06 \
    --cache backtest/data/BTCUSDT-5m.csv \
    --split 0.6 --out backtest/results/report.md --json backtest/results/report.json

# or from a CSV you already have (ts/open/high/low/close/volume, any timestamp format)
python -m backtest.run --csv path/to/BTCUSDT-5m.csv --split 0.6 --out report.md

# the book as §0 specifies it: shared equity, one position at a time, regime routing
python -m backtest.run --csv bars.csv --portfolio --funnel
```

---

## What was built

| File | Role |
|---|---|
| `backtest/indicators.py` | ATR, EMA/SMA, RSI, ADX, Bollinger, Keltner, Donchian, anchored VWAP + σ bands, TTM momentum, fractals, rolling percentile — all causal |
| `backtest/data.py` | `Bars` container, CSV load/save, venue fetchers (binance-vision / binance / bybit) with caching |
| `backtest/engine.py` | Bar-by-bar engine: pending orders, scaled exits, trails, time stops, fees, slippage, sizing, leverage cap, circuit breakers |
| `backtest/strategies.py` | S1, S2, S3, S5, S6, S9 as pure decision engines |
| `backtest/metrics.py` | Expectancy in R, hit rate, profit factor, Sharpe/Sortino, max DD, MAE, exit-reason and regime breakdowns |
| `backtest/run.py` | CLI with walk-forward split, cost overrides, sensitivity flags, `--funnel` |
| `backtest/funnel.py` | Signal-funnel recorder — per-gate pass rates (see below) |
| `backtest/portfolio.py` | Regime-routing table, shared-equity portfolio mode, attribution |
| `backtest/synth.py` | Synthetic bar generator — **harness self-test only** |
| `tests/test_backtest.py` | 38 mechanical assertions (all passing) |

### Assumptions that bias results *against* the strategies

- **Pessimistic intrabar fills** — when one bar's range covers both the stop and a
  target, the stop is taken. Always.
- **Causality is tested, not assumed** — `tests/test_backtest.py` asserts that ATR,
  RSI and ADX at bar *t* are unchanged when future bars are appended, that a
  fractal is invisible until its right shoulder closes, and that the Donchian
  channel excludes the current bar.
- **Slippage always moves against the fill**, scales with ATR%, ×2 on stop exits
  (they fire when the book is thinnest), ×4 on bars ranging > 3× ATR.
- **Taker on entries and stops, maker on limit targets.** Fees are charged on both
  legs of every trade and reported as a share of gross wins.
- **Leverage cap skips, never resizes** — a setup whose ATR-derived notional
  breaches the cap is dropped.

---

## Findings from implementing and validating the spec

These came out of building the harness. The first two are arithmetic and hold
regardless of what data you feed in. The third is a measured funnel on synthetic
bars and should be re-measured on real data.

### 1. S9's range-width filter was impossible — corrected

The playbook specified a 20-bar Donchian range of `0.5–3 × ATR(14)`. A 20-bar range
cannot be that narrow: for a random walk the expected *n*-bar range is ≈ `1.6 σ √n`,
and `ATR(14) ≈ 1.13 σ`, so a 20-bar Donchian sits near **6.4 × ATR** by
construction. Measured distribution:

```
p5   p25   p50   p75   p95
3.74 4.96  6.09  7.55  10.21     (x ATR14)
old window 0.5-3.0 captured 0.8% of bars -> S9 took 0 trades
```

Corrected to `3–8 × ATR` in both the playbook and the code; S9 then produced 48
trades over the same sample. Theory (6.4) and measurement (6.09) agree, so this is
not a synthetic-data artifact.

### 2. S1's stop had no floor, making it unwinnable near the VWAP anchor

Anchored-VWAP σ is ≈ 0 for the first hour after the 00:00 UTC re-anchor. The
σ-band stop therefore landed **8 bps** from entry — narrower than the 9 bps
round-trip fee. The first validation run showed −1.94R and −2.02R losses on a
strategy whose stop is supposed to define 1R: fees alone were ~1R.

Fixed by enforcing the playbook's own §0 rule in the engine (below) and adding a
"≥ 24 bars since anchor" requirement to the spec.

### 3. The §0 edge gate is the binding constraint on the whole book

§0 said "never take a setup whose target is < 3× round-trip cost" but nothing
enforced it. Implemented as a universal pre-trade check, it rejects most signals:

| Strategy | setups | rejected by edge gate | survived |
|---|---|---|---|
| S1 | 2 | 2 | **0** |
| S2 | 74 | 37 | 37 |
| S3 | 13 | 9 | 4 |
| S5 | 76 | 64 | 12 |
| S6 | 47 | 44 | 3 |
| S9 | 131 | 83 | 48 |

At 4.5 bps taker and ~0.15% ATR a round trip costs ≈ 12 bps, so TP1 must be ≥ 36
bps away. Most fade and pullback setups on a 5m chart simply aren't that big. The
honest reading: **these strategies are cost-constrained before they are
signal-constrained.** Before optimising entries, the desk should establish which
fee tier and which entry style (maker vs taker) it can actually achieve — that
choice determines whether half this book is viable at all.

Sensitivity to the gate (synthetic bars, 180 days — shape only, ignore levels):

```
min_edge   s2 trades   s5 trades   s6 trades   s9 trades
3.0 (spec)    37          12           3          48
1.5           61          23          13          96
0.0           74          60          38         120
```

Expectancy degrades monotonically as the gate loosens, which is what a working
cost model should do.

### 4. S1 and S6 are over-conjunctive as specified

S1 requires six conditions on one bar. Measured pass rates over 51,440 bars:
`ADX<20` 28%, `ADX flat` 52%, `ATR%<0.30%` 89%, `volume≥1.5×` 15%, `2σ pierce` 6.6%,
`RSI(2) extreme` 23% — joint occurrences: **10**. Roughly what independence
predicts, i.e. the conjunction is simply too deep to produce a tradeable sample.

S6's funnel was `ribbon aligned 12,605 → ADX 6,195 → fresh leg 5,525 → pullback ≤ 8
bars 3,190 → Fib 38–62% 552 → EMA21–55 zone 240 → low-volume pullback 60`. Note
the 552 → 240 step: the Fib retracement zone and the EMA21–55 zone are two
independent definitions of "the pullback area" and they only agree 43% of the
time. Requiring both is probably a mistake — pick one.

**These two were not retuned.** Loosening entry filters against synthetic data
would be fitting to noise. They are flagged for the real-data run.

### 5. Two spec rules were stated in the playbook but missing from the code

Both are now implemented, and both cost signals:

- **S1 — "≥ 24 bars since the VWAP re-anchor."** Added after finding 2. S1 still
  produces **zero** trades: the six-way conjunction leaves ~10 candidate bars per
  51k, the limit order misses most of them, and the §0 edge gate rejects the rest.
  **As specified, S1 is not tradeable.** It needs to be re-specified, not tuned.
- **S9 — "the range must be ≥ 20 bars old."** Enforcing it cut S9 from 48 trades
  to **12** on the same sample, so S9's sample size is now marginal too.

The first formulation of the range-age test compared the Donchian channel to
itself 20 bars earlier. That is wrong: those two windows are disjoint, so for a
random walk they differ by roughly the range itself — it passed 0.5% of break
events and took S9 to zero trades. The correct test asks whether the **preceding**
20 bars also sat inside the channel (a range that has contained price for 40 bars,
not 20), which passes ~20% of breaks:

```
tolerance   disjoint-Donchian (wrong)   prior-20-inside-channel (used)
0.00 ATR              0 / 11,976                1,878 / 11,976
0.25 ATR             62                         2,342
0.50 ATR            238                         2,854
```

---

## Harness validation run (synthetic — NOT a result)

Included only to show the machinery works end to end. The generator is a
GARCH-with-jumps random process; any P&L below is luck.

```
SYNTH-BTC 5m | 51,840 bars | 180 days
strategy trades hit_rate expectancy_r total_r  return_pct max_dd_pct profit_factor
s1       0      -        -            -        -          -          -
s2       37     0.7027   0.7237       26.78    9.74       -1.42      2.488
s3       4      0.0      -1.5849      -6.34    -2.20      -2.20      0.0
s5       12     0.5833   0.1404       1.68     0.57       -1.29      1.239
s6       3      0.3333   -0.0907      -0.27    -0.10      -0.54      0.9
s9       12     0.3333   -0.4243      -5.09    -1.79      -2.25      0.543
```

Do not read across this table. Every strategy is below the 300-trade minimum the
playbook sets, on data with no microstructure in it.

The column that *is* informative is `trades`. Only S2 generates a workable sample
once every stated rule is enforced; S1 generates none at all, and S3, S5, S6 and
S9 are in single or low double digits over six months. Signal frequency is a
property of the specification, not of the price series, so expect the same shape
on real data: **most of this book is too selective to be measurable**, let alone
profitable, and the specs need widening before the numbers mean anything.

```bash
python -m tests.test_backtest     # 38 mechanical checks, all passing
python -m backtest.run --synth 180
```

---

### 6. §0's routing table made S3 unreachable — corrected

Running the six strategies as six independent backtests is not what the playbook
describes: §0 specifies one shared equity, one position at a time, and one
portfolio-level circuit breaker. Portfolio mode (`--portfolio`) implements that,
and running it surfaced a third arithmetic-class defect.

The original routing table armed **S3 only in the HIGH bucket**. Measured, every
S3 signal fires in LOW or NORMAL:

```
strategy   regime at entry (standalone)          armed by original §0 table
s3         LOW 2, NORMAL 2                       HIGH          -> 0 trades, dead code
s5         NORMAL 5, HIGH 4, EXTREME 3           NORMAL        -> 5 of 12 survive
s2         HIGH 20, NORMAL 12, EXTREME 4, LOW 1  HIGH          -> 25 of 37 survive
```

The cause is definitional rather than statistical: **ATR(14) is a trailing
classifier**, and a squeeze breakout fires while the average still reflects the
compressed bars it is escaping. A strategy that trades a *transition* can never
be armed by a gate that measures the regime it is transitioning into. The table
also contradicted the strategies' own "optimal regime" lines — S3's section says
"transition from LOW to HIGH".

Corrected in both the playbook and `backtest/portfolio.py`, with each bucket now
following the strategies' own regime sections and intra-bucket priority set by
scarcity and time-criticality, never by observed P&L. `tests/test_backtest.py`
now asserts that every strategy is armed in at least one regime it actually
signals in — the regression that catches this whole class of bug.

### 7. "One position at a time" costs almost nothing — routing is what binds

Decomposing the two portfolio constraints on the same sample:

```
                                        trades
six independent runs (own equity each)     68
portfolio, contention only (--no-routing)  68     <- one-at-a-time costs 0
portfolio, with regime routing             63     <- routing costs 5
```

Contention is free because signal frequency is so low that these strategies
almost never want the book at the same time. That is worth knowing before anyone
spends effort on allocation logic: at current selectivity the correlation problem
§0 worries about does not bind, and the regime table is the only part of the
portfolio layer doing real work. If the specs are widened (findings 3–5), expect
this to invert.

## The funnel diagnostic

Since trade count is the problem, the harness reports **where the signals die**:

```bash
python -m backtest.run --csv bars.csv --funnel
```

Every entry condition is a named gate. Each row counts evaluations that reached
that gate *and* passed it, so the drop to the next row is exactly what the gate
costs. This is the tool for deciding what to widen — it replaces guessing.

```
s1 funnel  (4 setups emitted)
  gate                  reached    passed     pass%    killed
  adx<20_and_flat       51,531     9,306     18.06%   42,225   <-- biggest drop
  atr%<0.30              9,306     8,280     88.97%    1,026
  anchor_age>=24         8,280     7,345     88.71%      935
  vol>=1.5x              7,345       949     12.92%    6,396
  2sigma_pierce_reject     949        40      4.21%      909
  rsi2_extreme              40         4     10.00%       36
```

S1's problem is now precisely located: the killer is not any single gate but the
product of three independent ones — `volume ≥ 1.5×` (12.9%), `2σ pierce` (4.2%)
and `RSI(2) extreme` (10%). Four setups survive 51,531 bars, and the edge gate
takes all four. Any fix has to relax that product, not the ADX filter that
*looks* like the biggest drop.

S6 is the same story in a different place: `Fib 38–62%` passes 16.4% and
`EMA21–55 zone` a further 44.8%. As noted in finding 4 these are two definitions
of the same thing, and requiring both costs ~93% of surviving setups.

S6 emits 47 setups and trades 3; S9 emits 24 and trades 12. The gap in both cases
is the §0 edge gate, which confirms finding 3 from the other direction.

Notes on reading it: counts are per *evaluation*, not per bar — strategies that
test a long branch and then a short branch increment shared gate names twice (this
is why S9's `broke_out` row shows more `reached` than the row above it). That is
the right denominator for "how selective is this condition".

`tests/test_backtest.py` asserts the instrumentation is observation-only: every
strategy produces byte-identical trades with and without `--funnel`.

## What to do when real data is available

1. Run `--funnel` **first**, before looking at any P&L. It tells you which gates
   to widen; fixing frequency is a precondition for the statistics meaning
   anything.
2. Run with `--split 0.6` and report in-sample and out-of-sample separately.
3. Check trade counts first. Anything under ~300 out-of-sample trades is not
   evidence; S1 and S6 will likely need their conjunctions loosened before they
   generate a sample at all — do that on in-sample data only.
4. Run `--entry next_open` as a friction check. A strategy whose edge disappears
   when market entries move from the signal close to the next open is measuring
   its own fill assumption, not an edge.
5. Sweep `--taker` across the fee tiers actually available to the desk. Given
   finding 3, this matters more than any indicator parameter.
6. Only then look at expectancy, and only regime-conditionally — the `by_regime`
   block in the JSON output exists for this.
