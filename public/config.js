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
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFhcnNrcWpnZGF0ZWZ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI5ODMyMTAsImV4cCI6MjA3ODU1OTIxMH0._4DdIuu9qP82pbwzgVPHol8SWmS6ZBPNowwrPHLt5Fs",
  OWNER_EMAIL: "sahjonycapitalllc@outlook.com",

  // SAHJONY CONNECT is a first-party communications surface. Trading OS embeds
  // only exact, approved CONNECT session paths from this origin; arbitrary URLs
  // are rejected by public/connect-bridge.js. This is a public origin, not a secret.
  CONNECT_ORIGIN: "https://sahjony-connect.vercel.app",

  // Optional FREE key from finnhub.io → live stock quotes + financial news.
  // Crypto (CoinGecko) and fallback news (GDELT) need NO key.
  //
  // LEAVE THIS BLANK IN GIT. This repository is public, so a key committed here
  // is a published key. It is injected at deploy time from the Vercel env var
  // FINNHUB_API_KEY by scripts/build_public_config.sh (vercel.json buildCommand).
  //
  // Note this is a browser key either way: on a static site anything the page
  // calls Finnhub with is visible to whoever loads the dashboard. Injecting it
  // keeps it out of git history and out of the public repo — it does not make it
  // private. Scope/rotate it accordingly, or proxy Finnhub through api/ if it
  // ever needs to be genuinely secret.
  FINNHUB_API_KEY: "",
  // Optional extra news wires (the Financial Wire aggregates every one that's set,
  // on top of the always-on free GDELT + Finnhub feeds). Free tiers available:
  //   Marketaux  → marketaux.com  (entity-tagged market news; free tier + paid)
  //   CryptoPanic→ cryptopanic.com (crypto headlines; free)
  MARKETAUX_API_KEY: "",
  CRYPTOPANIC_API_KEY: ""
};

// Load the CONNECT bridge without modifying the integrity-pinned trading shell.
// The bridge is deliberately isolated from order/execution code.
(() => {
  if (document.querySelector('script[data-sahjony-connect-bridge]')) return;
  const s = document.createElement('script');
  s.src = './connect-bridge.js';
  s.defer = true;
  s.dataset.sahjonyConnectBridge = '1';
  document.head.appendChild(s);
})();
