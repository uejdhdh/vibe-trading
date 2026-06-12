const CACHE = "ot-v2";

// Network-first for HTML, cache-first for static assets
self.addEventListener("fetch", (e) => {
  // Always fetch HTML fresh (prevents stale JS refs after deploy)
  if (e.request.mode === "navigate" || e.request.destination === "document") {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // Cache-first for JS/CSS/images
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request).then((res) => {
      if (res.ok) {
        const clone = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, clone));
      }
      return res;
    }))
  );
});

// Clear old caches on activate
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
  )));
});
