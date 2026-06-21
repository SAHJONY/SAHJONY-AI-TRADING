// Headless test for public/login.html passcode screen (jsdom).
//   node tests/login_test.js
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, '..', 'public', 'login.html'), 'utf8');
const appScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim()).pop();

let passed = 0;
const check = (c, m) => { if (!c) { console.log('✗ FAIL:', m); process.exit(1); } console.log('✓', m); passed++; };

function client(state) {
  return { auth: {
    getSession: async () => ({ data: { session: state.session } }),
    signInWithPassword: async ({ email, password }) => {
      state.attempts.push({ email, password });
      if (password !== 'correct') return { error: { message: 'Invalid login credentials' } };
      state.session = { user: { email } };
      return { data: { session: state.session }, error: null };
    },
    signOut: async () => { state.session = null; return { error: null }; },
    resetPasswordForEmail: async (email) => { state.reset = email; return { error: null }; },
  } };
}

function mount(cfg, state) {
  const vc = new VirtualConsole();
  let nav = false;
  vc.on('jsdomError', e => { if (/navigation/i.test(e.message)) nav = true; });
  const dom = new JSDOM(html.replace(/<script src=[^>]*><\/script>/g, ''),
    { runScripts: 'outside-only', url: 'https://desk.test/login.html', virtualConsole: vc });
  const win = dom.window;
  win.SAHJONY_CONFIG = cfg;
  win.supabase = { createClient: () => client(state) };
  win.eval(appScript);
  return { win, redirected: () => nav };
}
const wait = () => new Promise(r => setTimeout(r, 30));
const txt = (win) => win.document.getElementById('msg').textContent;

async function main() {
  const OWNER = 'sahjonycapitalllc@outlook.com';
  const CFG = { SUPABASE_URL: 'https://x.supabase.co', SUPABASE_ANON_KEY: 'anon', OWNER_EMAIL: OWNER };

  // passcode mode hides the email field, shows the access code
  let st = { session: null, attempts: [] };
  let m = mount(CFG, st);
  check(m.win.document.getElementById('email').style.display === 'none', 'passcode mode hides the email field');
  check(m.win.document.getElementById('who').textContent === OWNER, 'shows the owner identity');

  // wrong code → error, no redirect, and it used the configured owner email
  m.win.document.getElementById('code').value = 'nope';
  m.win.document.getElementById('go').onclick(); await wait();
  check(st.attempts.length === 1 && st.attempts[0].email === OWNER, 'signs in with the configured owner email automatically');
  check(/Invalid login/.test(txt(m.win)) && m.redirected() === false, 'wrong code is rejected');

  // correct code → redirect to dashboard
  st = { session: null, attempts: [] }; m = mount(CFG, st);
  m.win.document.getElementById('code').value = 'correct';
  m.win.document.getElementById('go').onclick(); await wait();
  check(m.redirected() === true, 'correct access code opens the terminal');

  // forgot code → reset email to the owner
  st = { session: null, attempts: [] }; m = mount(CFG, st);
  m.win.document.getElementById('forgot').onclick(); await wait();
  check(st.reset === OWNER, 'forgot-code sends a reset to the owner email');

  // already signed in → auto redirect
  st = { session: { user: { email: OWNER } }, attempts: [] };
  m = mount(CFG, st); await wait();
  check(m.redirected() === true, 'existing session auto-opens the terminal');

  // no OWNER configured → email field revealed (fallback)
  st = { session: null, attempts: [] };
  m = mount({ SUPABASE_URL: 'https://x', SUPABASE_ANON_KEY: 'a', OWNER_EMAIL: '' }, st);
  check(m.win.document.getElementById('email').style.display === 'block', 'no owner email → email field shown (fallback)');

  console.log(`\nLOGIN (PASSCODE) TEST PASSED ✓ (${passed} checks)`);
}
// jsdom leaves timers running (the page's setInterval clock) which keeps Node's
// event loop alive — exit explicitly so CI / readiness.sh don't hang.
main().then(() => process.exit(0)).catch(e => { console.log('✗ ERROR:', e.stack); process.exit(1); });
