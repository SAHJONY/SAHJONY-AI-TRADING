# BTC 5m Backtest — harness, findings, and the data blocker

Companion to `docs/btc_futures_5m_playbook.md`. Covers the **14 OHLCV-only**
strategies: the playbook's S1, S2, S3, S5, S6, S9 plus candidates S11–S18.

---

## Widening the specs — on real 5m data, on frequency only

With real 5m BTC available, the funnel finally ran on the data the specification
was written for. Two results, one of which corrected an earlier inference.

### S1: the spec as written is unmeasurable

```
gate                      reached   passed   pass%
sigma_band_pierce_reject   2,794      162     5.80%   <-- biggest drop
adx<max_and_flat             162       11     6.79%
vol>=mult                    162       53    32.72%
rsi2_extreme                 162       50    30.86%
confluence_score>=min        162        1     0.62%
```

`ADX < 20 and flat` passes **6.79%** on real 5m BTC against 28% on synthetic
bars — BTC trends, so "no trend" is rarer than the specification assumed. That is
a fact only real data could supply.

Requiring all five context conditions leaves 0.62% of pierces, ≈ **34 trades a
year** — so the playbook's own 300-trade out-of-sample floor would need about
**nine years** of data. A strategy that cannot be measured is not a strategy.
Default `min_score` is now **0.8** (four of five), ≈ **305 trades a year**:
judgeable in roughly one.

**Chosen on frequency alone. P&L was deliberately not consulted**, and the
promotion gate still has to rule on whether it works at all — measurability is a
precondition for that verdict, not a substitute for it.

### S6: an earlier inference did not reproduce

Synthetic bars suggested the redundant Fib-AND-EMA pullback zone was S6's binding
gate (3 → 9 trades when relaxed). On real 5m BTC, `zone_mode` makes **no
difference at all**:

```
zone_mode=both  1 trade      zone_mode=fib  1 trade      zone_mode=ema  1 trade
```

Only four setups reach that gate in eleven days, so this is inconclusive rather
than refuted — but it is not evidence, and the default is therefore unchanged.
The synthetic-data recommendation was wrong to act on, which is exactly why the
rule was to widen on real data.

S9 is left alone too: each of its gates carries a distinct meaning (an
unconfirmed break, an RSI extreme, a range that has actually held), and the
funnel gives no basis for choosing one to drop.

## Worldwide data, and 65 years of S&P 500

IMF, OECD, BIS, the Bank of England, the Bundesbank and JPX are all blocked
alongside the US APIs. But the **Rdatasets mirror on GitHub raw is reachable** —
3,648 curated real datasets, 74 of them financial with ≥250 rows:

| Dataset | Rows | What |
|---|---|---|
| `gt/sp500` | **16,607** | **Daily S&P 500 OHLCV, 1950–2015** |
| `AER/DJIA8012` | 8,610 | Dow Jones, 1980–2012 (close only) |
| `datasets/EuStockMarkets` | 1,860 | **DAX, SMI, CAC, FTSE** (close only) |
| `evir/bmw`, `evir/siemens` | 6,146 | Daily log returns, German equities |
| `stevedata/ukg_eeri` | 8,340 | UK effective exchange rate, 1990– |
| `tsibbledata/gafa_stock` | 5,032 | Google/Amazon/Facebook/Apple prices |

```bash
python -m backtest.run --source sp500-65y --split 0.6
```

Only `gt/sp500` carries full OHLCV, so it is the one wired in — the others are
close-only, and without intrabar high/low the engine's stop and target fills
would be fiction. **65 years is the deepest sample available here**, spanning the
1962 break, the 1973–74 bear, Black Monday, the dot-com unwind and 2008, and it
is the first sample large enough to clear the 300-trade floor.

### S14: the cleanest overfit in the whole exercise

```
                 trades  hit_rate  expectancy_r  return_%  Sharpe
in-sample  (60%)   452     0.573      0.484       113.2     1.58
out-of-sample      357     0.431     -0.087       -10.6    -0.36
```

Sharpe 1.58 and +113% in-sample on 452 trades — a sample size that *looks*
authoritative — inverts to Sharpe −0.36 out-of-sample on 357 more. Nothing was
tuned; this is the default parameter set. Trade count alone never establishes
anything.

### Nothing is positive in both halves

```
       in-sample expectancy_r    out-of-sample expectancy_r
s11         +0.029                      -0.154
s12         -0.059                      +0.182
s13         -0.035                      +0.166
s14         +0.484                      -0.087
```

