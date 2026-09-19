# SAHJONY-AI-TRADING — World-Class Review
**Date:** 2026-09-19 · **Branch:** `upgrade/world-class` · **Reviewers:** 4 parallel deep-dives (architecture, strategies, risk/execution, data/ops) + lead synthesis

## What this repo is

A modular, multi-venue autonomous trading desk ("SAHJONY CAPITAL LLC") in layered Python: pure-domain quant engines (`intelligence/`), an orchestration layer (`workforce/` Firm: Research → AI Brain → Portfolio Manager → Strategy Desks → Risk Officer → Execution Trader → Treasurer → Reporter), and I/O adapters. Defaults to offline-sim; targets Alpaca **paper** with keys; live requires an exact-string ack plus multiple gates. A 12-persona Intelligence Council plus a Claude-primary AI brain produce conviction; hard risk ceilings in `config.py` cannot be widened by `.env`.

This is already far above a typical retail bot. The review below is calibrated against what the best institutional/prop systems do.

## Strengths (genuinely world-class already)

- **Fail-closed culture throughout.** Risk gates default-deny; the production canary adapter cannot place an order by construction (no transport injected by default); every external call is wrapped so the loop never crashes.
- **Hard ceilings in code** — 15% single position, 80% total deployed, 25% daily breaker — clamped at config load; `.env` can only tighten.
- **Backtest engine is deliberately pessimistic:** causal indicators, stop-assumed-first intrabar fills, fees both sides, vol-scaled slippage (×2 on stops, ×4 on event bars), edge gate (TP1 must clear 3× round-trip cost), leverage-breaching setups skipped not shrunk, fixed-fractional sizing in R-multiples.
- **Validation is institutional-grade:** expanding-window walk-forward with purge + embargo, untouched final holdout, PBO, Deflated Sharpe Ratio, Bonferroni multiple-testing-adjusted Sharpe hurdle, parameter-stability checks, promotion gates defaulting to FAIL.
- **Metrics done right:** R-multiples, trade count first, Sharpe/Sortino/max-DD/profit factor, MAE/MFE, regime-conditional expectancy, exit-reason breakdown, buy&hold reference.
- **Execution safety:** intent validation independent of risk gating (exits flow during halts), three-layer duplicate protection (sha256 intent id + atomic DB reservation + per-symbol pending lock), idempotency conflicts halt rather than guess.
- **Kill switch + latched daily circuit breaker** (no intraday un-trip; re-anchors on capital flows, not misread as drawdown), fail-closed remote halt.
- **Data integrity:** Hermes guardian quarantines bad feeds (conviction→0, blocks new risk, exits flow); per-quote provenance, outlier rejection, freeze detection; last-good-price fallback (never 0.0).
- **The AMPY lesson is in the code:** per-position cap includes existing position value — a documented fix for a real incident ($49k built on a $2k account via individually-small adds).
- **74 test files** with a conftest that disables live trading; honest limitation docs (IBKR/CCXT "untested live" disclaimers).

## Gaps (prioritized)

### P0 — Capital protection (non-negotiable for real money)

1. **`PortfolioRiskGovernor` is not wired into live execution.** Fractional-Kelly sizing, correlation/heat penalty (0.75), 80% gross-exposure cap, 5%/10% drawdown throttle — built, tested, but only instantiated in tests. Its own docstring says "shadow/challenger… before wiring it into live execution." The live book has no portfolio-heat or trailing max-drawdown guard; only the daily breaker + notional caps. → **IMPLEMENTING on this branch.**
2. **`hard_stop_breached()` is dead code** (`risk/risk_engine.py:127`). The advertised "Millennium-style programmatic exit before drawdown grows" per-position stop-out has zero callers. Nothing enforces a per-position hard stop live.
3. **Live risk-per-trade ≠ backtest risk-per-trade, and the gate is opt-in.** Backtest sizes 0.35% fixed-fractional off stop distance; live sizes conviction-scaled notional up to 10–15% equity with no stop-distance risk anchor. Worse: `OrderIntent.risk_check` defaults to `False` (`strategies/base.py:88`) — any strategy that forgets `risk_check=True` silently bypasses `RiskEngine.approve()`.
4. **Kill switch and daily breaker only block *new* risk; neither flattens positions.** A 6% down day halts entries but leaves the bleeding book open.

### P1 — Backtest realism corrections

