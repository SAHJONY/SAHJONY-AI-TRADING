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
| `backtest/run.py` | CLI with walk-forward split, cost overrides, sensitivity flags |
| `backtest/synth.py` | Synthetic bar generator — **harness self-test only** |
| `tests/test_backtest.py` | 14 mechanical assertions (all passing) |

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
python -m tests.test_backtest     # 14 mechanical checks, all passing
python -m backtest.run --synth 180
```

---

## What to do when real data is available

1. Run with `--split 0.6` and report in-sample and out-of-sample separately.
2. Check trade counts first. Anything under ~300 out-of-sample trades is not
   evidence; S1 and S6 will likely need their conjunctions loosened before they
   generate a sample at all — do that on in-sample data only.
3. Run `--entry next_open` as a friction check. A strategy whose edge disappears
   when market entries move from the signal close to the next open is measuring
   its own fill assumption, not an edge.
4. Sweep `--taker` across the fee tiers actually available to the desk. Given
   finding 3, this matters more than any indicator parameter.
5. Only then look at expectancy, and only regime-conditionally — the `by_regime`
   block in the JSON output exists for this.
