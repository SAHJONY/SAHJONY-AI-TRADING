# SAHJONY Institutional Runtime V2

## Objective

Evolve the existing trading system without replacing the current production runtime or weakening broker safety controls. V2 is introduced as a shadow/challenger stack and is promoted only after measurable out-of-sample improvement.

## Phase 1: risk and execution attribution

This branch adds two isolated components:

1. `risk/portfolio_governor.py`
   - fractional Kelly reduction
   - volatility targeting
   - correlation crowding penalty
   - soft/hard drawdown rails
   - single-position cap
   - gross-exposure cap
   - optional liquidity cap
   - fail-closed validation
   - reduction-only sizing: it cannot increase the caller's proposed notional

2. `execution/attribution.py`
   - reference-vs-fill slippage
   - fees
   - spread cost
   - adverse-selection cost
   - gross and net PnL
   - implementation shortfall in basis points

Neither component submits orders or changes broker configuration.

## Architecture target

```text
Market Data Fabric
        |
        v
Microstructure / Feature Layer
        |
        v
Alpha Ensemble
  | current agents
  | statistical models
  | TimesFM challenger (optional)
        |
        v
Consensus / Calibration
        |
        v
Portfolio Risk Governor
        |
        v
Deterministic Execution Policy
        |
        v
Broker / Exchange Router
        |
        v
Reconciliation + Execution Attribution
        |
        v
Learning / Champion-Challenger
```

GPT-class models belong above the deterministic execution path. They may analyze regimes, investigate anomalies, recommend strategy/risk changes, and generate research candidates, but they must not bypass portfolio limits, circuit breakers, broker reconciliation, or promotion gates.

## Promotion gates

V2 should remain shadow/paper until all of the following are demonstrated against the current champion baseline:

- 100% broker reconciliation for evaluated sessions
- 100% attributable fills/PnL for evaluated trades
- zero risk-limit bypasses
- lower or equal maximum drawdown
- lower implementation shortfall/slippage after comparable turnover
- improved net Sharpe/Sortino or clearly improved risk-adjusted expectancy
- no material regression across multiple market regimes

## Next phases

### Phase 2

- normalized real-time market-data interface
- microstructure features: order-flow imbalance, spread, depth imbalance, realized volatility, liquidity pressure
- event schema for alpha, risk, order, fill, and reconciliation telemetry

### Phase 3

- smart execution policy selection (limit/market/post-only/TWAP/VWAP where supported)
- strategy-level and broker-level execution attribution
- champion/challenger ranking with walk-forward evidence

### Phase 4

- GPT strategy supervisor with strict structured outputs
- TimesFM only as an optional challenger signal
- automatic recommendation generation, never automatic production promotion

## Safety invariant

No V2 component may enable live trading, widen hard risk ceilings, skip authenticated reconciliation, or self-promote a model/strategy into production without the existing governance gates.