5. `backtest/metrics.py` — `"mae_r_p90"` is computed with `np.percentile(..., 10)` (mislabeled; that's p10). → **FIXING on this branch.**
6. No bid-ask spread model; no latency model; perp funding defaults to 0 (`funding_bps_per_8h=0.0`) — a real cost for positions held across settlements. → **Adding spread cost option on this branch.**
7. Fabricated-bar risk: `bar_recorder` honestly documents O=H=L=C bars and tick-count "volume" at poll cadence, but nothing stops a strategy consuming those bars — volume/ATR/wick signals would read sampling artifacts as market structure.

### P1 — Strategy interface

8. **Three incompatible strategy conventions, no common live interface.** `strategies/base.py` is types/helpers only; live desks have inconsistent `decide()` signatures (`CopyTrader.decide(signals, state, equity, get_price)` vs `WheelStrategy.decide(symbol, snap, pos, council, budget, chain)`); the only real `Strategy` base class (`backtest/engine.py:115`) serves BTC-5m backtests that can't emit `OrderIntent`. `signals/` is an empty package. → **Defining unified `LiveStrategy` protocol on this branch.**
9. **No research→live promotion path.** Despite `docs/STRATEGY_PROMOTION_GATES.md`, validated backtest strategies (S1–S18) technically cannot become live desks — two separate worlds.
10. **Regime filter is advisory only.** `stressed_prob` is computed every cycle but no desk changes behavior on it — no bull/bear/chop gating of entries, sizing, or exits.

### P2 — Operations & safety hardening

11. **Alerting is dead code.** `utils/notify.py` (Telegram/WhatsApp/voice) is initialized once and never called. A circuit-breaker trip or broker disconnect pages nobody.
12. **Robinhood venue has no paper mode** — real-money-only API, double-gated but never exercised on fake money. A miscopied env arms real orders on an untested path.
13. **"Never enabled from CI" is policy, not architecture.** `.github/workflows/desk.yml` wires `LIVE_TRADING_ACK` from a GitHub secret with a documented live promotion path.
14. **`AUTO_UPDATE_MODELS=true` by default** — the AI brain can change model versions between cycles: unreviewed config drift in a determinism-oriented system.
15. **No verified test signal** — pytest isn't installed here and there's no pytest config; 73 test files' pass/fail state is unverified in this environment.
16. **Incubator strategies dead in the live loop** (`regime_momentum.py`, `statistical_mean_reversion.py`, `volatility_breakout.py` — tests only); live desks hardcode convictions (`conv = 0.70`) ignoring the council; wheel has no downside stop on assigned names.

## Upgrade plan (this branch)

| # | Upgrade | Status |
|---|---|---|
| 1 | Wire `PortfolioRiskGovernor` into `ExecutionTrader` as second gate (portfolio rails only; Kelly neutral via limits) + config flag + tests | **DONE** — budget-stage throttle (`_governor_cycle_gate`) + execution-stage veto (`_governor_decision`); 7 integration tests pass |
| 2 | Fix `mae_r_p90` percentile label | **DONE** |
| 3 | Add bid-ask spread to backtest `CostModel` | **DONE** — `spread_bps=1.0` default, taker crosses half; edge gate includes spread |
| 4 | Define unified `LiveStrategy` protocol in `strategies/base.py` + migrate one desk as proof | **DONE** — `StrategyContext` + `LiveStrategy` Protocol + `adapt_legacy_strategy()`; `TrailingLadder` migrated natively |
| 5 | Wire `hard_stop_breached()` into per-cycle position management | **DONE** — central `_catastrophic_stop_sweep` (25% default); 5 tests pass |
| 6 | Default `risk_check=True` on `OrderIntent` (fail-closed direction) | **DONE** — audited: all equity/option intents already set it explicitly |
| 7 | Wire `Notifier` to circuit-breaker/kill-switch/critical errors | Deferred (needs credentials; code-ready) |
| 8 | Research→live bridge (backtest `Strategy` → `OrderIntent` adapter) | Deferred (large) |
| 9 | Regime-gated entries/sizing | Deferred (needs validation first) |

**Non-goals for this branch:** live trading enablement, new venues, SaaS/CRM changes, any credential handling. Paper/sim defaults only.

## Implementation notes (2026-09-19)

**Portfolio governor wiring** (`workforce/workforce.py`, `config.py`):
- `Firm` constructs `PortfolioRiskGovernor` with `PortfolioRiskLimits` from config (Kelly neutral: `fractional_kelly=1.0` + `raw_kelly=1.0` → pass-through; vol targeting off — `RiskEngine.vol_scalar` owns it; correlation neutral at 0.0 until a matrix exists).
- Two integration layers: (a) `_governor_cycle_gate()` — once per cycle, computes a `[0,1]` budget throttle from drawdown/exposure room, applied to all strategy budgets; (b) `ExecutionTrader._governor_decision()` — veto-only backstop after `RiskEngine.approve()`, with intra-cycle gross-exposure tracking. Never mutates intents (no qty/`set_position` fixup risk). Fail-closed on any exception.
- `PORTFOLIO_GOVERNOR=false` restores pre-governor behavior. All governor decisions are audit-logged (`portfolio_governor` events).
- New config: `PORTFOLIO_GOVERNOR`, `PORTFOLIO_MAX_GROSS_PCT`, `PORTFOLIO_DD_SOFT/HARD`, `PORTFOLIO_MAX_PAIR_CORR` — all clamped.

**Backtest realism** (`backtest/engine.py`, `backtest/metrics.py`):
- `CostModel.spread_bps=1.0` (BTC perps realistic); `_fill_px` now takes `maker` flag — takers cross half-spread, makers pay none. Edge gate round-trip cost includes spread.
- Fixed `mae_r_p90` (was percentile 10, now 90).

**Strategy interface** (`strategies/base.py`, `strategies/trailing_ladder.py`):
- `StrategyContext` dataclass (symbol/snap/position/council/budget/state/get_price/extras) + `LiveStrategy` Protocol (`strategy_id`, `decide(ctx)`).
- `TrailingLadder` implements `decide(ctx)` natively; `decide_legacy()` shim kept for backward compat; workforce call site uses the protocol.
- `adapt_legacy_strategy()` wraps unmigrated desks (wheel, spreads, day, pairs, copy) — documents the migration path.

**Catastrophic stop** (`workforce/workforce.py`, `config.py`, `risk/risk_engine.py`):
- `_catastrophic_stop_sweep()` runs each cycle after the desks: liquidates any equity position beyond `CATASTROPHIC_STOP_PCT` (default 25%) from cost basis. Handles shorts (covers on price rise). Skips unpriceable/missing-basis positions. Emits `risk_check=False` exits so it works during halts.

**Tests added:** `test_governor_integration.py` (7), `test_strategy_interface.py` (4), `test_catastrophic_stop.py` (5). All pass. Existing suite: backtest, regressions, multi-market, circuit-breaker, order-lifecycle, copy/day/credit/pairs desks, governor unit tests — all pass.
