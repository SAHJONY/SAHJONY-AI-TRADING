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
(Wheel, Ladder) → Risk Officer → Execution Trader → Treasurer/CRM → Reporter.

## AI brain & counsellors (`intelligence/ai_brain.py`)
- PRIMARY: Claude (`claude-fable-5`, Anthropic SDK) — Chief Investment Strategist.
- COUNSELLORS: OpenAI (GPT) + Grok (xAI) — advisory inputs to the brain.
Advisory overlay only: nudges conviction + global risk posture; never invents trades.
Gated by `AI_BRAIN_ENABLED` + provider keys; degrades to neutral if unavailable.
