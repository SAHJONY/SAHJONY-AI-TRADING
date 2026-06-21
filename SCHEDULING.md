# Running the desk on a schedule (cloud) & paper trading

The trading loop does **not** run on Vercel — Vercel only hosts the dashboard.
To keep the desk running on its own (and the public dashboard fresh) without an
always-on computer, this repo ships a **GitHub Actions** schedule:
`.github/workflows/desk.yml`.

It advances one cycle every 15 minutes during the US session (Mon–Fri), commits
the secret-free `public/status.json`, and Vercel redeploys — so anyone you share
the link with (family/friends) always sees current numbers.

## Safety ladder (unchanged)

| Setup | What it does |
|------|---------------|
| **No secrets** (default) | `offline-sim` — zero orders, pure simulation. The dashboard just stays alive. |
| **Alpaca paper keys** | Trades the **real market on Alpaca PAPER** — live prices, **fake money**. |
| **Real money** | **Never enabled from CI.** `LIVE_TRADING_ACK` is intentionally left unset in the workflow. |

## Turn on paper trading (2 secrets)

1. Create a free **Alpaca paper** account → API keys (paper).
2. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `ALPACA_API_KEY` = your paper key (`PK…`)
   - `ALPACA_SECRET_KEY` = your paper secret
   - *(optional)* `ANTHROPIC_API_KEY` to switch on the Claude advisory brain
   - *(optional)* repo **Variable** `TICKERS` e.g. `AAPL,MSFT,NVDA,SPY`
3. That's it. The next scheduled run (or **Actions → SAHJONY desk → Run workflow**)
   trades on Alpaca paper. `ALPACA_PAPER` is hard-set to `true` in the workflow, so
   it can never place real-money orders.

To pause it: GitHub → **Actions → SAHJONY desk → ··· → Disable workflow**.

## State continuity

`state.json` and the SQLite DB are gitignored runtime artifacts. The workflow
caches them between runs (`actions/cache`) so the equity curve, capital ledger and
open positions stay consistent. Only the secret-free `public/status.json` is
committed back.

## Alternative: live owner view via the multi-tenant worker

For a logged-in, real-time owner experience (data streamed from Supabase instead
of the committed snapshot), run `python -m worker.run` on a scheduler with
`SUPABASE_DB_URL` + `SECRET_ENCRYPTION_KEY` (see `worker/.env.example`). The
dashboard reads `desk.last_status` live when you're signed in. The Actions
schedule above is the simplest path and is what keeps the **public** view fresh.
