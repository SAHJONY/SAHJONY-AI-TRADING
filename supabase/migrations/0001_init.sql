-- SAHJONY CAPITAL LLC — multi-tenant SaaS schema (MVP)
--
-- Every row is owned by a Supabase auth user. RLS scopes all access to the
-- owner; the Python worker uses the service-role key (which bypasses RLS) to
-- read every active desk, decrypt its keys, run a cycle, and write results back.
--
-- Customer API keys are stored ENCRYPTED (AES-256-GCM, app-level) in
-- broker_credentials.enc_value. They are encrypted by the Next.js server action
-- on entry and decrypted only inside the worker — never exposed to the browser.
-- (Production hardening: migrate to Supabase Vault / a KMS. See SAAS.md.)

create extension if not exists "pgcrypto";

-- ── profiles (1:1 with auth.users) ──────────────────────────────────────────
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text,
  created_at  timestamptz not null default now()
);

-- ── desks: one trading desk per customer (MVP allows multiple) ───────────────
create table if not exists public.desks (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete cascade,
  name                text not null default 'My Desk',
  -- 'sim' = offline simulation, 'paper' = Alpaca paper, 'live' = Alpaca live.
  -- Default is the safest mode; live requires an explicit opt-in (see below).
  mode                text not null default 'sim' check (mode in ('sim','paper','live')),
  live_ack            boolean not null default false,   -- explicit real-money acknowledgement
  tickers             text[] not null default array['AAPL','MSFT','SPY'],
  benchmark           text not null default 'SPY',
  ai_brain_enabled    boolean not null default false,
  -- risk knobs (still clamped to the engine's HARD ceilings at runtime)
  max_allocation_pct      numeric not null default 0.10,
  max_total_deployed_pct  numeric not null default 0.60,
  min_conviction          numeric not null default 0.55,
  active              boolean not null default true,
  state               jsonb not null default '{}'::jsonb,   -- persisted engine state
  last_status         jsonb,                                -- latest dashboard snapshot
  last_run_at         timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists desks_user_idx on public.desks(user_id);
create index if not exists desks_active_idx on public.desks(active) where active;

-- ── encrypted customer credentials ──────────────────────────────────────────
-- name is the env-style key (ALPACA_API_KEY, ANTHROPIC_API_KEY, …);
-- enc_value is AES-256-GCM ciphertext (base64(iv).base64(ciphertext+tag)).
create table if not exists public.broker_credentials (
  id          uuid primary key default gen_random_uuid(),
  desk_id     uuid not null references public.desks(id) on delete cascade,
  name        text not null,
  enc_value   text not null,
  updated_at  timestamptz not null default now(),
  unique (desk_id, name)
);
create index if not exists creds_desk_idx on public.broker_credentials(desk_id);

-- ── per-desk equity curve (one row per cycle) ───────────────────────────────
create table if not exists public.equity_points (
  id            bigserial primary key,
  desk_id       uuid not null references public.desks(id) on delete cascade,
  ts            timestamptz not null default now(),
  cycle         integer,
  equity        numeric,
  cash          numeric,
  deployed      numeric,
  realized_pnl  numeric,
  premium       numeric,
  mode          text
);
create index if not exists equity_desk_idx on public.equity_points(desk_id, id);

-- ── per-desk trade log ──────────────────────────────────────────────────────
create table if not exists public.trades (
  id          bigserial primary key,
  desk_id     uuid not null references public.desks(id) on delete cascade,
  ts          timestamptz not null default now(),
  cycle       integer,
  symbol      text,
  strategy    text,
  kind        text,
  side        text,
  qty         numeric,
  price       numeric,
  premium     numeric,
  notional    numeric,
  purpose     text,
  reason      text,
  mode        text,
  simulated   boolean default true
);
create index if not exists trades_desk_idx on public.trades(desk_id, id desc);

-- ── Row-Level Security ──────────────────────────────────────────────────────
alter table public.profiles            enable row level security;
alter table public.desks               enable row level security;
alter table public.broker_credentials  enable row level security;
alter table public.equity_points       enable row level security;
alter table public.trades              enable row level security;

-- profiles: owner only
create policy profiles_owner on public.profiles
  for all using (id = auth.uid()) with check (id = auth.uid());

-- desks: owner only
create policy desks_owner on public.desks
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- child tables: access if the parent desk belongs to the user
create policy creds_owner on public.broker_credentials
  for all using (exists (select 1 from public.desks d where d.id = desk_id and d.user_id = auth.uid()))
  with check (exists (select 1 from public.desks d where d.id = desk_id and d.user_id = auth.uid()));

create policy equity_owner on public.equity_points
  for select using (exists (select 1 from public.desks d where d.id = desk_id and d.user_id = auth.uid()));

create policy trades_owner on public.trades
  for select using (exists (select 1 from public.desks d where d.id = desk_id and d.user_id = auth.uid()));

-- ── auto-provision a profile + a default desk on signup ─────────────────────
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
    on conflict (id) do nothing;
  insert into public.desks (user_id, name) values (new.id, 'My Desk');
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
