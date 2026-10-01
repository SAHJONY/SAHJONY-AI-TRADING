# Safe LLM Council Integration

## Decision

Adopt the multi-model council *architecture pattern* without copying upstream source.
The referenced `karpathy/llm-council` repository is useful as inspiration, but at the
time of review its repository root did not expose a license file. This integration is
therefore an independent implementation.

## Purpose

The council improves research quality by adding three stages before an optional small
signal tilt:

1. Independent first opinions from multiple models.
2. Anonymized peer review and ranking.
3. Chairman synthesis with explicit uncertainty and invalidation conditions.

It is not an execution engine.

## Safety boundaries

- Feature flag: `SAHJONY_LLM_COUNCIL_ENABLED=false` by default.
- Research/shadow only.
- Minimum 3 independent models; maximum 7.
- Maximum council influence on an existing normalized signal: 15% and confidence-scaled.
- Council output cannot specify order quantity, notional, leverage, or broker route.
- The council cannot place orders or call broker adapters.
- Existing deterministic risk controls, Kelly sizing limits, exposure limits, circuit
  breakers, and kill switches remain authoritative and downstream.
- A council result is explicitly marked `execution_blocked=true`.

## Provider integration

`LLMCouncil` is provider-agnostic. Existing provider clients should be wrapped as
simple callables `(prompt: str) -> str`. Credentials remain in the existing secret
management layer; this module reads no provider API keys and performs no network I/O.

Suggested model diversity is one frontier model from at least three independent model
families/providers rather than multiple variants of the same model. Provider failures
should be handled by the existing provider layer and the council should fail closed if
fewer than three usable models remain.

## Recommended pipeline placement

```text
market data / research
        ↓
existing specialist agents
        ↓
LLM Council (shadow research only)
        ↓
bounded signal tilt (0–15%, confidence scaled)
        ↓
existing consensus engine
        ↓
Institutional Kelly / deterministic risk engine
        ↓
execution eligibility + broker controls
```

The council must never be inserted after the hard risk engine and must never receive a
direct broker client.

## Promotion criteria

Keep in shadow mode until all conditions hold over a statistically meaningful sample:

- Council hit rate exceeds the current AI-consensus baseline after fees/slippage.
- Brier/calibration score improves versus the baseline.
- No increase in max drawdown attributable to council tilts.
- No execution-boundary violations.
- Provider cost and latency remain inside operational budgets.
- At least 500 adjudicated observations across multiple market regimes before any
  consideration of promotion.

Even after promotion, retain the 15% influence cap unless a separate risk-reviewed PR
changes it with evidence.
