# Strategy Promotion Gates

## Purpose

These gates prevent research results, marketing claims, or attractive backtests from becoming live trading instructions without evidence.

## Gate 0 — Isolation

- Research code cannot import or call live order-routing modules.
- Research uses a separate data directory and database namespace.
- Generated artifacts cannot overwrite live state.
- Feature flags default to disabled.
- No test may submit an external order.

## Gate 1 — Data integrity

Required evidence:

- Point-in-time, survivorship-bias-free data where applicable.
- Corporate actions, delistings, funding, dividends, and contract rolls handled.
- Immutable source version or checksum.
- Coverage, missing-data, stale-data, and outlier reports.
- No forward-filled decision-critical values beyond an explicitly justified limit.

Automatic rejection:

- Mutable external dataset without pinning or checksum.
- Timestamp leakage.
- Unexplained zero volatility or impossible prices.
- Results dependent on excluded losing assets or periods.

## Gate 2 — Reproducible baseline

Each candidate must beat appropriate simple baselines after costs:

- Cash or risk-free return.
- Buy-and-hold benchmark.
- Equal-weight portfolio.
- Simple moving-average or momentum rule.
- Existing production strategy where applicable.

The entire experiment must run deterministically from a committed configuration.

## Gate 3 — Realistic execution

Backtests must include:

- Bid-ask spreads.
- Commissions and regulatory fees.
- Slippage as a function of volatility and participation.
- Market impact and capacity.
- Partial fills and rejected orders.
- Borrow and funding costs.
- Option exercise, assignment, dividends, and contract multipliers.
- Exchange outages and stale quotes.

## Gate 4 — Out-of-sample evidence

Minimum requirements:

- Purged walk-forward testing.
- An untouched final holdout.
- Parameter sensitivity analysis.
- Performance across distinct regimes.
- Multiple-testing adjustment or deflated Sharpe where relevant.
- Probability of backtest overfitting analysis for large searches.

No strategy is promoted based on in-sample Sharpe.

## Gate 5 — Risk

Candidate must declare:

- Maximum position and portfolio exposure.
- Expected and stressed drawdown.
- Volatility target.
- Tail loss under gap and liquidity shocks.
- Correlation concentration.
- Risk of ruin.
- Kill-switch and unwind behavior.
- Behavior when models, data, broker, or providers fail.

Hard rule: a dependency failure can only preserve or reduce risk.

## Gate 6 — Shadow execution

- Run without order authority using live market inputs.
- Compare theoretical, quoted, and realistically fillable prices.
- Record latency, rejection, slippage, drift, and missed trades.
- Require stable operation across multiple scheduling boundaries.
- Reconcile every hypothetical decision to its input snapshot.

## Gate 7 — Paper execution

- Use the intended broker's paper environment when available.
- Require order IDs, fills, cancellations, and positions to reconcile.
- Test recovery from duplicate events, restarts, and partial fills.
- Verify that paper and live credentials can never be selected simultaneously.

## Gate 8 — Independent review

Approval package must include:

- Strategy specification.
- Source and data manifest.
- Reproduction command.
- Full results, including losses.
- Benchmark comparison.
- Failure-mode analysis.
- Code and security review.
- Proposed initial risk budget.

## Gate 9 — Owner approval

No strategy receives live authority without explicit owner approval identifying:

- Strategy version and commit.
- Broker and account.
- Instruments allowed.
- Maximum capital and loss limits.
- Start date and rollback plan.

Approval is not transferable to later code or configuration changes.

## Gate 10 — Limited production

Initial activation must use the smallest practical risk budget and include:

- Real-time broker reconciliation.
- Independent heartbeat.
- Stale-data fail-close.
- Provider-failure fail-defensive behavior.
- Daily and cumulative loss limits.
- Automatic suspension on unexplained divergence.

Scaling requires a new review based on realized execution evidence.
