// Headless test for public/login.html (jsdom).
//   node tests/login_test.js
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, '..', 'public', 'login.html'), 'utf8');
const appScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim()).pop();

let passed = 0;
const check = (c, m) => { if (!c) { console.log('✗ FAIL:', m); process.exit(1); } console.log('✓', m); passed++; };

function client(state) {
  return {
    auth: {
      getSession: async () => ({ data: { session: state.session } }),
      signInWithPassword: async ({ email, password }) => {
        state.attempts.push({ email, password });
        if (password !== 'correct') return { error: { message: 'Invalid login credentials' } };
        state.session = { user: { email } };
        return { data: { session: state.session }, error: null };
      },
      signOut: async () => { state.signOut = true; state.session = null; return { error: null }; },
      resetPasswordForEmail: async (email) => { state.reset = email; return { error: null }; },
    },
  };
}

function mount(cfg, state) {
  const vc = new VirtualConsole();
  let nav = false;
  vc.on('jsdomError', e => { if (/navigation/i.test(e.message)) nav = true; });   // location.href set
  const dom = new JSDOM(html.replace(/<script src=[^>]*><\/script>/g, ''),
    { runScripts: 'outside-only', url: 'https://desk.test/login.html', virtualConsole: vc });
  const win = dom.window;
  win.SAHJONY_CONFIG = cfg;
  win.supabase = { createClient: () => client(state) };
  win.eval(appScript);
  return { win, redirected: () => nav };
}
const txt = (win) => win.document.getElementById('msg').textContent;
const wait = () => new Promise(r => setTimeout(r, 30));

async function main() {
  const CFG = { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'anon', OWNER_EMAIL: 'owner@sahjony.test' };

  // wrong password → error, no redirect
  let st = { session: null, attempts: [] };
  let m = mount(CFG, st);
  m.win.document.getElementById('email').value = 'owner@sahjony.test';
  m.win.document.getElementById('pw').value = 'wrong';
  m.win.document.getElementById('go').onclick(); await wait();
  check(st.attempts.length === 1, 'sign-in calls Supabase');
  check(/Invalid login/.test(txt(m.win)), 'wrong password shows error');
  check(m.redirected() === false, 'no redirect on failed login');

  // non-owner email → refused before hitting Supabase
  st = { session: null, attempts: [] };
  m = mount(CFG, st);
  m.win.document.getElementById('email').value = 'stranger@evil.com';
  m.win.document.getElementById('pw').value = 'correct';
  m.win.document.getElementById('go').onclick(); await wait();
  check(st.attempts.length === 0, 'non-owner refused without calling Supabase');
  check(/private to the owner/.test(txt(m.win)), 'non-owner sees owner-only message');

  // correct owner login → redirects to dashboard
  st = { session: null, attempts: [] };
  m = mount(CFG, st);
  m.win.document.getElementById('email').value = 'owner@sahjony.test';
  m.win.document.getElementById('pw').value = 'correct';
  m.win.document.getElementById('go').onclick(); await wait();
  check(st.attempts.length === 1, 'owner login calls Supabase');
  check(m.redirected() === true, 'successful owner login redirects to dashboard');

  // forgot password → sends reset
  st = { session: null, attempts: [] };
  m = mount(CFG, st);
  m.win.document.getElementById('email').value = 'owner@sahjony.test';
  m.win.document.getElementById('forgot').onclick(); await wait();
  check(st.reset === 'owner@sahjony.test', 'forgot-password sends reset email');

  // already-signed-in owner → auto-redirect on load
  st = { session: { user: { email: 'owner@sahjony.test' } }, attempts: [] };
  m = mount(CFG, st); await wait();
  check(m.redirected() === true, 'existing owner session auto-redirects to dashboard');

  console.log(`\nLOGIN TEST PASSED ✓ (${passed} checks)`);
}
main().catch(e => { console.log('✗ ERROR:', e.stack); process.exit(1); });
