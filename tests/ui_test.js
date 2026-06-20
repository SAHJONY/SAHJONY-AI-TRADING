// Headless UI test for the SAHJONY dashboard (jsdom).
//   node tests/ui_test.js
// Loads public/index.html with a mocked Supabase client + fetch, then exercises
// every tab and the live-control flow (sign-in form, control panel, HALT click).
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..', 'public');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const statusJson = JSON.parse(fs.readFileSync(path.join(ROOT, 'status.json'), 'utf8'));

// the inline app script is the only <script> block with a body (others are src-only)
const appScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map(m => m[1]).filter(s => s.trim().length > 0).pop();

let passed = 0;
function check(cond, msg) { if (!cond) { console.log('✗ FAIL:', msg); process.exit(1); } console.log('✓', msg); passed++; }

// mock Supabase client driven by a mutable `state`
function makeClient(state) {
  const q = () => {
    const o = { _upd: false };
    o.select = () => o; o.order = () => o; o.limit = () => o; o.eq = () => o;
    o.update = (f) => { o._upd = true; state.updates.push(f); return o; };
    o.then = (res) => res(o._upd ? { error: null } : { data: state.desks, error: null });
    return o;
  };
  return {
    auth: {
      getSession: async () => ({ data: { session: state.session } }),
      signInWithPassword: async ({ email }) => { state.session = { user: { email } }; return { error: null }; },
      signOut: async () => { state.session = null; return { error: null }; },
    },
    from: () => q(),
  };
}

function navClick(win, label) {
  const b = [...win.document.querySelectorAll('#nav button')].find(x => x.textContent.trim() === label);
  if (!b) throw new Error('nav button not found: ' + label);
  b.onclick();
}
const viewText = (win) => win.document.getElementById('view').textContent;

async function main() {
  const state = { session: null, desks: [], updates: [] };
  const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'https://desk.test/' });
  const win = dom.window;
  win.SAHJONY_CONFIG = { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'anon' };
  win.supabase = { createClient: () => makeClient(state) };
  win.fetch = async () => ({ json: async () => statusJson });

  win.eval(appScript);
  await new Promise(r => setTimeout(r, 60));   // let initial load() resolve

  // ── tabs render from real status.json (logged out → static snapshot) ──
  check(win.document.querySelectorAll('#nav button').length === 7, 'all 7 tabs present');
  check(viewText(win).includes('Equity'), 'Overview renders (Equity KPI)');
  navClick(win, 'Council'); check(viewText(win).includes('Intelligence Council'), 'Council tab renders');
  navClick(win, 'AI Brain'); check(viewText(win).includes('Chief Strategist'), 'AI Brain tab renders');
  navClick(win, 'Book'); check(viewText(win).toLowerCase().includes('positions'), 'Book tab renders');
  navClick(win, 'Workforce'); check(viewText(win).includes('workforce') || viewText(win).includes('Workforce'), 'Workforce tab renders');
  navClick(win, 'Environment'); check(viewText(win).includes('Environment'), 'Environment tab renders');

  // ── Controls tab, logged OUT → sign-in form ──
  navClick(win, 'Controls');
  check(viewText(win).includes('Owner sign-in'), 'Controls shows sign-in when logged out');
  check(win.document.getElementById('lbtn'), 'sign-in button present');

  // ── sign in + desk present → live data + control panel ──
  state.session = { user: { email: 'owner@sahjony.test' } };
  state.desks = [{
    id: 'desk-1', name: 'My Desk', mode: 'paper', active: true, halt: false,
    tickers: ['AAPL', 'MSFT'], max_allocation_pct: 0.1, max_total_deployed_pct: 0.6,
    min_conviction: 0.55, last_run_at: new Date().toISOString(),
    last_status: { ...statusJson, account: { ...statusJson.account, equity: 123456 } },
  }];
  await win.load();                 // re-pull desk + live data
  navClick(win, 'Overview');
  check(viewText(win).includes('123,456'), 'dashboard switches to LIVE desk.last_status when signed in');
  navClick(win, 'Controls');
  check(viewText(win).includes('Desk controls'), 'Controls renders the live panel when signed in');

  // ── click HALT → writes {halt:true} to the desk ──
  const halt = [...win.document.querySelectorAll('#view button')].find(b => /HALT/.test(b.textContent));
  check(!!halt, 'HALT button present');
  halt.onclick();
  await new Promise(r => setTimeout(r, 20));
  check(state.updates.some(u => u.halt === true), 'HALT click writes {halt:true} to Supabase');

  // ── Flatten → writes command=flatten (confirm() auto-true in jsdom) ──
  win.confirm = () => true;
  navClick(win, 'Controls');
  const flat = [...win.document.querySelectorAll('#view button')].find(b => /Flatten/.test(b.textContent));
  flat.onclick(); await new Promise(r => setTimeout(r, 20));
  check(state.updates.some(u => u.command === 'flatten'), 'Flatten click writes command=flatten');

  console.log(`\nUI TEST PASSED ✓ (${passed} checks)`);
}
main().catch(e => { console.log('✗ ERROR:', e.stack); process.exit(1); });
