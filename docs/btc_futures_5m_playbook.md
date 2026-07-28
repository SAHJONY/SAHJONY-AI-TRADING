# BTC Futures — 5-Minute Playbook (10 Strategies)

**Author role:** Senior Quantitative Trader / Risk Manager, crypto derivatives
**Instrument:** BTC perpetual & quarterly futures (CME `BTC`/`MBT`, or venue perps)
**Timeframe:** 5-minute bars, intraday only (no overnight carry unless stated)
**Status:** Research specification. **Not** wired into the autonomous loop. Paper /
backtest only until each strategy has out-of-sample evidence.

> Honesty note (house rule): these are transparent, public-domain estimators built
> from standard indicators and microstructure logic. None is a profit guarantee.
> Every parameter below is a *starting prior* to be walk-forward tested, not a
> tuned optimum. Assume any edge decays; re-fit quarterly.

---

## 0. Global execution & risk frame (applies to all 10)

Everything below assumes these constants. Strategy-level R:R numbers are stated
**net of** this friction, not gross.

| Item | Working assumption |
|---|---|
| Taker fee | 4.5 bps/side → **9 bps round trip** |
| Maker fee | 1–2 bps/side (rebate on some venues) |
| Slippage, calm tape | 0.5–1.5 bps on top-of-book size |
| Slippage, event tape (CPI/FOMC, liquidation cascade) | 5–25 bps, book can gap 50+ bps |
| Funding (perps) | ±0.01% / 8h typical, ±0.05–0.30% in squeezes — matters if held >1h |
| CME session gaps | Fri 22:00 UTC → Sun 23:00 UTC close; gap-fill logic in S10 |
| Minimum edge filter | **Never take a setup whose target is < 3× round-trip cost** |

⚠️ **That last row is the binding constraint, not a footnote.** At 4.5 bps taker
and ~0.15% ATR, a round trip costs ≈ 12 bps, so TP1 must be ≥ **~36 bps** away.
When the gate was implemented and run, it rejected the majority of signals from
every fade/pullback strategy here (S5 64 of 76, S6 44 of 47, S9 83 of 131, S1 both
candidates). The implication is structural: **at taker fees these 5m setups mostly
do not clear costs.** They need maker entries, a fee-tier/rebate venue, or wider
targets — see `docs/btc_futures_5m_backtest.md`.

**Position sizing (identical across all strategies):**

```
risk_$        = equity × risk_pct           # risk_pct = 0.25%–0.50% per trade
stop_distance = k × ATR(14, 5m)             # k defined per strategy
qty           = risk_$ / stop_distance      # in BTC
notional      = qty × price
CONSTRAINT: notional / equity ≤ 5×  (hard cap; 3× in ATR% > 0.45% regimes)
```

Leverage is an *output* of the stop distance, never an input. If the ATR-derived
size breaches the 5× cap, the trade is **skipped**, not resized upward.

**Portfolio-level circuit breakers:**
- Daily loss stop: **−2.0% of equity** → flat, no new entries until next UTC day.
- Consecutive-loss stop: 4 losers in one session → halve size for the rest of it.
- Max concurrent BTC exposure: 1 directional strategy at a time (they correlate to
  ~0.6–0.9 intraday); a second entry is allowed only if it is the *opposite*
  methodology class (e.g. one trend + one basis-RV) and total notional ≤ 5×.
- Never hold a directional 5m position through a scheduled macro print (CPI, NFP,
  FOMC). Flatten 3 bars (15 min) before, re-arm 3 bars after.

**Volatility regime classifier** (used by several strategies below):

```
ATRpct = ATR(14, 5m) / close
LOW      : ATRpct < 0.12%      → fade / mean-revert regime
NORMAL   : 0.12% ≤ ATRpct < 0.30%
HIGH     : 0.30% ≤ ATRpct < 0.60%  → trend / breakout regime
EXTREME  : ATRpct ≥ 0.60%       → size ×0.5, widen stops, breakout-only
```

---

## 1. Anchored VWAP Band Fade

**1. Name & core methodology** — *AVWAP σ-Band Fade*. Mean reversion around the
session's volume-weighted fair value. Premise: in the absence of trend, price
oscillates around AVWAP and σ-band excursions are inventory imbalances that decay.

