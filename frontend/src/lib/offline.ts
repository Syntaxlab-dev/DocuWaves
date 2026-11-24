import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * "Save for offline reading": fetches every published page of a project
 * once, so the service worker (public/sw.js) has them in its reading cache.
 * The requests are exactly the ones the reading pages make, so the cached
 * answers are found again under the same addresses. Images are kept as
 * they are seen; a page never opened online shows its text offline, and
 * its pictures once it has been opened.
 */
const SAVED_PREFIX = "docuwaves-offline:";

function savedKey(projectSlug: string, lang: string, version: string) {
  return `${SAVED_PREFIX}${projectSlug}|${lang}|${version}`;
}

export function offlineAvailable(): boolean {
  return typeof navigator !== "undefined" && "serviceWorker" in navigator && Boolean(navigator.serviceWorker.controller);
}

export function savedAt(projectSlug: string, lang: string, version: string): string {
  try {
    return window.localStorage.getItem(savedKey(projectSlug, lang, version)) ?? "";
  } catch {
    return "";
  }
}

export async function saveForOffline(
  projectSlug: string,
  lang: string,
  version: string,
  onProgress: (done: number, total: number) => void,
): Promise<number> {
  const l = lang || undefined;
  const v = version || undefined;
  const nav = await api.publicGetProjectNav(projectSlug, l, v);
  await Promise.allSettled([
    api.publicGetProject(projectSlug, l, v),
    api.publicListProjects(l),
    api.publicGetSite(),
    api.publicGlossary(projectSlug, l, v),
  ]);
  const pages = nav.categories.flatMap((c) => c.pages.map((p) => ({ category: c.slug, page: p.slug })));
  const categories = nav.categories.filter((c) => c.pages.length > 0);
  let done = 0;
  const total = pages.length + categories.length;
  onProgress(0, total);
  // A few at a time: fast, without queueing hundreds of requests at once.
  const queue: (() => Promise<unknown>)[] = [
    ...categories.map((c) => () => api.publicGetCategory(projectSlug, c.slug, l, v)),
    ...pages.map((p) => () => api.publicGetPage(projectSlug, p.page, l, v)),
  ];
  async function worker() {
    for (let next = queue.shift(); next; next = queue.shift()) {
      await next().catch(() => undefined);
      done += 1;
      onProgress(done, total);
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()]);
  try {
    window.localStorage.setItem(savedKey(projectSlug, lang, version), new Date().toISOString());
  } catch {
    // Saved all the same; only the "saved on" note is lost.
  }
  return pages.length;
}

/** Whether the browser is offline right now, kept up to date. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}
