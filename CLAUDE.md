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
- `python -m tests.test_optimizations` — locks in the hot-path work (expanding-vol
  equivalence, per-cycle quote cache, DB indices, recorded-feed bars).
  See `docs/system_review.md`.
- `python -m tools.position_audit` — audits every desk's books against the risk
  invariants (over-cap, unpriceable, sign/state contradiction, insolvent).
  Read-only, exits 1 on any finding so it can gate a pipeline. Run it before
  trusting any desk's P&L: three of its four checks were failing silently on
  `desks/paper` and `desks/stocks` while both dashboards rendered normally.
- `python -m tools.remediate_positions --home desks/paper` — prints the orders that
  would flatten every invariant-violating position. **Dry-run by default;
  `--apply` is the only way to send an order.** Routes through the desk's own
  broker adapter and journals each fill to the audit ledger. It refuses to touch
  a position the venue cannot price — selling into an unknown price is guessing.
- `python -m pytest tests/ -q` — the whole suite (343 tests). Needs `pytest`,
  `python-dotenv` and `alpaca-py`; without `alpaca-py`, `test_historical_data`
  fails 3 tests on `ModuleNotFoundError`, which is a missing dependency and not
  a regression.
- `requirements.txt` is the **desk's** runtime, and Vercel installs it verbatim
  into the `api/*.py` serverless bundle (500 MB ceiling). Research-only packages
  go in `requirements-backtest.txt`; `api/requirements.txt` is intentionally
  empty because those functions are stdlib-only. Adding a heavy dependency to
  the root file breaks the deployment, not just the install.
- `python main.py --cycles 8` — regenerates `public/status.json` for the dashboard.
  **Do not commit what this writes from a feature branch.** It also rewrites
  `public/knowledge.json` and `public/ai_shadow.json`; all three are owned by the
  *running* desk on `master`. Committing offline-sim output overwrites real
  accumulated state (the per-pair hit rates the desk weights itself with, the
  shadow-eval observation counts) and turns every later merge into a conflict
  whose "ours" side is simulated noise. Note the test suite writes them too, not
  just `main.py`. After verifying, restore all three:
  `git checkout -- public/status.json public/knowledge.json public/ai_shadow.json`.
- The dashboard is browser-rendered; `status.json` is the contract between the
  Python engine and `public/index.html` — keep the schema in `reporter.py` in sync.

## Deploy
- `public/` is a zero-build static site. Pushing to the linked Vercel project
  deploys it. The trading loop runs locally/cron (NOT on Vercel serverless).
- Model IDs: Claude brain default is `claude-fable-5` (thinking always on; steer
  depth via `output_config.effort`; server-side refusal fallback to `claude-opus-4-8`).
  If you touch the Anthropic call, consult the claude-api reference — don't guess the SDK.

## Analyst toolkit (Claude Code sessions on this repo)
- `.claude/settings.json` registers Anthropic's `claude-for-financial-services`
  plugin marketplace and enables `financial-analysis` (/comps, /dcf, /lbo) and
  `equity-research` (/earnings, /model-update) for OWNER research on names the
  desk trades. These are human-review drafting tools — they are NOT wired into
  the autonomous loop, make no recommendations, and execute nothing. Keep it
  that way: the trading cycle stays deterministic quant + the advisory AI brain.
- `.mcp.json` registers the `financial-datasets` MCP server (needs
  `FINANCIAL_DATASETS_API_KEY` in the environment — never in the repo). Same
  status as the plugins above: it is a tool for the **Claude Code session**, not
  for the desk. The trading loop is Python on GitHub Actions and does not speak
  MCP, so this can never become a live feed. What it *can* do is fetch bulk
  history once, which a session then commits as a CSV for `backtest/` — and bulk
  history is exactly what the desk lacks. As of 2026-08-02 both
  `mcp.financialdatasets.ai` and `api.financialdatasets.ai` return **403 at the
  egress proxy**, so it is configured but unreachable from a sandboxed session.

## AI brain hierarchy (owner's directive)
- **Primary engine / brain:** Claude (`anthropic` SDK).
- **Secondary engines / counsellors:** OpenAI (GPT) + Grok (xAI) + Gemini
  (Google), advisory only. Gemini uses its OpenAI-compatible endpoint and the
  `GEMINI_API_KEY` (or `GOOGLE_API_KEY`).
- **Always latest model (autonomous):** with `AUTO_UPDATE_MODELS=true` (default),
  `utils/model_registry.py` resolves each provider's newest model at run time
  (latest **Opus** for Claude; latest flagship GPT/Grok/Gemini), cached ~daily,
  and falls back to the configured `*_MODEL` default whenever the lookup can't run.
