# Arming the 24/7/365 Robinhood Crypto bot (REAL MONEY)

This turns the autonomous desk from paper (Alpaca) into a **live, round-the-clock
crypto trader** on Robinhood's **official** Crypto API, running on GitHub Actions
every 15 minutes — no computer needs to stay on.

## ⚠️ Read first — the honest truth
- This desk has **no proven trading edge**. The council uses transparent public
  signals; the AI overlay is not a market predictor. A small autonomous crypto
  bot most likely **bleeds slowly after fees**. Only risk money you can lose.
- Robinhood Crypto has **no sandbox** — every armed order moves real money.
- Everything below is **already built, tested, and merged**. Until you complete
  these steps the desk stays on Alpaca **paper**; even with `BROKER=robinhood_crypto`
  set, it runs **dry-run** (prices live, places nothing) until BOTH gates are on.
- Stocks are intentionally **not** automated (no official RH stock API; the
  unofficial route risks an account lockout). Crypto only.

## Guardrails already in place
- Two independent arming gates: `ROBINHOOD_LIVE=true` **and** the
  `LIVE_TRADING_ACK` secret = `I_UNDERSTAND_REAL_MONEY`. Miss either → dry-run.
- Per-order notional hard cap: `ROBINHOOD_MAX_ORDER_USD` (start at **$10**).
- Whole-account sizing capped by `TRADING_CAPITAL` (start at **$25**) + the risk
  engine's per-position / total-deployed / drawdown ceilings.
- `confirm_live()` prints an armed banner each run (no interactive hang in CI).

---

## Step 1 — Generate Robinhood Crypto API credentials (only you can do this)
1. In the Robinhood app/site, go to **Account → Crypto → API** (Robinhood Crypto
   API keys). Create a key. It gives you:
   - an **API key** (a UUID-like string), and
   - a **base64 Ed25519 PRIVATE-KEY SEED** — a single line, **not** a PEM block
     (no `-----BEGIN…-----`). If your tool exports a 64-byte key, the first 32
     bytes (the seed) are what we use.
2. Keep both secret. Never paste them into chat or commit them.

## Step 2 — Fund the Robinhood **crypto** wallet
Move ~**$25** into Robinhood crypto buying power (the equity/Agentic $25 cannot
trade crypto — separate wallet).

## Step 3 — Set GitHub **Secrets** (repo → Settings → Secrets and variables → Actions → Secrets)
Or via CLI (run each with the `!` prefix so it executes in this session):
```
! gh secret set ROBINHOOD_API_KEY --repo SAHJONY/SAHJONY-AI-TRADING
! gh secret set ROBINHOOD_PRIVATE_KEY --repo SAHJONY/SAHJONY-AI-TRADING
! gh secret set LIVE_TRADING_ACK --repo SAHJONY/SAHJONY-AI-TRADING --body 'I_UNDERSTAND_REAL_MONEY'
```
(The first two prompt for the value so it isn't echoed.)

## Step 4 — Set GitHub **Variables** (same page → Variables tab)
```
! gh variable set BROKER --repo SAHJONY/SAHJONY-AI-TRADING --body 'robinhood_crypto'
! gh variable set ROBINHOOD_LIVE --repo SAHJONY/SAHJONY-AI-TRADING --body 'true'
! gh variable set ROBINHOOD_MAX_ORDER_USD --repo SAHJONY/SAHJONY-AI-TRADING --body '10'
! gh variable set TRADING_CAPITAL --repo SAHJONY/SAHJONY-AI-TRADING --body '25'
! gh variable set TICKERS --repo SAHJONY/SAHJONY-AI-TRADING --body 'BTC/USD,ETH/USD,SOL/USD,LTC/USD'
```
(`gh variable set` needs only `repo` scope — no `workflow` scope required.)

## Step 5 — Apply the workflow change (needs the web editor)
The git token can't push `.github/workflows/*`. Open the workflow in GitHub's web
editor, **select-all → replace** with the contents of
[`docs/deploy/desk.yml`](./desk.yml), and commit to `master`:
> https://github.com/SAHJONY/SAHJONY-AI-TRADING/edit/master/.github/workflows/desk.yml

(That adds `BROKER` + the Robinhood env wiring; defaults are unchanged.)

## Step 6 — Verify auth read-only (moves no money)
Locally (after fixing the malformed line in your `.env` — Step 8):
```
! .venv/bin/python -m scripts.robinhood_check
```
Exit 0 = signing works against your real account. Fix any 401 before arming.

## Step 7 — First live run
Trigger the desk once from **Actions → “SAHJONY desk (scheduled)” → Run workflow**
(or wait ≤15 min for the cron). Watch the logs:
- Unarmed/misconfigured → `robinhood-dryrun`, "would place …", nothing moves.
- Fully armed → the "LIVE REAL-MONEY TRADING ARMED" banner, then real orders
  (each ≤ `$10`, gated by conviction + risk caps). It now trades 24/7/365.

---

## 🔴 Kill switch (disarm instantly — any ONE of these)
- `! gh variable set ROBINHOOD_LIVE --repo SAHJONY/SAHJONY-AI-TRADING --body 'false'`  → back to dry-run
- `! gh variable set TRADING_HALT --repo SAHJONY/SAHJONY-AI-TRADING --body 'true'`  → halts new-risk orders
- `! gh variable set BROKER --repo SAHJONY/SAHJONY-AI-TRADING --body 'alpaca'`  → back to paper
- Or delete the `LIVE_TRADING_ACK` secret.

## Step 8 (housekeeping) — fix the local `.env`
Line 8 is a stray `-----END PRIVATE KEY-----` (a malformed multi-line key) that
breaks local `python-dotenv` parsing. Make `ROBINHOOD_PRIVATE_KEY` a single-line
base64 seed and remove the PEM footer. This only affects local runs, not CI/prod.
