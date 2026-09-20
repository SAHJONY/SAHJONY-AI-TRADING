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
Pairs / StatArb Desk (`strategies/pairs_trading.py`, `PAIRS`, default
SPY:QQQ + GLD:SLV): market-neutral Engle-Granger spreads — short the rich leg,
long the cheap leg on |z| ≥ 2, exit on reversion (|z| ≤ 0.5), stop on blow-out
(|z| ≥ 4) or time. Legs live under their real symbols with strategy "pairs"
(short = negative shares); core desks skip pairs-owned symbols; the deployed
cap gates on GROSS exposure so shorts consume budget; an orphan leg is closed
immediately. Sim broker supports shorts (negative qty, marked to market).
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

## Brain upgrade — performance-weighted voting, de-risking, memory (`intel/`)
All advisory or de-risk-only; none widen risk caps, emit orders, or touch credentials.

- `council_calibration.py` — decayed per-agent realized accuracy; vote weights
  bounded [0.5, 1.5]; neutral until 20 observations.
- `trade_memory.py` — JSONL post-mortems with explicit unknowns (no invented
  rationale); filter/query + lesson extraction into the knowledge base.
- `dispersion.py` — council disagreement scales conviction down [0.3, 1.0];
  reduction-only, never increases it.
- `anomaly.py` — volatility-shock / extreme-return detection forces conviction
  to 0 for that symbol (stand-down), like Hermes' quarantine.
- `self_review.py` — nightly evidence-based review; lessons → knowledge base,
  and auto-demotion of strategies with sub-threshold rolling accuracy in the
  promotion pipeline (live → canary → paper), with reasons recorded.
- `auto_tune.py` — bounded self-tuning of NON-RISK parameters only, only when
  recorded walk-forward evidence improves; the $10/order, 12%, 70%, 10% halt
  envelope is hard-excluded and unchangeable by the tuner.
- `funding_intel.py` — keyless Hyperliquid (+ Binance fallback) funding/OI;
  9th workforce agent; contrarian advisory tilt bounded ±0.15.
- `options_flow.py` — keyless Deribit BTC options book summary: put/call OI
  ratios, per-expiry put-IV skew, term-structure slope; bounded
  defensive/neutral read, advisory only.
- `congress.py` — keyless STOCK Act PTR disclosure-activity feed (House Clerk
  search + degradable Senate EFD leg); report-level granularity, advisory only.
- `signal_attribution.py` — per-engine signal attribution ledger: snapshots
  every engine's directional input per symbol and grades it against realized
  signed moves at fixed 1h/4h/24h horizons (decayed rankings, 20-observation
  gating). Measurement only — correlational, never a reason to widen risk.
- `correlation.py` — correlation-adjusted exposure reporting, advisory only.
- `diversity.py` — council + portfolio diversity diagnostics, advisory/measurement
  only: bias–variance–covariance decomposition of the 12 persona votes (crowding
  that dispersion.py cannot see — 12 personas agreeing on the same signal are
  one bet), Meucci Effective Number of Bets on the book, decayed pairwise
  vote-correlation matrix, plain-language crowding flags. The Risk Officer may
  READ the effective-bets number; it is never wired into any gate. Short
  decaying vote window and noisy correlation estimates are documented limits —
  it diagnoses crowding, never fixes it.
- `execution_quality.py` — arrival-price vs fill-price slippage JSONL,
  measurement only (maker routing intentionally deferred).
- `tca.py` — Perold implementation-shortfall decomposition per order
  (delay / market impact / timing / opportunity / fees) into a JSONL ledger,
  plus pre-trade vs realized impact-estimate honesty tracking for the
  backtest cost model. Measurement only — it cannot design a better execution
  schedule at $10/order; most legs will print ≈ 0 except opportunity and
  fees, and that is the point.
- `daily_brief.py` — real-data morning brief → `public/daily_brief.md` +
  dashboard panel; never invents figures, marks gaps explicitly.
- `self_heal.py` — watchdog: health states per subsystem, keyless fallback
  chain (venue → CoinGecko → Kraken → Coinbase) with real backoff, circuit
  breaker (resume only after a streak), 3-strike escalation to the owner, and
  an auditable healing log. Never attempts credential repair.
