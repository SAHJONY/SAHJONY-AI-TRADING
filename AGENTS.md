# Agents — SAHJONY CAPITAL LLC

## The 12-persona Intelligence Council (`intelligence/agents.py`)
Each emits a directional score (−1…+1) + confidence; the council weights them
into a long-conviction (0–1) and a risk multiplier.

1. Citadel Systematic — trend/momentum
2. Two Sigma Backtest — statistical expectancy (Sharpe/win-rate)
3. Bridgewater Risk — risk parity / vol targeting
4. Renaissance Patterns — mean-reversion (z-score, autocorrelation)
5. Goldman Technical — RSI + MACD
6. JPMorgan Fundamental — valuation/trend proxy
7. D.E. Shaw Options — IV rank / premium favorability
8. AQR Factor — momentum + value + quality composite
9. Citadel Securities MM — VPIN order-flow toxicity
10. Millennium Pod — residual alpha vs benchmark, beta-neutrality
11. Renaissance Medallion — 2-state Gaussian regime (HMM-like) + cointegration
12. Sovereign Wealth — secular macro / accumulate-dips

> These are transparent public-domain estimators, not the firms' real models.

## Operational workforce (`workforce/workforce.py`)
Research Desk → Chief Strategist (AI Brain) → Portfolio Manager → Strategy Desks
(Wheel, Credit Spreads, Ladder; + Day/Forex and Copy desks) → Risk Officer →
Execution Trader → Treasurer/CRM → Reporter.
Volatility targeting (`RiskEngine.vol_scalar`, `VOL_TARGET_ANNUAL`, default 20%):
realized portfolio vol above target scales every new-position budget down
([×0.5, ×1.0] — de-risks only, never levers up); hard ceilings apply on top.
Equities rotate wheel/ladder/spread deterministically; an open position always
finishes under the desk that opened it (position-first routing). The Credit
Spread Desk (`strategies/credit_spreads.py`) sells bull put spreads — max loss
= (width − credit), known at entry, and that exact number is what the Risk
Officer gates on. `CREDIT_SPREADS_ENABLED=false` restores the 2-way split.

## AI brain & counsellors (`intelligence/ai_brain.py`)
- PRIMARY: Claude (`claude-fable-5`, Anthropic SDK) — Chief Investment Strategist.
- COUNSELLORS: OpenAI (GPT) + Grok (xAI) — advisory inputs to the brain.
Advisory overlay only: nudges conviction + global risk posture; never invents trades.
Gated by `AI_BRAIN_ENABLED` + provider keys; degrades to neutral if unavailable.

## Advisory Board (`intelligence/advisors.py`)
The 6-agent Intelligence Council from the README: Buffett (quality/value),
Munger (discipline), Macro, Growth, Quant — each a transparent price-based
proxy scoring [-1,1] with a rationale — plus a Risk Agent protection gate
(0..1) and a Decision Engine that blends them into a conviction tilt clamped
to ±0.10, gate-scaled (a stressed name never gets a positive nudge). Advisory
only; stacked tilts (alt-data + Hermes + board) are clamped to ±0.20 overall,
and Hermes' data quarantine always wins. `ADVISORS_ENABLED=false` disables.

## Hermes guardian (`intelligence/hermes.py`)
Background agent with a well-defined goal (`HERMES_GOAL`), run before the
strategists each cycle: (1) validates every market feed and QUARANTINES hard
failures (conviction forced to 0 → Risk Officer blocks new risk; exits still
flow); (2) keeps an honest Sharpe/Sortino/drawdown scorecard off the equity
curve; (3) self-improvement — grades the council's realized directional
hit-rate (decayed) into a bounded conviction tilt (±0.10), and re-weights
capital across strategy desks by realized win-rate (×0.70–×1.15; a losing desk
is trimmed, never switched off). Memory lives in state.json (cached across CI
runs) with exponential decay, so the learning loop runs in perpetuity.
Deterministic, transparent, fault-isolated; default ON, `HERMES_ENABLED=false` to disable.
