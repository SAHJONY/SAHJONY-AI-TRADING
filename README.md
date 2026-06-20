# SAHJONY CAPITAL LLC — Autonomous Agentic Trading Desk

A production-grade, fault-tolerant **paper-trading** quant system run by a
cooperating workforce of agents, with a native CRM + SQLite database, an AI brain
(Claude) advised by OpenAI and Grok counsellors, Bland.ai voice comms, and an
owner agentic dashboard deployable to Vercel.

> **Paper trading only.** With no credentials the desk runs in **offline-sim**
> mode (synthetic data, zero real orders). It targets an Alpaca **paper** account
> when keys are present. Nothing here is investment advice, and no bot guarantees
> profit — the "intelligence" is transparent, well-known estimators, not magic.

## Architecture

```
 main.py ──▶ Firm (workforce/) ──▶ one trading cycle
   │
   ├─ Research Desk        convenes the 12-agent Intelligence Council per ticker
   ├─ Chief Strategist     AI Brain (Claude) + OpenAI & Grok counsellors  (advisory overlay)
   ├─ Portfolio Manager    strategy assignment + conviction-scaled budget
   ├─ Wheel Options Desk    CSP → assignment → covered call
   ├─ Equity Ladder Desk    ratchet trailing stop + averaging-in
   ├─ Risk Officer          hard per-position & total-deployed gatekeeper
   ├─ Execution Trader      Alpaca paper / offline-sim, applies fills to state
   ├─ Treasurer + CRM       SQLite ledger (trades, equity curve, investors/AUM)
   └─ Reporter              public/status.json (owner dashboard) + console board
```

- **Intelligence:** `intelligence/engines.py` (Black-Scholes, IV, OLS alpha/beta,
  RSI/MACD, VPIN order-flow toxicity, a 2-state Gaussian regime model, Engle-Granger
  cointegration — pure NumPy) feeds the 12 personas in `intelligence/agents.py`.
- **AI brain:** `intelligence/ai_brain.py` — Claude (`claude-opus-4-8`) via the
  official Anthropic SDK is the primary engine; OpenAI + Grok are counsellors. It
  nudges conviction and a global risk posture; it never invents trades.
- **Database/CRM:** `database/db.py` (native SQLite) + `crm/crm.py`.
- **Dashboard:** `public/index.html` — static, zero-build, reads `status.json`.

## Quick start

```bash
pip install -r requirements.txt        # or run offline-sim with just numpy+pandas+dotenv
cp .env.template .env                   # fill in keys to go live (optional)

python main.py --cycles 8               # dry-run: 8 sim cycles, walks the market
python main.py --once                   # one cycle (cron entry point)
python -m tests.test_dry_run            # verification

# CRM
python -m crm.crm add --name "Jane Doe" --email jane@x.com --kind investor
python -m crm.crm contribute --id 1 --amount 50000 --nav 1.0
python -m crm.crm summary

# Voice comms test (needs VOICE_API_KEY + OWNER_PHONE)
python -m utils.notify --test
```

## Going live (Alpaca paper)

1. Create a free **paper** account at alpaca.markets, paste keys into `.env`
   (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER=true`).
2. (Optional) enable the AI brain: `AI_BRAIN_ENABLED=true` + `ANTHROPIC_API_KEY`
   (and `OPENAI_API_KEY` / `XAI_API_KEY` for counsellors).
3. (Optional) voice alerts: `VOICE_ALERTS=true` + `VOICE_API_KEY` + `OWNER_PHONE`.
4. Schedule it: `bash scripts/install_scheduler.sh` (every 15 min, market hours).

The **Risk Officer** enforces hard ceilings the `.env` can never widen
(`HARD_MAX_ALLOCATION_PCT` etc. in `config.py`).

## Dashboard (Vercel)

`public/` is a static, zero-build site. Pushing this repo deploys it to the
linked Vercel project. The **Environment** page lets the owner add/delete vars
and generates the `.env` + `vercel env` commands to apply them (the static page
never sees secret values — only which are set). Regenerate the data snapshot
with `python main.py --cycles 8` (writes `public/status.json`) and redeploy.
