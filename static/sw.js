// Service worker: makes the app installable and lets previously-viewed
// pages open without using data. Bump CACHE_NAME whenever style.css or
// this file changes, so devices pick up the new version instead of an
// old cached copy.
const CACHE_NAME = "timetable-cache-v1";

const APP_SHELL = [
  "/static/style.css",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/offline",
];

// --- Install: pre-cache the app shell (CSS, icons, manifest, offline page) ---
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// --- Activate: drop any old cache versions ---
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// --- Fetch strategy ---
// - Only GET requests are cached. POST (adding/deleting/saving data) always
//   goes straight to the network, since that's the only place it can be
//   saved — no offline editing.
// - Page navigations: try the network first (to always get fresh timetable
//   data when there's a connection); if that fails, fall back to whatever
//   copy of that page is in the cache, or the offline page as a last resort.
// - Static assets (css/icons/manifest): cache-first, since they rarely change.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const isStaticAsset = url.pathname.startsWith("/static/");

  if (isStaticAsset) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request))
    );
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) => cached || caches.match("/offline"))
      )
  );
});
