// Supabase Edge Function: voice-assistant
// Turns the dashboard's voice from a rigid keyword bot into a real bilingual
// assistant. The browser sends the spoken text + a compact snapshot of the live
// dashboard; this function asks an LLM (NVIDIA NIM — free, OpenAI-compatible) to
// answer naturally (English/Spanish) and optionally suggest ONE navigation action.
//
// The provider key (NVIDIA_API_KEY) lives ONLY here, never in the browser.
// Callable by anyone with the public anon key (the dashboard is public/read-only);
// it only reads the context the browser sends and returns text — it touches no
// user data and performs no trading.
//
// Deploy:
//   supabase functions deploy voice-assistant --no-verify-jwt
//   supabase secrets set NVIDIA_API_KEY=nvapi-xxxxxxxx
//   (optional) supabase secrets set NVIDIA_MODEL=meta/llama-3.3-70b-instruct
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

const TABS = ["Parquet", "Markets", "Macro", "News", "Council", "Book", "Brain", "Workforce", "Env"];

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const { text, lang, context } = await req.json().catch(() => ({}));
  const isES = String(lang || "").toLowerCase().startsWith("es");
  const langName = isES ? "Spanish" : "English";
  const offline = isES
    ? "El asistente de voz no está configurado todavía."
    : "The voice assistant isn’t configured yet.";
  if (!text || typeof text !== "string") return json({ reply: offline, action: { type: "none" } });

  const key = Deno.env.get("NVIDIA_API_KEY");
  if (!key) return json({ reply: offline, action: { type: "none" } });
  const model = Deno.env.get("NVIDIA_MODEL") || "meta/llama-3.3-70b-instruct";
  const base = (Deno.env.get("NVIDIA_BASE_URL") || "https://integrate.api.nvidia.com/v1").replace(/\/$/, "");

  const system =
    `You are the voice assistant for SAHJONY CAPITAL, an autonomous PAPER-trading quant desk ` +
    `(simulated money — never give financial advice; you explain the dashboard). ` +
    `Answer in ${langName}, conversationally and concisely (max ~50 words, no markdown). ` +
    `Use the live dashboard data provided. If the user clearly wants to open a section, set action.type="nav" ` +
    `and action.tab to one of: ${TABS.join(", ")}. Otherwise action.type="none". ` +
    `Respond ONLY with JSON: {"reply": string, "action": {"type": "nav"|"none", "tab"?: string}}.`;
  const user = `User said: "${text}"\n\nLive dashboard data:\n${String(context || "(none)").slice(0, 4000)}`;

  try {
    const payload: Record<string, unknown> = {
      model, max_tokens: 400, temperature: 0.4,
      response_format: { type: "json_object" },
      messages: [{ role: "system", content: system }, { role: "user", content: user }],
    };
    const headers = { "Authorization": "Bearer " + key, "Content-Type": "application/json" };
    let r = await fetch(base + "/chat/completions", { method: "POST", headers, body: JSON.stringify(payload) });
    if (!r.ok && [400, 404, 415, 422].includes(r.status)) {
      delete payload.response_format;
      r = await fetch(base + "/chat/completions", { method: "POST", headers, body: JSON.stringify(payload) });
    }
    if (!r.ok) {
      const errMsg = isES ? "No pude consultar al asistente ahora mismo." : "I couldn’t reach the assistant just now.";
      return json({ reply: errMsg, action: { type: "none" } });
    }
    const data = await r.json();
    const raw = data?.choices?.[0]?.message?.content ?? "{}";
    let parsed: { reply?: string; action?: { type?: string; tab?: string } } = {};
    try { parsed = JSON.parse(raw); }
    catch { const i = raw.indexOf("{"), j = raw.lastIndexOf("}"); if (i !== -1 && j > i) { try { parsed = JSON.parse(raw.slice(i, j + 1)); } catch { /* noop */ } } }
    let reply = (parsed.reply || (typeof raw === "string" ? raw : "")).toString().slice(0, 600).trim();
    if (!reply) reply = isES ? "No tengo una respuesta para eso." : "I don’t have an answer for that.";
    const act = parsed.action || { type: "none" };
    if (act.type === "nav" && !TABS.includes(act.tab || "")) act.type = "none";
    return json({ reply, action: act });
  } catch (e) {
    const errMsg = isES ? "Hubo un error con el asistente." : "There was an assistant error.";
    return json({ reply: errMsg, action: { type: "none" }, _error: String((e as Error)?.message || e) });
  }
});
