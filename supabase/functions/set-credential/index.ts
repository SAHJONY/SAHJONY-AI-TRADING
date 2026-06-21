// Supabase Edge Function: set-credential
// Encrypts a signed-in user's broker API keys server-side (AES-256-GCM) and
// stores them in broker_credentials. The encryption key (SECRET_ENCRYPTION_KEY)
// never leaves the server, so the browser never holds it. Row-Level Security
// (the caller's JWT) guarantees a user can only write to their OWN desk.
//
// Output format is byte-compatible with the Python worker (worker/crypto.py):
//   base64(iv[12]) + "." + base64(ciphertext||gcm_tag)
//
// Deploy:
//   supabase functions deploy set-credential
//   supabase secrets set SECRET_ENCRYPTION_KEY=<base64 of 32 random bytes>
//   (SUPABASE_URL and SUPABASE_ANON_KEY are injected automatically.)
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

function toB64(b: Uint8Array): string { let s = ""; for (const x of b) s += String.fromCharCode(x); return btoa(s); }
function fromB64(s: string): Uint8Array { const a = atob(s); const u = new Uint8Array(a.length); for (let i = 0; i < a.length; i++) u[i] = a.charCodeAt(i); return u; }

async function encrypt(plaintext: string, keyB64: string): Promise<string> {
  const raw = fromB64(keyB64);
  if (raw.length !== 32) throw new Error("SECRET_ENCRYPTION_KEY must be base64 of exactly 32 bytes");
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext));
  return toB64(iv) + "." + toB64(new Uint8Array(ct)); // ct already includes the 16-byte tag
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  try {
    const authHeader = req.headers.get("Authorization") || "";
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!,
      { global: { headers: { Authorization: authHeader } } },
    );
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return json({ error: "unauthorized" }, 401);

    const { desk_id, credentials } = await req.json().catch(() => ({}));
    if (!desk_id || !credentials || typeof credentials !== "object")
      return json({ error: "desk_id and credentials{} required" }, 400);

    const keyB64 = Deno.env.get("SECRET_ENCRYPTION_KEY");
    if (!keyB64) return json({ error: "server missing SECRET_ENCRYPTION_KEY" }, 500);

    const rows: { desk_id: string; name: string; enc_value: string }[] = [];
    for (const [name, value] of Object.entries(credentials)) {
      if (value === null || value === undefined || `${value}` === "") continue;
      rows.push({ desk_id, name, enc_value: await encrypt(`${value}`, keyB64) });
    }
    if (!rows.length) return json({ ok: true, saved: [] });

    // RLS (caller's JWT) enforces that desk_id belongs to this user.
    const { error } = await supabase.from("broker_credentials")
      .upsert(rows, { onConflict: "desk_id,name" });
    if (error) return json({ error: error.message }, 400);
    return json({ ok: true, saved: rows.map((r) => r.name) });
  } catch (e) {
    return json({ error: String((e as Error)?.message || e) }, 500);
  }
});
