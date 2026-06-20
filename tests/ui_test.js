// Headless UI test for the SAHJONY terminal dashboard (jsdom).
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
    }, from: () => q() };
}

function navClick(win, label) {
  const want = label.toUpperCase();
  const b = [...win.document.querySelectorAll('#nav button')]
    .find(x => x.textContent.replace(/^\s*\d+\s*/, '').trim().toUpperCase() === want);
  if (!b) throw new Error('nav button not found: ' + label);
  b.onclick();
}
const viewText = (win) => win.document.getElementById('view').textContent;

async function main() {
  const state = { session: null, desks: [], updates: [] };
  const vc = new VirtualConsole();
  const dom = new JSDOM(html.replace(/<script src=[^>]*><\/script>/g, ''),
    { runScripts: 'outside-only', url: 'https://desk.test/', virtualConsole: vc });
  const win = dom.window;
  win.SAHJONY_CONFIG = { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'anon' };
  win.supabase = { createClient: () => makeClient(state) };
  win.fetch = async () => ({ json: async () => statusJson });
  win.eval(appScript);
  await new Promise(r => setTimeout(r, 60));

  check(win.document.querySelectorAll('#nav button').length === 7, 'all 7 function tabs present');
  check(win.document.getElementById('tape').textContent.length > 0, 'ticker tape populated');
  check(viewText(win).includes('Equity'), 'Terminal cockpit renders (Equity/NAV)');
  check(viewText(win).includes('Council Heatmap') || viewText(win).includes('Heatmap'), 'Terminal shows council heatmap');
  navClick(win, 'Council'); check(viewText(win).includes('Intelligence Council'), 'Council tab renders');
  navClick(win, 'Brain'); check(viewText(win).includes('Chief Strategist'), 'Brain tab renders');
  navClick(win, 'Book'); check(viewText(win).toLowerCase().includes('positions'), 'Book tab renders');
  navClick(win, 'Workforce'); check(viewText(win).toLowerCase().includes('workforce'), 'Workforce tab renders');
  navClick(win, 'Env'); check(viewText(win).includes('ALPACA'), 'Env tab renders env catalog');

  navClick(win, 'Controls');
  check(/owner sign-in/i.test(viewText(win)), 'Controls shows sign-in when logged out');
  check(win.document.getElementById('lbtn'), 'sign-in button present');

  state.session = { user: { email: 'owner@sahjony.test' } };
  state.desks = [{ id: 'desk-1', name: 'My Desk', mode: 'paper', active: true, halt: false,
    tickers: ['AAPL', 'MSFT'], max_allocation_pct: 0.1, max_total_deployed_pct: 0.6, min_conviction: 0.55,
    last_run_at: new Date().toISOString(),
    last_status: { ...statusJson, account: { ...statusJson.account, equity: 123456 } } }];
  await win.load();
  navClick(win, 'Terminal');
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

  console.log(`\nTERMINAL UI TEST PASSED ✓ (${passed} checks)`);
}
main().catch(e => { console.log('✗ ERROR:', e.stack); process.exit(1); });
