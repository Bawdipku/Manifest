// Cache only the public shell. Authenticated records and documents are never cached.
const CACHE = "manifest-shell-2";
const ASSETS = [
  "/",
  "/app.js",
  "/app.css",
  "/favicon.svg",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
];
self.addEventListener("install", (e) =>
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS))),
);
self.addEventListener("activate", (e) =>
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("manifest-") && k !== CACHE)
            .map((k) => caches.delete(k)),
        ),
      ),
  ),
);
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (
    e.request.method === "GET" &&
    url.origin === location.origin &&
    ASSETS.includes(url.pathname)
  )
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
