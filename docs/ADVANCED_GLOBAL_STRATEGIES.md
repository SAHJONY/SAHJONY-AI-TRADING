# Advanced Global Strategy Research

## Status

This document is a research catalog. It does not authorize live activation, modify broker routing, or alter open positions. Every strategy must pass the promotion gates in `docs/STRATEGY_PROMOTION_GATES.md`.

## Research principles

The desk should copy the research discipline of leading systematic firms, not claim to reproduce proprietary signals.

- Renaissance Technologies: ensemble research, short-lived statistical signals, execution discipline.
- D. E. Shaw: quantitative multi-strategy diversification.
- Two Sigma: hypothesis-driven machine learning, feature libraries, automation, and regime modeling.
- AQR / Cliff Asness: value, momentum, quality, carry, and defensive factors.
- Man AHL / Russell Korgaonkar: multi-market trend following and volatility targeting.
- Bridgewater / Ray Dalio: global-macro cause-and-effect models and risk-balanced portfolios.
- Jane Street and Citadel Securities: pricing, execution, inventory control, and adverse-selection management.
- Ed Seykota, Bill Dunn, David Harding: systematic trend following and loss control.
- Paul Tudor Jones and Stanley Druckenmiller: macro catalysts and capital preservation; their discretionary judgment is not directly reproducible.

## Priority strategy families

### 1. Multi-speed time-series momentum

Combine approximately one-, three-, and twelve-month excess-return signals. Trade in the signal direction and scale exposure inversely to forecast volatility.

Required controls:

- Diversify across sufficiently liquid markets.
- Cap single-market, asset-class, and correlated-cluster exposure.
- Blend fast and slow signals.
- Reduce turnover when expected edge is smaller than estimated costs.
- Detect reversal and range-bound regimes without disabling the core model by discretion.

Primary reference:
https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing

### 2. Cross-sectional momentum

Rank comparable assets by medium-term risk-adjusted performance, buy the strongest eligible assets, and avoid or short the weakest only where the broker and mandate permit.

Required controls:

- Sector, beta, size, liquidity, and volatility neutrality.
- Skip earnings and corporate-action windows when event risk dominates.
- Control momentum-crash exposure through volatility and market-regime filters.

### 3. Quality-value-momentum ensemble

Score equities using profitability, growth, balance-sheet safety, payout quality, valuation, and momentum. Combine signals rather than relying on any single factor.

Required controls:

- Point-in-time fundamentals.
- Delisting and survivorship-bias-free universes.
- Sector-relative normalization.
- Capacity, turnover, borrow, and transaction-cost constraints.

References:
https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly
https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/AQRJPMQuant23FactFictionandFactorInvesting.pdf

### 4. Statistical arbitrage

Research cointegrated pairs, residual momentum, cross-sectional mean reversion, and market-neutral baskets.

Required controls:

- Walk-forward pair selection.
- Structural-break and parameter-drift tests.
- Dollar, beta, sector, and factor neutrality.
- Borrow availability and short-sale costs.
- Stop trading when residual behavior no longer matches training assumptions.

### 5. Regime-aware risk overlay

Estimate persistent volatility, liquidity, correlation, inflation, and growth regimes. Regime models may adjust risk budgets but must not override hard risk limits.

Required controls:

- Probabilistic states rather than single-label certainty.
- Hysteresis to prevent rapid switching.
- Independent tail-risk indicators.
- Fail-safe exposure reduction when inputs are stale or invalid.

Reference:
https://www.twosigma.com/articles/a-machine-learning-approach-to-regime-modeling/

### 6. Defined-risk options relative value

Research implied-versus-realized volatility, skew, term structure, calendars, butterflies, vertical spreads, and crash-protected premium harvesting.

Prohibited in initial research:

- Unhedged naked short options.
- Unlimited-loss structures.
- Martingale averaging.
- Strategies evaluated without realistic bid-ask spreads, assignment, exercise, dividends, and volatility-surface dynamics.

### 7. Crypto basis and funding carry

Research market-neutral spot-versus-futures and perpetual-funding trades only when both legs, collateral, custody, and liquidation controls are independently verified.

Required controls:

- Exchange and counterparty limits.
- Funding-rate persistence filters.
- Basis convergence and liquidation stress tests.
- Collateral fragmentation and stablecoin depeg scenarios.
- No assumption that historical carry is risk-free.

References:
https://www.bis.org/publ/work1087.pdf
https://www.cmegroup.com/markets/cryptocurrencies/cryptocurrency-basis-watch-and-implied-rate-tool.html

### 8. Adaptive market making

Research inventory-aware quoting based on Avellaneda-Stoikov and later multi-asset extensions.

This strategy requires direct order-book access, predictable latency, cancel/replace support, fill telemetry, queue-position modeling, and robust adverse-selection controls. It is not eligible for deployment through a retail interface without these capabilities.

### 9. Machine-learning signal ensemble

Use interpretable baselines first, then test gradient boosting, calibrated classifiers, temporal models, and representation learning.

Required controls:

- Purged and embargoed cross-validation.
- Strict separation of training, validation, and final holdout data.
- Feature timestamps and leakage audits.
- Stability across assets, regimes, and cost assumptions.
- Model uncertainty and drift monitoring.
- A simple benchmark must remain the promotion baseline.

## Recommended research portfolio

These are research-budget weights, not capital allocations:

| Sleeve | Research weight |
| --- | ---: |
| Multi-speed trend | 30% |
| Quality-value-momentum | 20% |
| Statistical arbitrage | 15% |
| Defined-risk options | 10% |
| Crypto momentum / mean reversion | 10% |
| Regime and risk overlays | 10% |
| Execution research | 5% |

## Current-system constraints

Before any new strategy can request live activation:

1. Broker identity, account type, execution source, and external order ID must be recorded for every order.
2. `LIVE` status must never coexist with paper-broker routing.
3. Primary-brain failure must not increase risk.
4. Empty or structurally incomplete provider responses must be rejected.
5. The confirmed capital deposit must be separated from trading profit.
6. Existing positions must remain untouched by research code.
7. Strategy promotion requires explicit owner approval after independent validation.