Every strategy flips sign. S12 and S13 are positive out-of-sample but *negative*
in-sample, which is the same coin landing the other way up — not evidence. And
buy-and-hold returned +1,948% then +493%, at Sharpe 0.77 and 0.56; nothing here
comes close.

Sixty-five years of the most-studied equity series in existence, fourteen
strategies, and **no survivor.** That is the expected result — it is what the
literature says happens to simple technical rules on liquid indices — and the
harness reproducing it is the strongest evidence that the harness is honest.

## Wall Street reference data — and the gate rejecting a real candidate

Bloomberg Terminal is a licensed product whose API needs an authenticated
terminal session; there is no path to it here or from the desk without a
subscription. Every free institutional API is also blocked by this egress policy
— **SEC EDGAR, FRED, World Bank, ECB, Nasdaq Data Link and Alpha Vantage all
fail**. Only GitHub public repos and package registries are reachable.

Package registries turn out to be enough. Serious econometrics libraries *bundle*
genuine market data offline, no API and no key:

| Source | Span | Data |
|---|---|---|
| `arch.data.default` | **1919–2018** | Moody's AAA / BAA corporate credit spreads |
| `arch.data.wti` | 1986–2019 | WTI crude, 8,611 sessions |
| `arch.data.sp500` / `nasdaq` | 1999–2018 | Real daily OHLCV, 5,031 sessions each |
| `arch.data.frenchdata` | monthly | Fama–French factors (Mkt-RF, SMB, HML, RF) |
| `statsmodels` macrodata | 1959–2009 | US GDP, CPI, unemployment, T-bill |

These packages are **not** in `requirements.txt`. `arch` drags in scipy and
statsmodels, and Vercel installs the root requirements verbatim into the
`api/*.py` serverless bundle — with `pyarrow` alongside them the bundle reached
826 MB against a 500 MB ceiling and the deployment failed. They live in
`requirements-backtest.txt` instead:

```bash
pip install -r requirements.txt -r requirements-backtest.txt
```

`backtest/data.py` imports both lazily, so without them the affected sources
raise `DataUnavailable` naming the file to install, and everything else works.

```bash
python -m backtest.run    --source sp500-1d --split 0.6
python -m backtest.improve --source sp500-1d --strategy s12
```

S&P 500 1999–2018 is **the largest multi-regime sample available here** — the
dot-com unwind, the 2008 crisis and the 2010s bull, including a first half where
buy-and-hold returned 2.4% over twelve years with a 57% drawdown.

### One candidate looked real

S12 (Connors RSI(2)) was positive in *both* halves of a walk-forward split, which
nothing else managed:

```
                trades  hit_rate  expectancy_r  Sharpe
in-sample  (60%)   48     0.667       0.134      0.62
out-of-sample      33     0.727       0.175      0.68
buy & hold OOS      —         —           —      0.80
```

Consistent hit rate across a regime change is what a genuine mean-reversion edge
looks like. So it went through the promotion gate.

### The gate rejected it

```
PASS  oos_trades        56        (>= 30)
PASS  oos_expectancy_r  0.0477    (> 0)
FAIL  pbo               0.5857    (<= 0.35)
FAIL  deflated_sharpe   0.0017    (>= 0.95)
PASS  param_stability   0.7654    (>= 0.6)
PASS  param_drift       0.3536    (<= 0.5)
PASS  positive_folds    1.000     (>= 0.6)

VERDICT: REJECT
```

Five checks of seven pass. It fails the two that decide the question:

- **PBO 0.59** — pick the in-sample winner and it lands *below median*
  out-of-sample 59% of the time. Worse than a coin flip: the search is selecting
  noise, not skill.
- **Deflated Sharpe 0.0017** — after charging for 18 trials, the observed
  per-trade Sharpe of 0.080 sits far under the 0.489 a best-of-18 search would
  produce by luck alone.

The fold-by-fold expectancy also decays, 0.122 → 0.040 → 0.026, and the whole
out-of-sample record is 2.67R across 56 trades — negligible before it is
significant.

**This is the machinery earning its keep.** A strategy that is positive in every
fold, stable in its parameters and consistent across a regime change is still
rejected, because the statistics cannot distinguish it from luck. Anyone reading
only the first table would have promoted it.

## Real 5-minute BTC data — the spec's own instrument and timeframe

```bash
python -m backtest.run --source public-btc-5m        # 3,106 real 5m BTC/USDT bars
```