**2. Indicators & parameters**
- Anchored VWAP, anchored to **00:00 UTC daily open** (re-anchor each UTC day).
- AVWAP standard-deviation bands at **±1.0σ, ±2.0σ, ±2.5σ** (σ = volume-weighted).
- ADX(14) on 5m — **trend suppressor**.
- RSI(2) — exhaustion trigger (far more responsive than RSI(14) on 5m).
- ATR(14) — stop sizing.
- Volume: 20-bar SMA of volume.

**3. Long entry (all must hold on close of bar *t*)**
1. `ADX(14) < 20` and ADX not rising for 3 bars (no trend regime).
2. Regime = LOW or NORMAL (`ATRpct < 0.30%`).
3. Low of bar *t* pierced **−2.0σ** band; close is back **above** −2.0σ (rejection wick).
4. `RSI(2) < 5` on bar *t−1* or *t*.
5. Bar *t* volume ≥ 1.5 × 20-bar volume SMA (capitulation flush, not a drift).
6. Entry: limit order at the **−2.0σ band**, valid 2 bars. Maker fill preferred; if
   unfilled after 2 bars, cancel — do not chase.

**4. Short entry** — exact mirror: pierce and reject **+2.0σ**, `RSI(2) > 95`,
`ADX(14) < 20`, volume ≥ 1.5×, limit at +2.0σ.

**5. Risk protocol**
- Stop: beyond the **±2.5σ** band, or `1.2 × ATR(14)` from entry — whichever is
  **wider** (survives the second flush) — capped at 0.55% of price.
- **Floor the stop, and don't trade near the anchor.** σ is ~0 for the first hour
  after the 00:00 UTC re-anchor, which put the σ-band stop **8 bps** from entry in
  validation — inside the 9 bps round-trip fee, making the trade unwinnable before
  it started. Require ≥ 24 bars since the anchor, and let the §0 edge gate (below)
  reject anything left.
- TP1: **AVWAP itself** — scale 60% off.
- TP2: opposite **1.0σ** band — remaining 40%.
- Move stop to breakeven when TP1 fills.
- Typical: stop 0.30%, TP1 0.35%, TP2 0.60% → blended **R:R ≈ 1.5 : 1**.
- Time stop: **12 bars (60 min)**. Mean reversion that hasn't reverted is a trend.
- Hard invalidation: if ADX crosses above 25 while in trade, exit at market.

**6. Optimal regime** — Ranging / low-to-normal volatility. Asian session
(00:00–06:00 UTC) and mid-afternoon US lulls. **Turn off** during US cash open,
CME open, and any macro print. Worst enemy: a trend day, where the band fade
becomes a knife-catch.

---

## 2. Session Opening-Range Expansion

**1. Name & core methodology** — *ORB-15 Session Expansion*. Trend following /
volatility breakout. Premise: liquidity handoffs at session opens produce a
directional imbalance that persists for the first hours of the session.

**2. Indicators & parameters**
- Opening Range = **first 3 bars (15 min)** after each of:
  - CME/US equity open **13:30 UTC**
  - London open **07:00 UTC**
  - CME crypto reopen **23:00 UTC Sunday**
- OR high / OR low / OR mid.
- ATR(14, 5m) measured **before** the open (the last pre-session reading).
- Volume: OR bars' cumulative volume vs. the same-3-bar volume median of the prior 10 sessions.
- EMA(50) on 5m as directional context.

**3. Long entry**
1. Opening range width is **0.4 × ATR(14) ≤ ORwidth ≤ 2.5 × ATR(14)** (too narrow =
   noise, too wide = the move already happened).
