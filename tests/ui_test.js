// Headless UI test for the SAHJONY parquet dashboard (jsdom).
//   node tests/ui_test.js
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.join(__dirname, '..', 'public');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const statusJson = JSON.parse(fs.readFileSync(path.join(ROOT, 'status.json'), 'utf8'));
const appScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim()).pop();

let passed = 0;
const check = (c, m) => { if (!c) { console.log('✗ FAIL:', m); process.exit(1); } console.log('✓', m); passed++; };

function makeClient(state) {
  const q = () => { const o = { _upd: false };
    o.select = () => o; o.order = () => o; o.limit = () => o; o.eq = () => o;
    o.update = (f) => { o._upd = true; state.updates.push(f); return o; };
    o.then = (res) => res(o._upd ? { error: null } : { data: state.desks, error: null }); return o; };
  return { auth: {
      getSession: async () => ({ data: { session: state.session } }),
      signInWithPassword: async ({ email }) => { state.session = { user: { email } }; return { error: null }; },
      signOut: async () => { state.session = null; return { error: null }; },
    }, from: () => q(),
    channel: () => { const ch = { _cbs: [], on: (_e, _o, cb) => { ch._cbs.push(cb); return ch; }, subscribe: () => { state.channel = ch; return ch; } }; return ch; },
    removeChannel: () => {},
  };
}
const sockets = [];
class FakeWS { constructor(url){ this.url=url; this.readyState=0; sockets.push(this); setTimeout(()=>{ this.readyState=1; this.onopen && this.onopen(); },0); } send(){} close(){ this.readyState=3; this.onclose && this.onclose(); } }

function navClick(win, label) {
  const want = label.toUpperCase();
  const b = [...win.document.querySelectorAll('#nav button')]
    .find(x => x.textContent.replace(/^\s*\d+\s*/, '').trim().toUpperCase() === want);
  if (!b) throw new Error('nav button not found: ' + label);
  b.onclick();
}
const viewText = (win) => win.document.getElementById('view').textContent;

// jsdom (without pretendToBeVisual) has no requestAnimationFrame. Stub it to invoke
// the callback synchronously with a far-advanced timestamp so time-based count-up
// animations settle to their final value in a single frame. The dashboard's only
// rAF user (animateCounts) self-terminates at progress>=1, so this cannot recurse
// forever, and running synchronously means the final value is present the instant a
// render returns — no waiting on a timer before assertions. Applied to every window.
const installRaf = (w) => {
  w.requestAnimationFrame = (cb) => {
    cb(((w.performance && w.performance.now) ? w.performance.now() : Date.now()) + 100000);
    return 0;
  };
  w.cancelAnimationFrame = () => {};
};

