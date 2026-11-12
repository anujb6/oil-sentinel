/* Oil Sentinel service worker.
 * BUILD is stamped by the deploy workflow, so every deploy is a new worker and a new cache.
 * Everything is network-first and revalidated with the server (GitHub Pages caches files for
 * 10 minutes otherwise); the cache is only a fallback for when the phone is offline. */
const BUILD = '__BUILD__';
const CACHE = `oil-sentinel-${BUILD}`;
const OFFLINE_HEADER = 'X-Oil-Sentinel-Offline';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png', './icons/apple-touch-icon.png'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL.map(u => new Request(u, { cache: 'no-cache' })))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(
    fetch(req, { cache: 'no-cache' })
      .then(response => {
        if (response.ok && response.type === 'basic') {
          const copy = response.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return response;
      })
      .catch(() => caches.match(req).then(hit => {
        if (!hit) return req.mode === 'navigate' ? caches.match('./').then(page => page || Response.error()) : Response.error();
        // Label saved copies so the page can tell the user it is offline.
        const headers = new Headers(hit.headers);
        headers.set(OFFLINE_HEADER, '1');
        return hit.blob().then(body => new Response(body, { status: hit.status, statusText: hit.statusText, headers }));
      }))
  );
});