2. Bar closes **above OR high**, close in the upper 40% of its own range.
3. That bar's volume ≥ **1.3 ×** the 20-bar volume SMA.
4. Price **> EMA(50)** (don't fight the intraday backdrop).
5. Entry: stop-market at `OR_high + 0.05 × ATR` to reduce wick-triggered fills; or
   limit on a 1-bar retest of OR high (better fill, ~35% miss rate).
6. **Only the first breakout attempt per session is traded.** Attempt #2 is S9's job.

**4. Short entry** — mirror: close below OR low, close in lower 40% of range,
volume ≥ 1.3×, price < EMA(50), stop-market at `OR_low − 0.05 × ATR`.

**5. Risk protocol**
- Stop: **OR mid** (aggressive) or `1.0 × ATR` beyond entry (standard) — use OR mid
  when `ORwidth < 1.2 × ATR`, else ATR stop.
- TP1: `1 × ORwidth` projected from the break — take 50%.
- TP2: `2 × ORwidth` — take 30%.
- Runner: 20% on a **3×ATR Chandelier trail** (highest-high of last 22 bars − 3×ATR).
- **R:R ≈ 2.0 : 1** on the blended exit; TP2 leg alone ~3:1.
- Session time stop: flat 4 hours after entry regardless.

**6. Optimal regime** — Trend expansion, HIGH volatility, macro-catalyst days.
Fails badly in LOW-ATR chop where every OR break is a false break; require
`ATRpct ≥ 0.15%` at the session open or skip the day.

---

## 3. Squeeze Compression Breakout (BB-in-KC)

**1. Name & core methodology** — *Volatility Compression Breakout*. Volatility
regime-change trading. Premise: realised volatility is mean-reverting and
autocorrelated — compression resolves into expansion, and the resolution direction
is best inferred from momentum built during the squeeze.

**2. Indicators & parameters**
- Bollinger Bands (20, 2.0).
- Keltner Channels (20, **1.5 × ATR(20)**).
- **Squeeze ON** = BB upper < KC upper **and** BB lower > KC lower.
- Momentum oscillator: linear-regression slope of `close − avg(avg(HH20,LL20), SMA20)` over 20 bars (the TTM momentum histogram).
- Bandwidth percentile: `BBwidth / SMA20`, ranked over the trailing 200 bars.
- Volume 20-SMA.

**3. Long entry**
1. Squeeze has been **ON for ≥ 6 consecutive bars** (30 min of compression).
2. Bandwidth percentile of the squeeze period is in the **bottom 20%** of the last 200 bars.
3. Squeeze **fires** (BB re-exits KC) on bar *t*.
4. Momentum histogram is **positive and rising** on bars *t−1* and *t*.
5. Bar *t* closes above `KC upper` **and** above the squeeze-range high.
6. Volume on *t* ≥ 1.4 × 20-bar SMA.
7. Entry at market on close of *t* (this setup does not tolerate limit-order patience).

**4. Short entry** — mirror: squeeze fires, momentum negative and falling, close
below KC lower and below the squeeze-range low, volume ≥ 1.4×.

**5. Risk protocol**
- Stop: opposite side of the **squeeze range** (the consolidation high/low), capped
  at `1.5 × ATR(14)`. Compression means the range is tight, so this is usually a
  small stop — that's the whole point of the setup.
- TP1: `1.5 × squeeze_range_height` — 50% off.
- TP2: `3.0 × squeeze_range_height` — 30% off.
- Runner: 20%, trail on **EMA(21) close-through**.
- **R:R ≈ 2.5 : 1**, and this is the highest-R:R setup in the book because entry
  risk is defined by a compressed range.
- Failure rule: if price re-enters the squeeze range and closes inside it, exit
  immediately — a failed expansion usually reverses through the other side.

**6. Optimal regime** — Transition from LOW to HIGH volatility. Best pre-macro
(the 30–60 min coil ahead of CPI/FOMC) and in the late Asian → early London
handoff. Do not trade in EXTREME regime — there is no compression to trade.

---

## 4. CVD Absorption Divergence

**1. Name & core methodology** — *Order-Flow Absorption Reversal*. Pure order flow.
Premise: when aggressive market orders push volume in one direction but price
refuses to follow, a passive participant is absorbing. Absorption at a level
frequently precedes reversal.

**2. Indicators & parameters**
- **Cumulative Volume Delta (CVD)** from tick/trade data: `Σ(aggressive buy vol − aggressive sell vol)`, session-anchored, aggregated to 5m.
- CVD slope over 6 bars (linear regression).
- Price swing structure: 5-bar fractal highs/lows.
- Delta-per-bar vs. its 20-bar SMA (to identify *heavy* effort).
- Open Interest (perps) delta over the same 6 bars.
- ATR(14).

**3. Long entry**
1. Price prints a **lower low** vs. the prior 5-bar fractal low, within the last 3 bars.
2. **CVD prints an equal or higher low** over the same window → sellers are hitting
   the bid with size and getting nowhere (**bullish absorption divergence**).
3. Cumulative sell-delta over the divergence window ≥ **1.5 ×** its 20-bar average
   (effort must be large; a small divergence is noise).
4. Open Interest **rising** into the low → new shorts being opened into absorption
   (fuel for a squeeze). If OI is *falling*, this is long liquidation, not
   absorption — **skip**.
5. Confirmation bar: a 5m close **above** the high of the divergence low bar.
6. Entry at market on that confirmation close.

**4. Short entry** — mirror: price higher high, CVD equal/lower high (bearish
absorption), buy-delta ≥ 1.5× average, OI rising, confirm on close below the
divergence high bar's low.

**5. Risk protocol**
- Stop: **1 tick beyond the absorption extreme** (the wick low/high), floored at
  `0.8 × ATR(14)` so a 1-tick stop can't be micro-stopped by noise.
- TP1: the most recent opposing swing (prior 5-bar fractal) — 50%.
- TP2: `2.5 × risk` — 30%.
- Runner: 20% trailed under successive 5-bar fractals.
- **R:R ≈ 2.2 : 1**. This setup's strength is a genuinely tight, structurally
  justified stop.
- Hard rule: if CVD makes a *new* extreme in the trade direction against you
  (absorption failed, aggressor won), exit at market immediately — do not wait
  for the price stop.

**6. Optimal regime** — Works across regimes but best at HIGH volatility session
extremes and at prior day high/low, monthly VWAP, and large resting-liquidity
levels. **Requires trade-tick data**; if you only have OHLCV, this strategy is not
implementable and should be disabled rather than approximated with a volume proxy.

---

## 5. Liquidity Sweep Reclaim

**1. Name & core methodology** — *Stop-Run Reversal / market structure*. Premise:
resting stop clusters sit just beyond obvious swing highs/lows. Price is drawn
there, triggers them, and if the move was liquidity-seeking rather than
informational, it reverses back inside the range within a few bars.

**2. Indicators & parameters**
- Swing high/low detection: **fractal with 3-bar lookback each side**, only levels
  that have held for ≥ 12 bars.
- Sweep window: **≤ 3 bars** beyond the level.
- Reclaim confirmation: 5m close back inside the prior range.
- ATR(14); RSI(14) for divergence confluence (optional filter, adds ~10% win rate,
  costs ~25% of signals).
- Session/prior-day high & low, and the **Asian-session range** (00:00–07:00 UTC)
  as the highest-quality sweep levels.

**3. Long entry** (sweep of a low)
1. Identify a qualified swing low `L` (or prior-day low / Asian low).
2. Price trades **below L** by ≥ `0.15 × ATR` (a genuine sweep, not a graze).
3. Within **3 bars**, a 5m bar **closes back above L**.
4. That reclaim bar's range ≥ `0.8 × ATR` and it closes in the **upper third** of
   its range.
5. Optional confluence: RSI(14) at the sweep low is **higher** than at the prior low.
6. Entry: market on the reclaim close, or limit at `L` on the retest (≈50% of
   sweeps retest; better fill, ~half the fills missed).

**4. Short entry** — mirror: sweep above swing high `H` by ≥ 0.15×ATR, close back
below `H` within 3 bars, reclaim bar closes in lower third of its range.

**5. Risk protocol**
- Stop: **beyond the sweep extreme** + `0.25 × ATR` buffer (stop-hunters often
  double-tap the same wick). Cap at `1.5 × ATR`; if the sweep wick is longer than
  that, the trade is **skipped** — the risk no longer fits the sizing model.
- TP1: mid-point of the swept range — 40%.
- TP2: **the opposite side of the range** (equal highs/lows, where the *other*
  stop cluster sits) — 40%.
- Runner: 20% beyond the range, trailed at `2 × ATR`.
- **R:R ≈ 2.5–3.0 : 1** — the defining feature: stop at the wick, target the
  opposite liquidity pool.
- Invalidation: a 5m **close** back beyond the sweep extreme = thesis dead, exit.
- Time stop: 10 bars to reach TP1 or exit at market.

**6. Optimal regime** — Ranging-to-choppy markets and the pre-breakout hours; also
extremely effective at HIGH volatility session opens where the first move is
frequently a fake. Poor in sustained trend expansion — in a real trend the "sweep"
is just continuation, which is why the reclaim close is non-negotiable.

---

## 6. EMA Ribbon Pullback Continuation

**1. Name & core methodology** — *Trend-following pullback*. Premise: intraday BTC
trends persist through shallow, low-volume retracements; entering on the
retracement rather than the breakout dramatically improves R:R and cuts slippage.

**2. Indicators & parameters**
- EMA **8 / 21 / 55** on 5m (the ribbon).
- EMA(200) on 5m for the higher-order bias.
- ADX(14) — **trend confirmer** (opposite polarity to S1's use).
- Fibonacci retracement of the last impulse leg (38.2% / 50% / 61.8%).
- ATR(14); volume 20-SMA.

**3. Long entry**
1. Ribbon stacked bullish: `EMA8 > EMA21 > EMA55`, all three sloping up over 5 bars.
2. `close > EMA200` and `ADX(14) > 22` and ADX rising.
3. An impulse leg has just made a new 20-bar high.
4. Price retraces into the **EMA21–EMA55 zone**, which overlaps the **38.2–61.8%**
   retracement of that leg.
5. Pullback quality: pullback bars' average volume **< 0.8 ×** the impulse bars'
   average volume (retracement, not distribution), and the pullback takes **≤ 8 bars**.
6. Trigger: a 5m bar closes back **above EMA8** with a close in the upper half of
   its range.
7. Entry at market on that close; or resting limit at EMA21 for a better price.

**4. Short entry** — mirror: `EMA8 < EMA21 < EMA55` all sloping down, `close < EMA200`,
ADX > 22 rising, new 20-bar low, retrace into EMA21–EMA55 / 38.2–61.8%, low-volume
pullback ≤ 8 bars, trigger on close back below EMA8.

**5. Risk protocol**
- Stop: **below EMA55 − 0.5 × ATR**, or below the pullback swing low, whichever is
  lower; hard cap `1.5 × ATR`.
- TP1: prior impulse high (the swing that started the pullback) — 40%.
- TP2: `1.618 ×` the impulse leg projected from the pullback low — 30%.
- Runner: 30%, **Chandelier trail at 2.5 × ATR(22)**; exit fully on an `EMA8 < EMA21`
  cross.
- **R:R ≈ 2.0 : 1** blended; the runner leg is what pays for the strategy's
  ~45–50% hit rate.
- Max **2 pullback entries per trend leg** — the third pullback in a leg is
  statistically distribution, not continuation.

**6. Optimal regime** — Trend expansion, NORMAL-to-HIGH volatility, US session.
Explicitly gated OFF when `ADX < 22` (that's S1's regime) and in EXTREME volatility
where EMA structure whipsaws faster than the 5m bar can confirm.

---

## 7. Funding & OI Liquidation-Cascade Momentum

**1. Name & core methodology** — *Derivatives-positioning momentum*. Premise:
crowded, over-levered perp positioning is fuel. When funding is extreme and open
interest is high, a move against the crowd triggers forced liquidations that
mechanically extend the move. You are trading the cascade, not predicting it.

**2. Indicators & parameters**
- **Funding rate** (perp, 8h), and its 3-day z-score.
- **Open Interest** (aggregate across major perp venues), 5m change and 24h z-score.
- **Liquidation volume** feed (5m notional liquidated), 20-bar SMA.
- Perp **basis** vs. index (bps).
- ATR(14); 20-bar Donchian channel.

**3. Long entry** (short-squeeze cascade)
1. Funding rate **z-score ≤ −1.5** over the trailing 3 days (shorts are paying —
   crowded short).
2. Open Interest 24h z-score ≥ **+1.0** (the crowd is levered, not flat).
3. Trigger bar: price closes **above the 20-bar Donchian high** with range ≥ `1.5 × ATR`.
4. **Short-liquidation notional** in that bar ≥ **3 ×** its 20-bar SMA (the cascade
   is confirmed, not anticipated).
5. Open Interest **falls** ≥ 0.5% over the trigger bar → positions being force-closed.
6. Entry at market immediately on the trigger bar close. **Accept the slippage** —
   this is the one setup where paying up is correct; use IOC with a 15 bps limit
   cap and abandon if unfilled.

**4. Short entry** — mirror: funding z-score ≥ **+1.5** (crowded long), OI z ≥ +1.0,
close below 20-bar Donchian low with range ≥ 1.5×ATR, long-liquidation notional ≥ 3×
SMA, OI falling ≥ 0.5%.

**5. Risk protocol**
- Stop: `1.5 × ATR(14)` — **wide by design**; cascades are violent in both
  directions. Because the stop is wide, `risk_pct` for this strategy is **halved to
  0.25%** and the leverage cap tightened to **3×**.
- TP1: `1.5 × risk` — 50% off fast (cascades mean-revert hard once liquidations exhaust).
- TP2: `3.0 × risk` — 30%.
- Runner: 20% until **liquidation volume falls back below its 20-bar SMA for 2
  consecutive bars**, then market out.
- **R:R ≈ 2.0 : 1** with a deliberately low expected hit rate (~40%).
- Hard time stop: **6 bars (30 min)**. Cascades are fast; if it hasn't paid in 30
  minutes it wasn't a cascade.
- Do not add. Do not average down. Ever, on this one.

**6. Optimal regime** — EXTREME volatility, by definition. Requires funding, OI,
and liquidation data feeds — with OHLCV only, **disable it**; a proxy version of
this strategy is worse than no strategy.

---

## 8. Perp–Spot Basis Z-Score Reversion

**1. Name & core methodology** — *Statistical relative value*. Premise: the perp (or
front-quarterly) trades at a basis to spot/index that is stationary intraday.
Extreme basis dislocations on a 5m horizon are liquidity events and revert. This
is the only market-neutral-*ish* strategy in the book.

**2. Indicators & parameters**
- `basis_bps = (perp_mid − index) / index × 10_000`.
- Rolling mean and stdev of `basis_bps` over **288 bars (24h)**.
- `z = (basis_bps − mean) / stdev`.
- ADF/Hurst sanity check on the basis series (rolling 3-day) — **only trade when
  Hurst < 0.5**, i.e. the basis is actually mean-reverting.
- Funding rate (the basis's carry anchor) and time-to-next-funding.
- ATR(14) of BTC price for stop sizing.

**3. Long entry (long perp)**
1. `z ≤ −2.0` (perp trading cheap to index — panic selling in derivatives).
2. Hurst(basis, 3d) **< 0.5** and stdev of basis is not itself exploding
   (`stdev_now < 2 × stdev_24h_median`) — a regime break is not a dislocation.
3. Basis **stops making new lows** for 2 consecutive bars (z is rising off the extreme).
4. Time to next funding settlement **> 45 min** (avoid funding-print distortion).
5. Entry: limit at perp mid, market only if z ≤ −3.0.
6. **Hedged variant (preferred):** long perp / short an equal notional of spot or
   the quarterly — isolates the basis and removes BTC direction entirely.
   Unhedged variant is a directional trade with a basis trigger and must be sized
   under the standard ATR rule.

**4. Short entry (short perp)** — mirror: `z ≥ +2.0` (perp rich — leveraged
euphoria), Hurst < 0.5, basis stops making new highs for 2 bars, >45 min to
funding.

**5. Risk protocol**
- Stop (hedged): `z` reaching **±3.5** → exit; i.e. the stop is in basis space, not
  price space. Position sizing off basis stdev, not ATR.
- Stop (unhedged): `1.0 × ATR(14)` on BTC price, standard sizing.
- TP: **z reverting to ±0.5** — full exit; no scaling (the mean is the target).
- **R:R ≈ 1.3 : 1 hedged**, but with a materially higher hit rate (~65–70%
  historically for basis reversion) and near-zero directional beta — the Sharpe,
  not the R:R, is the point.
- Funding drag: if the position must be held across a settlement, the funding
  payment is charged against the trade's expectancy *before* entry. If
  `expected_reversion_bps < funding_cost_bps + 9 bps fees`, **skip**.
- Time stop: **24 bars (2h)**.

**6. Optimal regime** — All regimes, but the dislocations that matter cluster in
HIGH/EXTREME volatility. Degrades in a sustained directional squeeze where the
basis trends (hence the Hurst gate). Requires a synchronised perp + index/spot
feed with aligned timestamps — stale-quote arbitrage against yourself is the main
failure mode here.

---

## 9. Failed Breakout Range Fade

**1. Name & core methodology** — *Contrarian false-breakout fade*. Premise: most
range breakouts on a 5m BTC chart fail. When a break lacks volume and order-flow
confirmation and price closes back inside, the trapped breakout traders' stops
become the fuel for a move to the opposite side of the range.

**2. Indicators & parameters**
- Donchian channel (20) to define the range; range must be ≥ **20 bars old**.
- Range width filter: **`3 × ATR(14) ≤ width ≤ 8 × ATR(14)`**.
  *(Corrected after implementation. The original `0.5–3 × ATR` was arithmetically
  impossible for a 20-bar range: for a random walk the expected n-bar range is
  ≈ `1.6 σ √n` while `ATR(14) ≈ 1.13 σ`, putting a 20-bar Donchian near **6.4 ×
  ATR** by construction. Measured median was 6.09 × ATR and the old window matched
  0.8% of bars.)*
- Volume 20-SMA; RSI(2).
- Bollinger Bandwidth percentile (to confirm the market is *in* a range, i.e. NOT
  in the bottom-20% squeeze that S3 trades — a squeeze break is usually real).
- ATR(14).

**3. Long entry** (fading a failed downside break)
1. A 20-bar Donchian range has been intact ≥ 20 bars.
2. Price breaks **below** the range low.
3. Break bar volume **< 1.2 ×** the 20-bar volume SMA → **unconfirmed** break
   (this is the core filter; a high-volume break is not faded).
4. Within **3 bars**, a 5m bar **closes back above the range low**.
5. `RSI(2) < 10` at the break extreme.
6. Bandwidth percentile **> 30%** (not a compression breakout — those are real).
7. Entry at market on the reclaim close.

**4. Short entry** — mirror: break above range high on volume < 1.2× SMA, close back
inside within 3 bars, `RSI(2) > 90`, bandwidth percentile > 30%.

**5. Risk protocol**
- Stop: `0.35 × range_width` beyond the failed break extreme; hard cap `1.2 × ATR`.
- TP1: **range mid** — 50%.
- TP2: **opposite range boundary** — 50%. No runner: this is a range trade and it
  ends at the range edge.
- **R:R ≈ 2.0 : 1** (stop is a fraction of the range, target is the full range).
- Invalidation: a **second** break of the same side on volume ≥ 1.5× SMA → exit at
  market and stand down on this range for the rest of the session. Ranges that
  break twice, break.
- Max **2 fades per range** per side.
- Time stop: 15 bars (75 min).

**6. Optimal regime** — Ranging, LOW-to-NORMAL volatility, weekends and holiday
tape, Asian session. Explicitly mutually exclusive with S3 (squeeze) — the
bandwidth-percentile gate exists precisely so the two never fire on the same
setup. Disable entirely on macro-catalyst days.

---

## 10. Order-Book Imbalance Micro-Scalp

**1. Name & core methodology** — *Market microstructure / queue imbalance*.
Premise: over very short horizons, the microprice (depth-weighted mid) predicts
the next trade direction better than the mid. Persistent top-of-book imbalance
plus a book-pressure drift gives a small but repeatable edge — harvested with
maker orders so fees work *for* you.

**2. Indicators & parameters**
- **Order-book imbalance** across the top 10 levels:
  `OBI = (Σ bid_size − Σ ask_size) / (Σ bid_size + Σ ask_size)`, sampled at 1s and
  averaged over the 5m bar.
- **Microprice** = `(bid × ask_size + ask × bid_size) / (bid_size + ask_size)`;
  signal = `microprice − mid` in bps.
- Book **replenishment ratio**: added vs. cancelled size at the touch over 30s.
- Spread (bps) and top-of-book depth vs. their 100-bar medians.
- 5m ATR(14) for the regime gate and hard stop.

**3. Long entry**
1. `OBI ≥ +0.35` sustained for **≥ 60 seconds** (not a single snapshot — spoofing
   shows up as a spike that doesn't persist).
2. `microprice − mid ≥ +0.8 bps`.
3. Bid-side **replenishment ratio > 1.2** (the bid is being refilled as it is hit —
   real intent, not a display).
4. Spread ≤ 1.5 × its 100-bar median **and** top-of-book depth ≥ 0.8 × median
   (adequate liquidity; the edge is negative in a thin book).
5. `ATRpct < 0.30%` — micro-scalping in HIGH/EXTREME volatility is a losing game.
6. Entry: **post-only limit at the bid**. If not filled within 45s, cancel. Never
   cross the spread on this strategy — the entire edge is smaller than the taker fee.

**4. Short entry** — mirror: `OBI ≤ −0.35` sustained ≥ 60s, `microprice − mid ≤
−0.8 bps`, ask-side replenishment > 1.2, spread/depth normal, `ATRpct < 0.30%`,
post-only limit at the ask.

**5. Risk protocol**
- Stop: **4–6 bps** from entry (roughly `0.25 × ATR`), as a **market** order —
  micro-scalps must exit fast and take the fee.
- TP: **8–12 bps**, post-only limit on the opposite side (earn the maker rebate on
  both legs where the venue offers one).
- **R:R ≈ 1.5 : 1 gross**; net edge is thin and depends entirely on maker fills.
  With taker fills on both legs (9 bps round trip) the strategy is **negative
  expectancy** — that is the single most important fact about it.
- Signal-invalidation exit: OBI flips sign or falls below ±0.10 → flat immediately,
  regardless of P&L. The signal, not the price, is the stop.
- Time stop: **3 minutes**.
- Sizing: `risk_pct` reduced to **0.10%** per trade (high frequency, low edge per
  trade); daily trade cap of 40 to bound fee drag; cumulative fee spend tracked as
  a first-class P&L line.

**6. Optimal regime** — LOW volatility, tight spreads, deep book — the exact
conditions every other strategy here dislikes. **Kill switch:** any of
`ATRpct ≥ 0.30%`, spread > 2 × median, or depth < 0.5 × median → stand down.
Requires L2 book data and low-latency execution; on a retail REST connection with
200 ms+ round trips, do not run this — the edge is inside the latency.

---

## Strategy matrix

| # | Strategy | Class | Best regime | Typical stop | R:R | Data needed |
|---|---|---|---|---|---|---|
| 1 | AVWAP σ-Band Fade | Mean reversion | Ranging, LOW/NORMAL | 1.2×ATR | 1.5 | OHLCV |
| 2 | Session ORB Expansion | Momentum breakout | Trend expansion, HIGH | 1.0×ATR / OR mid | 2.0 | OHLCV |
| 3 | Squeeze Compression Break | Vol expansion | LOW→HIGH transition | Squeeze range | 2.5 | OHLCV |
| 4 | CVD Absorption Divergence | Order flow | HIGH, at key levels | 0.8×ATR | 2.2 | Trade ticks |
| 5 | Liquidity Sweep Reclaim | Market structure | Ranging / session opens | Sweep wick + 0.25×ATR | 2.5–3.0 | OHLCV |
| 6 | EMA Ribbon Pullback | Trend following | Trend, NORMAL/HIGH | EMA55 − 0.5×ATR | 2.0 | OHLCV |
| 7 | Liquidation Cascade | Positioning momentum | EXTREME | 1.5×ATR | 2.0 | Funding/OI/liqs |
| 8 | Perp–Spot Basis Z-Score | Statistical RV | All (dislocations) | z = ±3.5 | 1.3 (hedged) | Perp + index |
| 9 | Failed Breakout Fade | Contrarian range | Ranging, LOW/NORMAL | 0.35×range | 2.0 | OHLCV |
| 10 | Order-Book Imbalance | Microstructure | LOW vol, deep book | 4–6 bps | 1.5 gross | L2 book |

**Regime routing** — at most one directional strategy live at a time:

```
ATRpct < 0.12%              → S3, S10, S9, S1, S5     (fade / compression)
0.12% ≤ ATRpct < 0.30%      → S3, S2, S6, S5, S1, S9  (mixed)
0.30% ≤ ATRpct < 0.60%      → S2, S6, S5, S4          (trend / breakout)
ATRpct ≥ 0.60%              → S7, S8 only             (cascade / RV), size ×0.5
Squeeze ON + bandwidth pct < 20  → S3 has priority, S9 disabled
ADX < 20 → S1/S9 armed, S6 disabled ; ADX > 22 rising → S6 armed, S1 disabled
```

*(Corrected after implementation. The original table routed **S3 to HIGH only**,
which made it unreachable: every S3 signal fires in LOW/NORMAL, because ATR(14)
is a **trailing** classifier and a squeeze breaks out while the average still
reflects the compressed bars it is escaping. That also contradicted S3's own
"optimal regime — transition from LOW to HIGH". Each row now follows the
strategies' own regime sections. Priority inside a bucket is by scarcity and
time-criticality — a rare setup that must be taken on its signal bar outranks a
frequent one — never by observed P&L.)*

**Lagging-classifier caveat, generally.** Any regime gate built on a trailing
average reads the regime the market is *leaving*, not the one it is entering.
That is harmless for the fade strategies, which want the regime to persist, and
actively wrong for the expansion strategies (S2, S3), which are defined by a
regime change. Where a strategy trades a transition, gate it on the compression
it is leaving, not the expansion it is entering.

## Validation requirements before any of these leave paper

1. Walk-forward, not in-sample: fit on 6 months, test on the next 2, roll.
2. Fees and slippage modelled at the table in §0 — **not** at zero, and not at the
   maker rate unless the strategy is genuinely post-only.
3. Funding charged on every bar held for perps.
4. Report: hit rate, expectancy in R, max adverse excursion distribution, Sharpe,
   max drawdown, and **trade count** (a 12-trade backtest proves nothing).
5. Regime-conditional performance — a strategy that is only profitable in one
   regime must be gated to that regime in code, not left to run everywhere.
6. Minimum 300 out-of-sample trades before any size beyond the smallest increment.
</content>
</invoke>