async function main() {
  const state = { session: null, desks: [], updates: [] };
  const vc = new VirtualConsole();
  const dom = new JSDOM(html.replace(/<script src=[^>]*><\/script>/g, ''),
    { runScripts: 'outside-only', url: 'https://desk.test/', virtualConsole: vc });
  const win = dom.window;
  win.SAHJONY_CONFIG = { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'anon' };
  win.supabase = { createClient: () => makeClient(state) };
  win.WebSocket = FakeWS;
  const CRYPTO = [{ symbol: 'btc', name: 'Bitcoin', current_price: 61000, price_change_percentage_24h: 2.4, market_cap: 1.2e12, total_volume: 3e10 }];
  const ARTS = [{ title: 'Markets rally on cooling inflation', url: 'https://news.test/a', domain: 'reuters.com', seendate: '20260620T210000Z' }];
  const credCalls = [];
  win.fetch = async (url, opts) => {
    if (/functions\/v1\/set-credential/.test(url)) {
      const body = JSON.parse((opts && opts.body) || '{}');
      credCalls.push({ url, headers: (opts && opts.headers) || {}, body });
      return { ok: true, json: async () => ({ ok: true, saved: Object.keys(body.credentials || {}) }) };
    }
    if (/alternative\.me/.test(url)) return { ok: true, json: async () => ({ data: [{ value: '72', value_classification: 'Greed', timestamp: '1' }] }) };
    if (/search\/trending/.test(url)) return { ok: true, json: async () => ({ coins: [{ item: { name: 'Solana', symbol: 'SOL', market_cap_rank: 5 } }] }) };
    if (/api\/v3\/global/.test(url)) return { ok: true, json: async () => ({ data: { total_market_cap: { usd: 2.4e12 }, market_cap_change_percentage_24h_usd: 1.5, market_cap_percentage: { btc: 52.3, eth: 17.1 }, active_cryptocurrencies: 12000 } }) };
    if (/frankfurter/.test(url)) return { ok: true, json: async () => ({ rates: { EUR: 0.92, GBP: 0.79, JPY: 150.2, CAD: 1.36, AUD: 1.52, CHF: 0.88, CNY: 7.1 } }) };
    if (/coingecko/.test(url)) return { ok: true, json: async () => CRYPTO };
    if (/gdelt/.test(url)) return { ok: true, json: async () => ({ articles: ARTS }) };
    if (/finnhub.*calendar\/earnings/.test(url)) return { ok: true, json: async () => ({ earningsCalendar: [{ symbol: 'AAPL', date: '2026-06-25', hour: 'amc', epsEstimate: 1.21 }] }) };
    if (/finnhub.*company-news/.test(url)) return { ok: true, json: async () => ([{ headline: 'AAPL unveils new chip', url: 'https://x', source: 'CNBC', datetime: 1782000000 }]) };
    if (/finnhub.*\/news/.test(url)) return { ok: true, json: async () => ([{ headline: 'Fed holds rates steady', url: 'https://x', source: 'Reuters', datetime: 1782000000 }]) };
    if (/finnhub.*\/quote/.test(url)) return { ok: true, json: async () => ({ c: 540.2, d: 3.1, dp: 0.58, h: 541, l: 537 }) };
    return { ok: true, json: async () => statusJson };
  };
  installRaf(win);
  win.eval(appScript);
  await new Promise(r => setTimeout(r, 60));

  check(win.document.querySelectorAll('#nav button').length === 11, 'all 11 function tabs present');
  check(win.document.getElementById('tape').textContent.length > 0, 'ticker tape populated');
  check(viewText(win).includes('Equity'), 'Parquet cockpit renders (Equity/NAV)');
  check(viewText(win).includes('Council Heatmap') || viewText(win).includes('Heatmap'), 'Parquet shows council heatmap');
  await win.fetchMarkets(true); await win.fetchNews(true); await win.fetchIntel(true);
  navClick(win, 'Markets'); check(viewText(win).includes('BTC'), 'Markets tab renders live crypto (CoinGecko)');
  navClick(win, 'Macro'); check(/Fear & Greed/.test(viewText(win)) && viewText(win).includes('72'), 'Macro tab renders sentiment + intel');
  check(viewText(win).includes('BTC dominance'), 'Macro shows global crypto stats');
  navClick(win, 'Parquet'); check(/AI Market Read/.test(viewText(win)) && /(RISK-|NEUTRAL)/.test(viewText(win)), 'Parquet shows synthesized AI Market Read');
  navClick(win, 'News'); check(/cooling inflation/.test(viewText(win)), 'News tab renders live wire (GDELT)');
  navClick(win, 'Council'); check(viewText(win).includes('Intelligence Council'), 'Council tab renders');
  await new Promise(r => setTimeout(r, 150));
  check(/HEADLINES/.test(viewText(win)) && /cooling inflation/.test(viewText(win)), 'Council shows per-ticker headlines');
  navClick(win, 'Brain'); check(viewText(win).includes('Chief Strategist'), 'Brain tab renders');
  navClick(win, 'Book'); check(viewText(win).toLowerCase().includes('positions'), 'Book tab renders');
  navClick(win, 'Workforce'); check(viewText(win).toLowerCase().includes('workforce'), 'Workforce tab renders');
  navClick(win, 'Env'); check(viewText(win).includes('ALPACA'), 'Env tab renders env catalog');

  // Controls is owner-only: the nav hides it from read-only viewers (family/friends),
  // so a logged-out visitor can never land on it.
  check(![...win.document.querySelectorAll('#nav button')].some(b => /Controls/i.test(b.textContent)),
    'Controls tab hidden from the nav when logged out (owner-only)');

  state.session = { user: { email: 'owner@sahjony.test' } };
  state.desks = [{ id: 'desk-1', name: 'My Desk', mode: 'paper', active: true, halt: false,
    tickers: ['AAPL', 'MSFT'], max_allocation_pct: 0.1, max_total_deployed_pct: 0.6, min_conviction: 0.55,
    last_run_at: new Date().toISOString(),
    last_status: { ...statusJson, account: { ...statusJson.account, equity: 123456 } } }];
  await win.load();
  navClick(win, 'Parquet');
  check(viewText(win).includes('123,456'), 'dashboard switches to LIVE desk.last_status when signed in');
  navClick(win, 'Controls');
  check(/desk controls/i.test(viewText(win)), 'Controls renders the live panel when signed in');

  const halt = [...win.document.querySelectorAll('#view button')].find(b => /HALT/.test(b.textContent));
  check(!!halt, 'HALT button present'); halt.onclick(); await new Promise(r => setTimeout(r, 20));
  check(state.updates.some(u => u.halt === true), 'HALT click writes {halt:true} to Supabase');

  win.confirm = () => true; navClick(win, 'Controls');
  const flat = [...win.document.querySelectorAll('#view button')].find(b => /flatten/i.test(b.textContent));
  flat.onclick(); await new Promise(r => setTimeout(r, 20));
  check(state.updates.some(u => u.command === 'flatten'), 'Flatten click writes command=flatten');

  // ── self-service broker keys onboarding ──
  navClick(win, 'Controls');
  check(/Broker Keys/.test(viewText(win)), 'Controls renders the self-service Broker Keys panel');
  win.document.getElementById('kak').value = 'PKTEST123';
  win.document.getElementById('kas').value = 'secret-xyz';
  const savek = [...win.document.querySelectorAll('#view button')].find(b => /SAVE KEYS/.test(b.textContent));
  check(!!savek, 'SAVE KEYS button present'); savek.onclick(); await new Promise(r => setTimeout(r, 30));
  check(credCalls.length === 1, 'SAVE KEYS calls the set-credential Edge Function once');
  check(/\/functions\/v1\/set-credential$/.test(credCalls[0].url), 'posts to the set-credential function endpoint');
  check(credCalls[0].body.credentials.ALPACA_API_KEY === 'PKTEST123'
    && credCalls[0].body.credentials.ALPACA_SECRET_KEY === 'secret-xyz', 'sends entered broker keys in the body');
  check(/^Bearer /.test(credCalls[0].headers.Authorization || ''), 'authorizes with the caller bearer token');
  check(credCalls[0].body.desk_id === 'desk-1', 'scopes the save to the signed-in desk_id');

  // ── realtime streaming ──
  check(win.document.getElementById('dStream').className.includes('live'), 'crypto WebSocket connects (STREAM dot live)');
  const bws = sockets.find(s => /binance/.test(s.url));
  check(!!bws, 'Binance crypto stream opened');
  bws.onmessage({ data: JSON.stringify({ data: { s: 'BTCUSDT', c: '70000', P: '5.0' } }) });
  await new Promise(r => setTimeout(r, 1000));
  check(win.document.getElementById('tape').textContent.includes('70,000'), 'live crypto tick streams into the ticker tape');
  check(!!state.channel, 'Supabase Realtime channel subscribed for the desk');
  state.channel._cbs[0]({ new: { ...state.desks[0], last_status: { ...statusJson, account: { ...statusJson.account, equity: 987654 } } } });
  await new Promise(r => setTimeout(r, 20));
  navClick(win, 'Parquet');
  check(viewText(win).includes('987,654'), 'Supabase Realtime push updates the dashboard instantly');

  // ── Finnhub-powered panels (indices + earnings) via a second mount ──
  const st2 = { session: null, desks: [], updates: [] };
  const dom2 = new JSDOM(html.replace(/<script src=[^>]*><\/script>/g, ''),
    { runScripts: 'outside-only', url: 'https://desk.test/', virtualConsole: new VirtualConsole() });
  const w2 = dom2.window;
  w2.SAHJONY_CONFIG = { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'anon', FINNHUB_API_KEY: 'testkey' };
  w2.supabase = { createClient: () => makeClient(st2) };
  w2.WebSocket = FakeWS;
  w2.fetch = win.fetch;
  installRaf(w2);
  w2.eval(appScript);
  await new Promise(r => setTimeout(r, 60));
  await w2.fetchIntel(true);
  navClick(w2, 'Macro');
  check(/Equity Indices/.test(viewText(w2)) && /S&P 500/.test(viewText(w2)), 'Macro renders live equity indices (Finnhub)');
  check(/Earnings/.test(viewText(w2)) && /AAPL/.test(viewText(w2)), 'Macro renders earnings calendar (Finnhub)');

  console.log(`\nTERMINAL UI TEST PASSED ✓ (${passed} checks)`);
}
// jsdom keeps timers/WebSockets alive (the dashboard's setInterval(load,30000) +
// clock), which would keep Node's event loop running forever — exit explicitly so
// CI / readiness.sh don't hang after a green run.
main().then(() => process.exit(0)).catch(e => { console.log('✗ ERROR:', e.stack); process.exit(1); });