Found by cloning a public repo (git clone works for arbitrary public repos here,
and `raw.githubusercontent.com` serves the file directly over HTTPS). Real prices
($83,940–$94,034), real traded volume, zero timestamp gaps.

**It is short — ~11 days, about 9 tradeable after warmup.** That is nowhere near
the 300 out-of-sample trades the promotion gate wants, so it cannot say whether
anything is profitable. What it *can* do is check that 5m logic behaves as
designed, and it produced two results worth having.

### The regime classifier was right

§0's volatility buckets were written from priors, before any data existed. On
real 5m BTC:

```
ATR% percentiles      p5 0.079%   p25 0.126%   p50 0.172%   p75 0.237%   p95 0.333%

spec bucket                    share of real bars
LOW      < 0.12%                    22.2%
NORMAL   0.12% – 0.30%              68.1%
HIGH     0.30% – 0.60%               9.7%
EXTREME  ≥ 0.60%                     0.0%
```

The bulk lands in NORMAL with tails either side — which is what a regime
classifier should do. (EXTREME is absent because this is a calm eleven-day
window, not because the bucket is wrong.)

### The over-selectivity finding reproduces on real data

Previously this was inferred from synthetic bars. On real 5m BTC over ~9
tradeable days:

```
playbook strategies   S1 1   S2 2   S3 1   S5 3   S6 1   S9 1     trades
new candidates        S11 47  S12 24  S13 22  S14 24  S16 17  S17 32  S18 57
```

The original six fire **1–3 times in nine days** — roughly 40–120 trades a year,
against a gate that wants 300 out-of-sample. That is **3–8 years of data per
strategy** before any of them could be judged. The S11–S18 candidates, written
deliberately shallower, run at ~700–2,300 trades a year and could be judged in
months.

Every strategy lost money over this window, but on 1–57 trades that is noise, not
a finding. The honest statement is that the sample is too small, which is itself
the point: **the specification's frequency problem is now confirmed on real
market data.**

---

## Real hourly data — and the edge did not survive

A public dataset **is** reachable behind this egress policy:
`raw.githubusercontent.com` serves arbitrary public repositories (200), as does
PyPI, while every exchange API and Yahoo Finance are denied. That gives
**46,237 clean hourly BTC bars, 2011–2017, with real traded volume**:

```bash
python -m backtest.run --source public-btc-1h --split 0.6
```

