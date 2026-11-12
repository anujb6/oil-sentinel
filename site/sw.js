const STATIC_CACHE = 'oil-sentinel-static-v3';
const STATIC = ['./','./index.html','./style.css','./app.js','./manifest.webmanifest','./icons/icon-192.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(STATIC_CACHE).then(c=>c.addAll(STATIC)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==STATIC_CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin)return;
  // Inventory data should never be served from stale static cache if network works.
  if(url.pathname.endsWith('/data.json') || url.pathname.endsWith('/briefing.txt')){
    event.respondWith(fetch(req).catch(()=>caches.match(req)));
    return;
  }
  // Network-first prevents old JS/CSS from persisting after a new Pages deployment.
  event.respondWith(fetch(req).then(response=>{
    if(response.ok && (url.pathname.endsWith('/app.js') || url.pathname.endsWith('/style.css') || url.pathname.endsWith('/index.html') || url.pathname.endsWith('/'))) {
      const copy=response.clone();caches.open(STATIC_CACHE).then(c=>c.put(req,copy));
    }
    return response;
  }).catch(()=>caches.match(req)));
});
