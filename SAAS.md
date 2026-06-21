# Multi-account (family & friends) — groundwork

This is **phase 2**: letting other people each run their own desk with their own
keys. The personal live path is in [LIVE.md](LIVE.md); build that first.

Decisions locked: **Supabase + Next.js on Vercel**, the Python engine on a
**worker host (cron)**, **paper-default with opt-in live**.

## What exists now (this commit)
- **`supabase/migrations/0001_init.sql`** — multi-tenant schema with Row-Level
  Security. Each user owns their `desks`, encrypted `broker_credentials`,
  `equity_points`, and `trades`. A signup trigger auto-creates a profile + a
  default desk.
- **`worker/`** — the multi-tenant runner. Per active desk it decrypts that
  desk's keys, builds a per-desk `Config`, runs ONE cycle of the existing engine
  (full reuse of `intelligence/`, `strategies/`, `risk/`, `workforce/`), and
  writes state + a dashboard snapshot + equity/trades back to Postgres.
  - `worker/run.py` — cron entry (`python -m worker.run`)
  - `worker/crypto.py` — AES-256-GCM, byte-compatible with the web side
  - `worker/db_pg.py` — service-role Postgres access (bypasses RLS)
- **`supabase/functions/set-credential/`** — a Deno Edge Function that lets a
  signed-in user save their own broker keys **without** a separate Next.js app.
  It AES-256-GCM-encrypts each value server-side (so the browser never holds the
  encryption key) in the exact format `base64(iv) + "." + base64(ct||tag)` that
  `worker/crypto.py` decrypts, then upserts to `broker_credentials` through the
  caller's JWT so RLS pins the write to that user's desk.
- **Dashboard onboarding panel** — `public/index.html` → Controls tab →
  **Broker Keys**. Signed-in users type their Alpaca (and optional Anthropic)
  keys; `saveCredentials()` POSTs them to the Edge Function. The panel only ever
  shows **set / missing**, never a stored value.

## Onboarding a family/friend account (self-service)
1. They open the dashboard and sign in (Supabase Auth). The signup trigger has
   already created their profile + a default desk.
2. **Controls → Broker Keys** → paste Alpaca **paper** keys → SAVE KEYS. The
   Edge Function encrypts and stores them under *their* desk.
3. **Controls → Configuration / Trading Mode** → set tickers, caps, and `paper`.
4. The worker's next pass decrypts their keys and runs their desk. Live trading
   still requires the per-desk `mode=live` + `live_ack` opt-in.

### Deploy the Edge Function (one-time)
```bash
supabase functions deploy set-credential
# 32-byte key, SAME value as the worker's SECRET_ENCRYPTION_KEY:
supabase secrets set SECRET_ENCRYPTION_KEY="$(python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')"
# SUPABASE_URL and SUPABASE_ANON_KEY are injected automatically.
```
The web `public/config.js` needs only the public `SUPABASE_URL` + anon key — the
function URL is derived as `${SUPABASE_URL}/functions/v1/set-credential`.

## Secret handling
Customer keys are stored **encrypted** (AES-256-GCM) in `broker_credentials`.
The web app encrypts on entry with a server-only `SECRET_ENCRYPTION_KEY`; the
worker decrypts with the same key at run time. The browser never sees plaintext
after entry, and the key never enters the repo.
> Production hardening: move to Supabase Vault / a managed KMS with per-tenant
> envelope keys. App-level AES is the MVP floor, not the ceiling.

## Safety: live is gated per desk
A desk only trades real money when `mode='live'` **and** `live_ack=true` **and**
Alpaca keys are present; otherwise the worker falls back to `sim` for that run
(logged, never silently traded) — the same deliberate opt-in as the personal app.

## Still to build (next phases)
- ~~Onboarding form + per-desk dashboard~~ — **done** via the static dashboard's
  Controls tab (auth, Broker Keys, config/mode, live controls) + the
  `set-credential` Edge Function. A full Next.js `web/` app is now optional.
- Deploy the worker on Railway/Render/Fly with a cron schedule.
- Billing / invites for family & friends.

## Env (worker)
```
SUPABASE_DB_URL=postgres://...      # service-role connection (bypasses RLS)
SECRET_ENCRYPTION_KEY=<base64 of 32 random bytes>   # shared with the web app
```
Generate the key: `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`
