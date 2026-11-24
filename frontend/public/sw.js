/*
 * DocuWaves' service worker: what makes the documentation readable offline
 * and the site installable as an app.
 *
 * What it keeps, and how:
 *   - The app itself (/assets/*, content-hashed): cache first -- a file of
 *     that name never changes.
 *   - What a reader reads (GET /api/public/*): network first, the cached
 *     copy only when the network fails. A reader online always sees the
 *     current page; offline they see the last one they (or "Save for
 *     offline reading") fetched.
 *   - Page addresses (navigations): network first, the app shell offline,
 *     which then reads from the cache above.
 * What it never touches: anything that is not a GET, the admin API, sign-in,
 * the chat, exports, other origins. Signing out empties the reading cache
 * (lib/offlineCache.ts), since it may hold private projects.
 *
 * Plain JavaScript in public/, not part of the bundle: a service worker's
 * address must stay the same from release to release.
 */
const SHELL_CACHE = "docuwaves-shell-v1";
const ASSET_CACHE = "docuwaves-assets-v1";
const READ_CACHE = "docuwaves-read-v1";
const KEEP = [SHELL_CACHE, ASSET_CACHE, READ_CACHE];
const SHELL = "/index.html";
const NOT_CACHED = [/^\/api\/public\/chat/, /^\/api\/public\/feedback/, /\/export\//];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll([SHELL, "/favicon.svg", "/icon-192.png"]))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((n) => n.startsWith("docuwaves-") && !KEEP.includes(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function navigation(request) {
  try {
    const response = await fetch(request);
    // Keep the newest shell: a release changes the bundle it names.
    if (response.ok) {
      const cache = await caches.open(SHELL_CACHE);
      await cache.put(SHELL, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(SHELL);
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cacheFirst(request, ASSET_CACHE));
  } else if (url.pathname.startsWith("/api/public/")) {
    if (NOT_CACHED.some((re) => re.test(url.pathname))) return;
    event.respondWith(networkFirst(request, READ_CACHE));
  } else if (request.mode === "navigate" && !url.pathname.startsWith("/api/")) {
    event.respondWith(navigation(request));
  }
});