**These are hourly bars, not the 5-minute specification.** That invalidates the
session strategies outright (S2's "opening range = first 3 bars" becomes three
*hours*; S17's windows are minute-based) and mis-scales every ATR% regime
threshold — median bar range here is 0.74%, which reads as EXTREME on gates
calibrated for 5m. Structural strategies (Donchian, RSI(2), %B, NR7, engulfing)
are the ones this can fairly speak to.

### What happened

S2 looked spectacular, and held up out-of-sample on default parameters with no
tuning:

```
                    trades  hit_rate  expectancy_r  return_%  max_DD_%  Sharpe
in-sample  (60%)      666     0.620      0.507       222.3     -10.75    4.35
out-of-sample (40%)   399     0.657      0.664       150.8      -2.45    5.99
buy & hold OOS          —         —          —      1265.9     -38.67    2.23
```

Two things stop that being a result:

**1. It loses to buy-and-hold by 8×.** +151% against +1,266% over the same
window. `public/evaluation.json`'s own primary criterion is "net-of-fees return
beats buy-and-hold BTC" — on this data S2 fails it. Better Sharpe and a far
smaller drawdown, but 2011–2017 was a once-in-history bull market and any
long-biased rule looks good in it.

**2. A Sharpe near 6 is a red flag, and the flag was right.** S2 enters with a
stop-market order, and the engine fills it *at the stop price* whenever the bar
trades through it. On hourly bars that gap through a level, that is an optimistic
fill. Raising base slippage from 0.8 bps to 10 bps:

```
slippage    trades   expectancy_r   return_%   Sharpe
0.8 bps       399        0.664       150.84     5.99
 10 bps        60        0.202         4.27     0.88
```

Not degradation — **collapse**. Trade count falls 85% because the §0 edge gate
starts rejecting setups whose targets never really cleared costs, and what
survives is Sharpe 0.88 on 60 trades, below the 300-trade significance floor.
The apparent edge was a fill assumption.

Every other strategy lost money on real data at default settings, several
catastrophically (S15 −96.7%, S11 −88.6%).

### What this establishes

The harness works on real market data, and the first thing it did with real data
was destroy an apparent edge. That is the machinery behaving correctly. It does
**not** validate any strategy at 5 minutes — that still needs 5m bars.

---

## Status: no 5-minute real-data results yet

**The backtest has not been run on real BTC data.** This session's egress policy
denies every market-data host that was tried:

```
data.binance.vision      403   api.binance.com          403
api.bybit.com            403   data.alpaca.markets      403
api.exchange.coinbase.com 403  api.kraken.com           403
min-api.cryptocompare.com 403  query1.finance.yahoo.com 403
mcp.financialdatasets.ai 403   api.financialdatasets.ai 403
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

## Robinhood as a data source — what it can and cannot do

Asked to source the backtest from Robinhood, the answer is a capability limit,
not an outage:

**Robinhood's crypto trading API has no candles.** It serves
`/api/v1/crypto/marketdata/best_bid_ask/` — one live quote — and nothing else.
`utils/brokers/robinhood_crypto.py` says so in its own docstring and backfills
*daily* closes from CoinGecko for the council. **No amount of network access or
credentials turns that into 5-minute history.** (Separately, this sandbox cannot
reach `trading.robinhood.com` or `api.coingecko.com` either, and has no RH
credentials — but that is the lesser of the two blockers.)

What Robinhood *can* do is accumulate history going forward, so
`utils/bar_recorder.py` folds the quotes the desk already fetches into OHLCV bars
and stores them:

```bash
BAR_RECORDER=true          # BAR_INTERVAL_MINUTES is derived, leave it unset
```

The harness reads that database directly — no export step, no adapter:

```bash
python -m backtest.run --desk-db data/trading.db --desk-coverage   # is it usable yet?
python -m backtest.run --desk-db data/trading.db --desk-symbol BTC/USD
python -m backtest.improve --desk-db data/trading.db --strategy s12
```

`export_csv()` → `--csv` still works and is round-trip verified; `--desk-db` is
the same data without the intermediate file.

**Two limitations that change what those bars mean:**

1. **Volume is a tick count, not traded volume.** `best_bid_ask` carries no size.
   Strategies gated on volume — S2's `vol_mult`, S15's volume spike, S1's
   capitulation filter — are measuring *sampling frequency* on these bars, not
   participation. Their volume conditions are not meaningful here. `--desk-db`
   prints this warning on every run.
2. **Bar resolution is bounded by the poll cadence** — and more sharply than the
   word "resolution" suggests. A bar's high can only exceed its low if **two or
   more** quotes landed inside it. Measured from `public/status.json` on `master`
   (cycles 432→456), the live desk's gap between cycles is **12.6 min minimum,
   16.1 min median, 153.7 min maximum**. At that cadence a 5-minute bucket
   receives one quote or none, so every 5m bar it produces has
   `open == high == low == close`: a real price, but a **fabricated range**. ATR,
   wicks, and intrabar stop tests computed on such bars are not conservative
   approximations — they are fiction.

**So the bar size is derived from the cadence, not chosen.** `config.bar_intervals_for(cycle_minutes)`
returns two standard sizes off the ladder `1, 5, 15, 30, 60, 120, 240, 1440`:

| | rule | at `CYCLE_MINUTES=15` | at `CYCLE_MINUTES=5` |
|---|---|---|---|
| **native** | smallest bar the cadence fills at all (≥1 quote) | 15m | 5m |
| **usable** | smallest bar that gets ≥3 quotes, so its high/low are observed | **60m** | **15m** |

Both are written from the same quote stream; the coarse one is what backtests
should read. The consequence worth stating plainly: **the desk records a 5-minute
bar when, and only when, it polls every 5 minutes.** Set `CYCLE_MINUTES=5` and
`(5, 15)` follows with no code change — the 5-minute spec starts recording the
moment the poll is fast enough to justify it, and not one cycle before.

The readers enforce the same rule. `load_desk_db()` defaults to `min_ticks=2` and
**refuses** a series whose bars are all single-tick, naming the cadence as the
cause rather than silently handing back range-free bars; with no interval named
it selects the series with the most bars that have a *measured* range, since
ranking by row count would reliably pick the worst data available.
`--desk-coverage` reports `single_tick_pct` per series and prints the correct
intervals for the configured cadence, so "is there enough history yet?" and "am I
recording the right thing?" both have numeric answers.

And the arithmetic worth doing before relying on this. The harness needs ~400
bars of warmup before its first signal, and the promotion gate wants 300
out-of-sample trades:

| cadence | usable series | bars/day | 400-bar warmup |
|---|---|---|---|
| `CYCLE_MINUTES=15` (today) | 60m | 24 | ~17 days |
| `CYCLE_MINUTES=5` | 15m | 96 | ~4 days |
| `CYCLE_MINUTES=1` | 5m | 288 | ~1.4 days |

Warmup is the easy part; 300 out-of-sample *trades* is the binding one, and at 24
bars a day that is years away. Speeding the poll up is therefore the lever that
matters — the desk runs on a GitHub Actions loop (`.github/workflows/desk.yml`),
so `CYCLE_MINUTES` is a repository variable, not a code change. This path is
still the right thing to start now precisely because it takes so long; it is not
a substitute for downloading history from a venue that publishes candles.

## What was built

| File | Role |
|---|---|
| `backtest/indicators.py` | ATR, EMA/SMA, RSI, ADX, Bollinger, Keltner, Donchian, anchored VWAP + σ bands, TTM momentum, fractals, rolling percentile — all causal |
| `backtest/data.py` | `Bars` container, CSV load/save, venue fetchers (binance-vision / binance / bybit) with caching |
| `backtest/engine.py` | Bar-by-bar engine: pending orders, scaled exits, trails, time stops, fees, slippage, sizing, leverage cap, circuit breakers |
| `backtest/strategies.py` | S1, S2, S3, S5, S6, S9 as pure decision engines |
| `backtest/strategies_extra.py` | S11–S18 candidate strategies (see roster below) |
| `backtest/metrics.py` | Expectancy in R, hit rate, profit factor, Sharpe/Sortino, max DD, MAE, exit-reason and regime breakdowns |
| `backtest/run.py` | CLI with walk-forward split, cost overrides, sensitivity flags, `--funnel` |
| `backtest/funnel.py` | Signal-funnel recorder — per-gate pass rates (see below) |
| `backtest/portfolio.py` | Regime-routing table, shared-equity portfolio mode, attribution |
| `backtest/optimize.py` | Walk-forward search, PBO/CSCV, deflated Sharpe, stability, promotion gate |
| `backtest/improve.py` | CLI for the self-improvement loop; emits a reviewable JSON proposal |
| `backtest/synth.py` | Synthetic bar generator — **harness self-test only** |
| `tests/test_backtest.py` | 53 mechanical assertions (all passing) |

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
python -m tests.test_backtest     # 53 mechanical checks, all passing
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

## The candidate roster (S11–S18)

Eight additional strategies were added as **candidates**, bringing the
implementable book to 14. None is claimed to win: the promotion gate decides
that on out-of-sample evidence, and nothing here has seen real BTC data.

| # | Strategy | Class | Why it earns a slot |
|---|---|---|---|
| S11 | Donchian Turtle Breakout | Trend | The oldest systematic trend rule; the honest baseline every fancier trend strategy should beat |
| S12 | Connors RSI(2) Pullback | Mean reversion + trend filter | Published and widely replicated — a near-null model for "does reversion work here at all" |
| S13 | Bollinger %B Reversion | Mean reversion | Same family as S1 but trend-filtered, so it never fades a trend day |
| S14 | NR7 Range Expansion | Volatility expansion | S3's premise measured on one bar instead of a band relationship, so it fires far more often |
| S15 | Volume-Spike Continuation | Momentum | Trades participation rather than fading it; risk defined by the signal bar |
| S16 | Engulfing at Extreme | Price action | No indicators — a one-bar shift in control at a channel extreme |
| S17 | Session-Window Momentum | Seasonality | Makes the "crypto has sessions" claim testable, with the window as a searchable parameter rather than folklore |
| S18 | Dual-Timeframe Pullback | Trend + timing | 30m trend from aggregated 5m bars, causal by construction |

**These are deliberately cheaper in conditions than S1–S9.** The funnel work
showed the original book's problem was not weak signals but conjunctions so deep
nothing fired. Each of these uses 3–5 conditions, and it shows in the sample
sizes — 198 to 674 trades over 180 days where S1 produced zero:

```
s11 626   s12 379   s13 333   s14 390
s15 198   s16 443   s17 464   s18 674
```

**Every one loses money on synthetic data, and that is the correct result.** The
generator is a random process; after real fees, any strategy must have negative
expectancy on it. A candidate that "won" here would indicate a bug in the cost
model, not an edge. This is the sanity check the roster exists to pass before it
ever sees real bars.

All eight are registered, routed by regime, and have search spaces in
`backtest/improve.py`, so `python -m backtest.improve --strategy s11` runs the
full walk-forward + PBO + deflated-Sharpe + promotion gate against them.

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

## The self-improvement layer

Automated parameter search is easy to write and almost always produces a
beautiful, worthless equity curve. Everything expensive in `backtest/optimize.py`
exists to make the search **refuse** results, not to find them.

```bash
python -m backtest.improve --csv bars.csv --strategy s6 --folds 4 --out proposals/
```

| Control | What it answers | Gate |
|---|---|---|
| Walk-forward | Do parameters chosen on one window survive the next? | in-sample is never reported |
| **PBO** (CSCV) | If I pick the in-sample winner, how often is it below median out-of-sample? | ≤ 0.35 |
| **Deflated Sharpe** | Is this Sharpe better than the best of N lucky trials? | ≥ 0.95 |
| **Parameter stability** | Is the optimum a plateau or a spike in a noise surface? | neighbours ≥ 60% of winner |
| **Parameter drift** | Do the chosen values move every fold? | cross-fold CV ≤ 0.50 |
| Trade floor | Is there enough evidence to say anything? | ≥ 300 OOS trades |

**The gate defaults to REJECT and requires every check to pass.** It emits a JSON
proposal; it never writes to a live configuration. A system that silently
re-tunes itself in production is not self-improving, it is unsupervised — and
under this repo's safety directives that is a decision for a human, not a loop.

### Validating the guards in both directions

A gate that always rejects is as useless as one that always promotes, so both
behaviours are tested:

```
PBO ~0.0    when one parameter set genuinely dominates every block
PBO ~0.26   on pure noise — the search learned nothing
DSR 0.9914 -> 0.9791  same Sharpe, 1 trial vs 5,000 trials
stability >= 0.9 on a plateau, <= 0.2 on a spike
```

Run end-to-end on synthetic (edge-free by construction) data, the loop **rejects
S6 on all seven checks**, with PBO = 0.63. That is the correct answer on a random
process, and it is the strongest evidence available here that the machinery
works.

### Strategy upgrades this enabled

All six strategies are now parameterised — every tunable number lives in
`PARAMS`, read through `self.p`. **Constructing a strategy with no arguments
reproduces the playbook exactly**, verified trade-by-trade across 18 runs, so
parameterisation added search surface without changing a single documented rule.

Two structural upgrades came from the funnel findings rather than from any P&L:

- **S1 — confluence score.** Six hard-ANDed conditions produced 4 setups in 51k
  bars. The band pierce stays mandatory (it defines the entry price); the five
  context conditions are scored, with `min_score` setting how many must agree.
  `min_score=1.0` is the original spec; relaxing it restored frequency
  (0 → 45 → 287 trades at 1.0 / 0.8 / 0.6).
- **S6 — `zone_mode`.** The Fib window and the EMA21–55 zone are two definitions
  of the same thing. `both` is the spec; `fib` and `ema` pick one (3 → 9 / 7
  trades).

Those trade counts are mechanism demonstrations on synthetic data. **Which
threshold is correct is exactly what the promotion gate exists to decide, on real
data.** Defaults remain the specification precisely so that no unvalidated value
becomes the new normal by accident.

## What to do when real data is available

1. Run `--funnel` **first**, before looking at any P&L. It tells you which gates
   to widen; fixing frequency is a precondition for the statistics meaning
   anything.
2. Then `python -m backtest.improve --strategy sN` per strategy, and believe the
   promotion gate rather than the equity curve. Expect most strategies to be
   rejected on the trade floor before any other check even applies.
3. Run with `--split 0.6` and report in-sample and out-of-sample separately.
4. Check trade counts first. Anything under ~300 out-of-sample trades is not
   evidence; S1 and S6 will likely need their conjunctions loosened before they
   generate a sample at all — do that on in-sample data only.
5. Run `--entry next_open` as a friction check. A strategy whose edge disappears
   when market entries move from the signal close to the next open is measuring
   its own fill assumption, not an edge.
6. Sweep `--taker` across the fee tiers actually available to the desk. Given
   finding 3, this matters more than any indicator parameter.
7. Only then look at expectancy, and only regime-conditionally — the `by_regime`
   block in the JSON output exists for this.
