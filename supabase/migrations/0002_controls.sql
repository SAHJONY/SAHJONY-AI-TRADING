-- Live controls for the owner dashboard → worker control plane.
-- The dashboard writes these (RLS-protected, owner only); the worker obeys them
-- each cycle. Existing fields already act as controls: `active` (start/stop),
-- `mode` + `live_ack` (arm live), `tickers` / `*_pct` (config). These add the
-- remote kill switch and one-shot commands.

alter table public.desks
  add column if not exists halt boolean not null default false,        -- kill switch
  add column if not exists command text,                               -- 'flatten' | 'resume' | null
  add column if not exists command_issued_at timestamptz,
  add column if not exists command_done_at timestamptz,
  add column if not exists command_result text;

-- (RLS policy desks_owner from 0001 already covers these columns: a user can
--  read/update only their own desks. The worker uses the service role.)
