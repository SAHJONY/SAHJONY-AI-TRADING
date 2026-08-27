// SAHJONY Trading OS ↔ SAHJONY CONNECT bridge.
// Isolated from trading/execution code: this file only renders trusted CONNECT
// communication sessions inside the dashboard. It never reads broker credentials,
// places orders, changes trading controls, or accepts arbitrary iframe origins.
(() => {
  'use strict';

  const cfg = window.SAHJONY_CONFIG || {};
  const configuredOrigin = String(cfg.CONNECT_ORIGIN || '').trim().replace(/\/$/, '');
  const devOrigins = location.hostname === 'localhost' || location.hostname === '127.0.0.1'
    ? ['http://localhost:8000', 'http://127.0.0.1:8000'] : [];
  const allowedOrigins = new Set([configuredOrigin, ...devOrigins].filter(Boolean));
  const allowedPaths = new Set([
    '/messenger.html', '/chat.html', '/call.html', '/business-contact.html',
    '/personal-os.html', '/customer-command-center.html'
  ]);

  const state = { currentUrl: null, dock: null, frame: null, status: null };

  function parseTrustedUrl(raw) {
    if (!raw || !configuredOrigin) return null;
    try {
      const u = new URL(String(raw), configuredOrigin + '/');
      if (!allowedOrigins.has(u.origin)) return null;
      if (!allowedPaths.has(u.pathname)) return null;
      return u;
    } catch (_) { return null; }
  }

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function ensureUi() {
    if (state.dock) return state.dock;
    const style = document.createElement('style');
    style.textContent = `
      #connectDock{position:fixed;inset:64px 14px 14px 14px;z-index:2147483000;display:none;
        border:1px solid rgba(67,189,214,.38);border-radius:16px;overflow:hidden;background:#070a10;
        box-shadow:0 22px 80px rgba(0,0,0,.72),0 0 0 1px rgba(255,255,255,.025)}
      #connectDock.open{display:grid;grid-template-rows:auto 1fr}
      #connectDock .cdbar{display:flex;align-items:center;gap:8px;padding:9px 11px;background:#0b111b;
        border-bottom:1px solid #27324a;font:600 11px ui-monospace,SFMono-Regular,Menlo,monospace;color:#e9eff9}
      #connectDock .cdbrand{color:#43bdd6;font-weight:800;letter-spacing:.08em}.cdgrow{flex:1}
      #connectDock .cdstatus{color:#8a99b6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:45vw}
      #connectDock button{border:1px solid #27324a;background:#111925;color:#e9eff9;border-radius:7px;padding:6px 9px;
        font:600 10px ui-monospace,SFMono-Regular,Menlo,monospace;cursor:pointer}
      #connectDock button:hover{border-color:#43bdd6;color:#43bdd6}
      #connectDock iframe{width:100%;height:100%;min-height:0;border:0;background:#050a10}
      #connectDock .cderror{padding:28px;color:#f4d288;font:500 12px ui-monospace,SFMono-Regular,Menlo,monospace}
      #connectLauncher{position:fixed;right:16px;bottom:16px;z-index:2147482999;border:1px solid rgba(67,189,214,.42);
        background:linear-gradient(135deg,#122031,#0b111b);color:#e9eff9;border-radius:999px;padding:10px 14px;
        box-shadow:0 10px 32px rgba(0,0,0,.52);font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace;cursor:pointer}
      #connectLauncher span{color:#43bdd6}
      #connectPaste{position:fixed;right:16px;bottom:62px;z-index:2147483001;width:min(420px,calc(100vw - 32px));display:none;
        border:1px solid #27324a;border-radius:12px;background:#0b111b;padding:11px;box-shadow:0 16px 50px rgba(0,0,0,.65)}
      #connectPaste.open{display:block}#connectPaste input{width:100%;padding:9px;border-radius:7px;border:1px solid #27324a;
        background:#070a10;color:#e9eff9;font:11px ui-monospace,SFMono-Regular,Menlo,monospace}#connectPaste .row{display:flex;gap:7px;margin-top:8px}
      #connectPaste button{flex:1;border:1px solid #27324a;background:#111925;color:#e9eff9;border-radius:7px;padding:8px;cursor:pointer}
      @media(max-width:700px){#connectDock{inset:0; border-radius:0}.cdstatus{display:none!important}}
    `;
    document.head.appendChild(style);

    const dock = document.createElement('section');
    dock.id = 'connectDock';
    dock.setAttribute('aria-label', 'SAHJONY CONNECT Session Dock');
    dock.innerHTML = `<div class="cdbar"><span class="cdbrand">SAHJONY CONNECT</span><span>SESSION DOCK</span><span class="cdgrow"></span><span class="cdstatus">idle</span><button data-cd="external">OPEN ↗</button><button data-cd="full">FULL</button><button data-cd="close">CLOSE</button></div><div class="cdbody"></div>`;
    document.body.appendChild(dock);
    state.dock = dock;
    state.status = dock.querySelector('.cdstatus');

    const launcher = document.createElement('button');
    launcher.id = 'connectLauncher';
    launcher.innerHTML = '<span>●</span> CONNECT';
    launcher.title = 'Open a SAHJONY CONNECT session inside Trading OS';
    document.body.appendChild(launcher);

    const paste = document.createElement('div');
    paste.id = 'connectPaste';
    paste.innerHTML = `<input id="connectUrlInput" type="url" inputmode="url" placeholder="Paste trusted SAHJONY CONNECT session link"><div class="row"><button data-cp="open">OPEN INSIDE TRADING OS</button><button data-cp="cancel">CANCEL</button></div>`;
    document.body.appendChild(paste);

    launcher.onclick = () => paste.classList.toggle('open');
    paste.querySelector('[data-cp="cancel"]').onclick = () => paste.classList.remove('open');
    paste.querySelector('[data-cp="open"]').onclick = () => {
      const raw = paste.querySelector('#connectUrlInput').value.trim();
      paste.classList.remove('open');
      open(raw, { source: 'manual-paste' });
    };
    dock.querySelector('[data-cd="close"]').onclick = close;
    dock.querySelector('[data-cd="external"]').onclick = () => {
      if (state.currentUrl) window.open(state.currentUrl, '_blank', 'noopener,noreferrer');
    };
    dock.querySelector('[data-cd="full"]').onclick = async () => {
      try { await dock.requestFullscreen?.(); } catch (_) {}
    };
    return dock;
  }

  function showError(text) {
    const dock = ensureUi();
    dock.classList.add('open');
    state.status.textContent = 'blocked';
    dock.querySelector('.cdbody').innerHTML = `<div class="cderror">${esc(text)}</div>`;
  }

  function open(rawUrl, meta = {}) {
    const u = parseTrustedUrl(rawUrl);
    if (!u) {
      showError(configuredOrigin
        ? 'Blocked: only approved SAHJONY CONNECT session URLs can open inside Trading OS.'
        : 'CONNECT bridge is not configured for this deployment.');
      return false;
    }
    const dock = ensureUi();
    const body = dock.querySelector('.cdbody');
    body.textContent = '';
    const frame = document.createElement('iframe');
    frame.src = u.href;
    frame.title = 'SAHJONY CONNECT communication session';
    frame.referrerPolicy = 'strict-origin-when-cross-origin';
    frame.allow = 'microphone; camera; display-capture; fullscreen; clipboard-read; clipboard-write';
    frame.setAttribute('allowfullscreen', '');
    body.appendChild(frame);
    state.frame = frame;
    state.currentUrl = u.href;
    state.status.textContent = `${u.pathname.replace(/^\//,'')} · ${meta.source || 'deep-link'}`;
    dock.classList.add('open');
    try { sessionStorage.setItem('sahjonyConnectLastSession', u.href); } catch (_) {}
    history.replaceState(null, '', stripConnectParams(location.href));
    return true;
  }

  function close() {
    if (!state.dock) return;
    state.dock.classList.remove('open');
    const body = state.dock.querySelector('.cdbody');
    if (body) body.textContent = '';
    state.frame = null;
    state.currentUrl = null;
    if (state.status) state.status.textContent = 'idle';
  }

  function stripConnectParams(href) {
    try {
      const u = new URL(href);
      ['connect_url','connectUrl','url','text','title'].forEach(k => u.searchParams.delete(k));
      return u.pathname + (u.search ? u.search : '') + (u.hash || '');
    } catch (_) { return href; }
  }

  function deepLinkFromLocation() {
    const q = new URLSearchParams(location.search);
    // Web Share Target may send the URL in `url`, or browsers may include it in `text`.
    const candidates = [q.get('connect_url'), q.get('connectUrl'), q.get('url')];
    const text = q.get('text');
    if (text) {
      const match = text.match(/https?:\/\/[^\s]+/i);
      if (match) candidates.push(match[0]);
    }
    for (const candidate of candidates) {
      if (parseTrustedUrl(candidate)) return candidate;
    }
    return null;
  }

  function wrap(sessionUrl) {
    const u = parseTrustedUrl(sessionUrl);
    if (!u) throw new Error('Untrusted CONNECT URL');
    const here = new URL(location.origin + location.pathname);
    here.searchParams.set('connect_url', u.href);
    return here.href;
  }

  window.addEventListener('message', event => {
    if (!allowedOrigins.has(event.origin)) return;
    const data = event.data || {};
    if (data.type !== 'SAHJONY_CONNECT_OPEN_SESSION') return;
    open(data.url, { source: 'postMessage' });
  });

  window.addEventListener('storage', event => {
    if (event.key !== 'sahjonyConnectOpenSession' || !event.newValue) return;
    open(event.newValue, { source: 'cross-tab' });
  });

  document.addEventListener('click', event => {
    const a = event.target?.closest?.('a[href]');
    if (!a || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const u = parseTrustedUrl(a.href);
    if (!u) return;
    event.preventDefault();
    open(u.href, { source: 'in-app-link' });
  }, true);

  window.SAHJONY_CONNECT = Object.freeze({
    open,
    close,
    wrap,
    isTrusted: raw => Boolean(parseTrustedUrl(raw)),
    origin: configuredOrigin,
    version: '1.0.0'
  });

  function boot() {
    ensureUi();
    const deepLink = deepLinkFromLocation();
    if (deepLink) open(deepLink, { source: 'deep-link/share-target' });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();