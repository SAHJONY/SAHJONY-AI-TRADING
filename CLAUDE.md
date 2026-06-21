# SAHJONY CAPITAL LLC — working agreement (read first)

An autonomous, **paper-trading** quant desk: a workforce of agents (12-persona
Intelligence Council + an AI brain) trading an Alpaca paper account, with a
native SQLite CRM/database and a static owner dashboard deployed on Vercel.

## Standing directives
- **Safety first, always paper.** Default mode is offline-sim (zero real orders).
  Live mode targets Alpaca **paper**. Never wire real-money trading without an
  explicit, deliberate change. The Risk Officer's hard ceilings in `config.py`
  (`HARD_MAX_ALLOCATION_PCT`, `HARD_MAX_TOTAL_DEPLOYED_PCT`) must never be raised
  casually — `.env` can only tighten them.
- **Be honest about capability.** The 12 "firm" personas are transparent, public-
  domain estimators (momentum, mean-reversion, VPIN, regime/HMM, cointegration,
  residual-alpha regression). They are NOT those firms' proprietary models and
  are not a profit guarantee. Keep marketing language out of code and docs.
- **Fault isolation.** Every external call (broker, LLM, voice, DB) is wrapped so
  a failure logs and degrades gracefully — the trading loop never crashes.
- **No secrets in the repo.** All keys via `process`/`os.environ`, set in `.env`
  (gitignored) or Vercel env. `public/status.json` is the only committed runtime
  artifact and is secret-free (names + set/missing booleans only).

## Architecture (clean layering)
- **Domain (pure):** `intelligence/engines.py` (NumPy math), `intelligence/agents.py`
  (council), `strategies/*` (decision engines emitting `OrderIntent`s — no I/O).
- **Application:** `workforce/workforce.py` (the Firm orchestrates a cycle),
  `risk/risk_engine.py` (gatekeeper), `intelligence/ai_brain.py` (LLM overlay).
- **Adapters (I/O):** `utils/alpaca_client.py` (broker/sim), `database/db.py`
  (SQLite), `utils/notify.py` (Bland.ai voice), `workforce/reporter.py` (dashboard).
- **Entry:** `main.py`. Strategies never touch the broker or DB — the Execution
  Trader does. Keep it that way.

## Verify like this
- `python -m py_compile $(git ls-files '*.py')` — syntax gate.
- `python -m tests.test_dry_run` — 8 offline cycles; asserts state/DB/status update.
- `python main.py --cycles 8` — regenerates `public/status.json` for the dashboard.
- The dashboard is browser-rendered; `status.json` is the contract between the
  Python engine and `public/index.html` — keep the schema in `reporter.py` in sync.

## Deploy
- `public/` is a zero-build static site. Pushing to the linked Vercel project
  deploys it. The trading loop runs locally/cron (NOT on Vercel serverless).
- Model IDs: Claude brain default is `claude-opus-4-8` (adaptive thinking). If you
  touch the Anthropic call, consult the claude-api reference — don't guess the SDK.

## AI brain hierarchy (owner's directive)
- **Primary engine / brain:** Claude (`anthropic` SDK).
- **Secondary engines / counsellors:** OpenAI (GPT) + Grok (xAI) + Gemini
  (Google), advisory only. Gemini uses its OpenAI-compatible endpoint and the
  `GEMINI_API_KEY` (or `GOOGLE_API_KEY`).
- **Always latest model (autonomous):** with `AUTO_UPDATE_MODELS=true` (default),
  `utils/model_registry.py` resolves each provider's newest model at run time
  (latest **Opus** for Claude; latest flagship GPT/Grok/Gemini), cached ~daily,
  and falls back to the configured `*_MODEL` default whenever the lookup can't run.
