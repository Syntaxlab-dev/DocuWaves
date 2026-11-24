/**
 * The service worker's reading cache (public/sw.js), seen from the page.
 * Its own module so that lib/api.ts can empty it on sign-out without
 * importing the offline-saving code, which imports the API.
 */
export const READ_CACHE = "docuwaves-read-v1";

/** Forgets everything kept for offline reading -- on sign-out, because a
 *  signed-in reader's cache may hold private projects. */
export async function clearReadingCache(): Promise<void> {
  try {
    if ("caches" in window) await caches.delete(READ_CACHE);
  } catch {
    // No cache to clear, or storage blocked: nothing kept either.
  }
}

/** Registers the service worker in a production build. Not in development,
 *  where it would serve yesterday's bundle against today's code. */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Not installable then; the site works exactly as before.
    });
  });
}
