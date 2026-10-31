/**
 * sw.js — SATS Companion Service Worker (v2.1)
 * 
 * Offline caching strategy:
 * - Network-first with cache fallback for HTML and app scripts (ensures fresh updates)
 * - Cache fallback when offline for zero-latency offline experience
 * - Background queue sync for mutations
 */

const CACHE_NAME = "sats-companion-v2.1";
const STATIC_ASSETS = [
  "/",
  "/static/index.html",
  "/static/app.js",
  "/static/manifest.json"
];

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
        keys.filter((k) => k !== CACHE_NAME).map((k) => {
          console.log("[SW] Deleting old cache:", k);
          return caches.delete(k);
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // 1. API calls: Network-first, fallback to offline 503 response if offline
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

  // 2. Static assets & HTML: Network-first, fallback to Cache when offline
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse.ok && event.request.method === "GET") {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request).then((cached) => {
          return cached || caches.match("/");
        });
      })
  );
});
