/**
 * sw.js — SATS Companion Service Worker
 * 
 * Implements offline caching strategy:
 * - Cache-first for static assets (HTML, JS, CSS)
 * - Network-first with local fallback for API calls
 */

const CACHE_NAME = "sats-companion-v1";
const STATIC_ASSETS = ["/", "/static/app.js", "/static/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls: Network first
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({
            status: "offline",
            message: "Offline mode — transaction stored locally for synchronization.",
            data: null,
          }),
          { headers: { "Content-Type": "application/json" }, status: 503 }
        );
      })
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((response) => {
        if (response.ok && event.request.method === "GET") {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      });
    })
  );
});
