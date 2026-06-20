-- Enable Supabase Realtime so the dashboard streams desk updates the instant the
-- worker writes them (no polling). RLS still applies to realtime, so each owner
-- only receives changes for their own desks. Safe to run once.
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'desks'
  ) then
    alter publication supabase_realtime add table public.desks;
  end if;
end $$;
