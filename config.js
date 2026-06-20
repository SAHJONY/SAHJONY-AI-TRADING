// SAHJONY dashboard — Supabase connection for LIVE CONTROLS (optional).
// Fill these to enable the Controls tab + live data. Both are PUBLIC-safe:
// the anon key only works through Row-Level Security (owner sees only their own
// desks). Leave blank to run the dashboard as a read-only static snapshot.
//
// Find them in Supabase → Project Settings → API.
window.SAHJONY_CONFIG = {
  SUPABASE_URL: "",       // e.g. https://xxxx.supabase.co
  SUPABASE_ANON_KEY: ""   // the public anon/publishable key (NOT the service role)
};
