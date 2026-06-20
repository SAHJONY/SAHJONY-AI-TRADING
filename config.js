// SAHJONY dashboard — Supabase connection for LIVE CONTROLS.
// All values are PUBLIC-safe: the anon key only works through Row-Level Security
// (each owner sees only their own desks). Leave SUPABASE_* blank to run the
// dashboard as a read-only static snapshot.
//
// OWNER_EMAIL (optional): lock login to a single account — anyone else is
// refused even with valid Supabase credentials. Leave "" to allow any
// authenticated user (RLS still scopes data to that user).
//
// Find the Supabase values in Supabase → Project Settings → API.
window.SAHJONY_CONFIG = {
  SUPABASE_URL: "https://awzczbaarskqjgdatefv.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF3emN6YmFhcnNrcWpnZGF0ZWZ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI5ODMyMTAsImV4cCI6MjA3ODU1OTIxMH0._4DdIuu9qP82pbwzgVPHol8SWmS6ZBPNowwrPHLt5Fs",
  OWNER_EMAIL: "sahjonycapitalllc@outlook.com",
  // Optional FREE key from finnhub.io → live stock quotes + financial news.
  // Crypto (CoinGecko) and fallback news (GDELT) need NO key.
  FINNHUB_API_KEY: ""
};
