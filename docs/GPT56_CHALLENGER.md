# GPT-5.6 Quant Challenger (Research Only)

This challenger is deliberately isolated from order execution. It exists to test whether a GPT-5.6-assisted research layer adds measurable value over the current champion without changing broker behavior.

## Pipeline

1. `intelligence/market_state.py` compresses price and optional microstructure data into a bounded market snapshot.
2. `intelligence/quant_ensemble.py` computes transparent local signals.
3. `intelligence/monte_carlo.py` runs bootstrap simulations locally and returns aggregate risk/return statistics only.
4. `intelligence/gpt56_shadow_reviewer.py` optionally asks GPT-5.6 to classify regime, uncertainty, disagreement, and signal fragility using strict Structured Outputs.
5. `intelligence/gpt56_challenger_pipeline.py` records neutral research observations in the existing `ShadowPipeline`.

## Safety boundary

The challenger does **not** emit trade direction, order intents, leverage, position sizes, or broker actions. `record_shadow()` always writes `adjustment=0.0` and `risk_multiplier=1.0`; research output is stored only in metadata for later evaluation.

No module in the challenger imports `execution`, `utils.broker`, or broker adapters.

## Feature flags

The OpenAI review is off by default:

```bash
GPT56_CHALLENGER_ENABLED=false
GPT56_CHALLENGER_MODEL=gpt-5.6
GPT56_CHALLENGER_REASONING=medium
GPT56_CHALLENGER_TIMEOUT_SECONDS=45
```

`OPENAI_API_KEY` is required only when the reviewer is enabled. If disabled or unavailable, the pipeline still runs the deterministic snapshot, ensemble, and Monte Carlo stages and returns a conservative research review.

## Promotion criteria

This branch should remain a challenger until out-of-sample shadow evidence is sufficient. Compare it with the existing champion on net expectancy after costs, Sharpe/Sortino, drawdown, CVaR, calibration, latency, schema validity, and stability across regimes.

Promotion must never be inferred from a single profitable window. The existing execution and hard-risk gates remain authoritative.
