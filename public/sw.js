// SAHJONY parquet — minimal service worker (enables install + offline shell).
// App shell is cached network-first; live data (status.json) and all cross-origin
// APIs / Supabase / WebSockets are never cached.
const C = 'sahjony-v2';
const SHELL = ['./','./index.html','./login.html','./config.js','./manifest.webmanifest',
  './favicon.svg','./icon-192.png','./icon-512.png','./apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(C).then(c => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== C).map(x => caches.delete(x))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin || /status\.json/.test(u.pathname)) return;
  e.respondWith(
    fetch(e.request).then(r => { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); return r; })
      .catch(() => caches.match(e.request))
  );
});
