# GO-LIVE — the one checklist

This is the single source of truth for taking SAHJONY from "built" to "trading".
The **software is complete and verified**; what remains are the things only *you*
can do — supply keys, deploy, and arm. Detail lives in [LIVE.md](LIVE.md)
(personal), [SAAS.md](SAAS.md) (family & friends), [MULTI_ACCOUNT.md](MULTI_ACCOUNT.md)
(many desks / 24-7 crypto).

## Prove it's green (anytime)
```bash
bash scripts/readiness.sh
```
Runs the syntax gate, the full test suite (8 Python + UI 36 checks + login 8),
regenerates `public/status.json`, and ends with a read-only broker preflight.
**Exit 0 = safe to run. Places no orders.**

## What is DONE (in the repo, tested)
- ✅ Trading engine: 12-agent council, AI brain (Claude primary; OpenAI/Grok
  counsellors), wheel + trailing-ladder + copy-trading strategies.
- ✅ Safety: hard risk ceilings, daily circuit breaker (latched), kill switch
  (`TRADING_HALT` / `HALT` file), and the deliberate `LIVE_TRADING_ACK` gate with
  a 5-second abort banner. Live is refused unless you opt in twice.
- ✅ Brokers: Alpaca (US equities/options + 24-7 crypto) validated; IBKR and CCXT
  adapters wired behind `BROKER=` (paper/testnet-validate before live).
- ✅ Multi-account: per-desk isolation (`SAHJONY_HOME`), Supabase multi-tenant
  schema + RLS, the cron worker, and **self-service Broker-Keys onboarding** (the
  `set-credential` Edge Function + the dashboard Controls panel).
- ✅ Dashboard: realtime "Parquet" terminal (live crypto/news/macro feeds,
  Supabase live controls + realtime push), owner-only PIN login, PWA + share card.

## What only YOU can do — go-live checklist

### A. Personal paper desk (start here)
- [ ] **Rotate the Alpaca paper keys** that were once pasted in chat (`PK7XVEJI…`)
      — generate fresh ones in the Alpaca dashboard. Never reuse leaked keys.
- [ ] `cp .env.template .env`, set `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`,
      `ALPACA_PAPER=true`. (Optional: `AI_BRAIN_ENABLED=true` + `ANTHROPIC_API_KEY`.)
- [ ] `python main.py --preflight` → must print **READY ✓**.
- [ ] `python main.py --once`, watch a few cycles, then schedule:
      `bash scripts/install_scheduler.sh`.

### B. Owner dashboard on Vercel
- [ ] Confirm `public/config.js` holds only public values (Supabase URL + anon
      key, OWNER_EMAIL, Finnhub free key). **No passwords/secrets — it is public.**
- [ ] Merge to the branch Vercel deploys (`master`) and push **once**
      (free tier = 100 deploys/day; batch changes).

### C. Multi-account (family & friends) — optional
- [ ] Apply the Supabase migrations (`supabase/migrations/000{1,2,3}_*.sql`).
- [ ] Deploy the onboarding function and set its key (same value as the worker):
      ```bash
      supabase functions deploy set-credential
      supabase secrets set SECRET_ENCRYPTION_KEY="$(python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')"
      ```
- [ ] Run the worker on a host (Railway/Render/Fly) with `worker/.env.example`
      filled in, on a cron: `python -m worker.run`.

### D. Going LIVE with real money (only after paper looks right)
- [ ] Fund your Alpaca **live** account; put **live** keys in `.env`.
- [ ] Set `ALPACA_PAPER=false` **and** `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`.
- [ ] `python main.py --preflight` → must show your real equity and **LIVE ARMED**.
- [ ] `python main.py --once` → confirm the 5-second **LIVE REAL-MONEY** banner,
      then let it run. Tighten caps in `.env` first if you want.

> ⚠️ Real money can lose money. The "intelligence" is transparent public-domain
> estimators, not a profit guarantee. Start on paper and only arm live when you
> understand the behavior.
