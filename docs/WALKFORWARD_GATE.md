# Walk-forward evidence gate & auto-demotion

Fail-closed by design: **missing evidence blocks advancement.** No strategy
reaches live capital on backtest alone, on vibes, or on stale artifacts.

## Pipeline stages (`intelligence/promotion_pipeline.py`)

```
research → backtest → walk_forward → paper → shadow → canary → production
```

Each stage's evidence is recorded as a signed, hash-verified artifact
(`ingest_artifact`). The gate checks, in `_evidence_blockers`, require the
exact predecessor evidence flag before the next stage is allowed:

| Target stage | Recorded evidence required (fail-closed) |
|---|---|
| `walk_forward` | `backtest_passed` |
| `paper` | `walk_forward_passed` |
| `shadow` | ≥20 paper observations, paper Sharpe ≥ 0, paper max-DD ≤ 15% |
| `canary` | ≥100 shadow observations, shadow Sharpe ≥ 0.25, shadow max-DD ≤ 10%, **explicit human canary approval** |
| `production` | ≥50 canary observations, independent risk review, **explicit human production approval** |

Additional automatic fail-closed gates on every artifact ingest:
data quality ≥ 98%, operational health ≥ 95%, stage drawdown ceilings
(`MAX_DRAWDOWN`: backtest 25% / walk_forward 20% / paper 15% / …),
calibration error ≤ 15% in shadow/canary.

No human approval can be implied or automated — `approvals` entries are keyed
per stage and missing entries are blockers. Canary/production are disabled by
host policy unless explicitly enabled (`allow_canary` / `allow_production`).

## Auto-demotion (`intel/self_review.py`)

The nightly self-review grades each strategy on decayed realized accuracy
(`intel/council_calibration.py`, same math as the Hermes council scorecard).
A strategy whose rolling accuracy falls below threshold (`min_accuracy`, 0.48)
with enough observations (`min_observations`, 50) is automatically demoted one
stage (e.g. production → canary → paper) via `PromotionPipeline.demote()`
with the reason recorded in the promotion audit log (`promotion_events`).

Auto-demotion is **bounded**: it only moves strategies DOWN the ladder, never
up; it never touches the risk envelope ($10/order, 12%/position, 70% deployed,
10% daily halt), the arming chain, or credentials. It can be killed with
`AUTO_DEMOTE_ENABLED=false`.

## Stale-evidence invalidation

`SelfReview._review_strategies` invalidates a demoted strategy's advancement
evidence **for real**: after `demote()` it deletes the evidence keys and stage
approvals that gate every stage above the new target
(`walk_forward_passed`, paper/shadow/canary observations, Sharpe, drawdown,
calibration, risk-review, and human approvals). With those keys gone, the
gate's predecessor checks (`_evidence_blockers`) fail on any re-promotion
attempt — re-promotion requires **fresh recorded walk-forward evidence**,
fail-closed. The invalidated keys are recorded in the demotion entry
(`evidence_invalidated`). The desk's Hermes `strategy_weights` simultaneously
trim that desk's capital (×0.70–×1.15, losers trimmed, never switched off).

## Human surface

Every demotion is recorded with: strategy, from→to stage, rolling accuracy,
observations, window, reason, UTC timestamp — visible in the dashboard's
"Morning brief & system health" panel (`status.json` → `self_review`) and in
`public/daily_brief.md`.
