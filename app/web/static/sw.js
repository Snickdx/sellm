/* sellm service worker — cache static shell; network for app/API. */
const CACHE_VERSION = "sellm-pwa-v7";
const PRECACHE = [
  "/offline.html",
  "/manifest.json",
  "/favicon.ico",
  "/favicon.svg",
  "/apple-touch-icon.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-192.png",
  "/icons/icon-maskable-512.png",
  "/static/brand/logo-mark.svg",
  "/static/brand/logo-horizontal-dark.svg",
  "/static/components/shell-extra.css?v=7",
  "/static/components/api.js?v=3",
  "/static/components/claim.js?v=1",
  "/static/components/exit-voice.js?v=1",
  "/static/components/exit.js?v=25",
  "/static/components/group.js?v=2",
  "/static/components/chat.js?v=28",
  "/static/components/router.js?v=4",
  "/static/components/admin.js?v=20",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isApiOrAuth(url) {
  return url.pathname.startsWith("/api/");
}

function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/static/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname === "/manifest.json" ||
    url.pathname === "/favicon.ico" ||
    url.pathname === "/favicon.svg" ||
    url.pathname === "/apple-touch-icon.png" ||
    url.pathname.startsWith("/favicon-") ||
    url.pathname === "/offline.html"
  );
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Never cache API / auth responses.
  if (isApiOrAuth(url)) return;

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => res)
        .catch(async () => {
          const cache = await caches.open(CACHE_VERSION);
          return (await cache.match("/offline.html")) || Response.error();
        })
    );
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const network = fetch(req)
          .then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(CACHE_VERSION).then((cache) => cache.put(req, copy));
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
