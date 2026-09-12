/* ORCA service worker — static app shell only.
 *
 * Scientific API responses are network-only so stale observations are never
 * presented as fresh. OSM tiles are also left to normal HTTP caching (through
 * the ORCA Box proxy), which preserves the upstream cache policy and avoids
 * prohibited offline/bulk tile storage.
 */
const SHELL = "orca-shell-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(
  Promise.all([
    self.clients.claim(),
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== SHELL).map((key) => caches.delete(key)),
    )),
  ]),
));

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  const isShell = url.origin === self.location.origin && url.pathname.startsWith("/_next/static");
  if (!isShell) return; // HTML, APIs and map tiles use the network/browser cache.

  event.respondWith(
    caches.open(SHELL).then(async (cache) => {
      const hit = await cache.match(request);
      if (hit) return hit;
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone());
      return response;
    }),
  );
});
