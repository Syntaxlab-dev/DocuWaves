import { useEffect, useState } from "react";
import { ApiError, api, type NavCategory, type NavPage, type ProjectNav } from "@/lib/api";

/** "notfound" is kept apart from "failed" on purpose: an unknown slug is a
 *  404 view with a way back, a network/server failure is an error message --
 *  telling a reader their URL is wrong when the server merely fell over
 *  would send them looking for a mistake they didn't make. */
export type NavStatus = "loading" | "ready" | "notfound" | "failed";

/** The project's whole published structure IN ONE CONTENT LANGUAGE, which
 *  the project, category and page views all need (the sidebar is on all
 *  three). One hook rather than the same effect copied into each of them.
 *
 *  `lang` is part of the effect's dependencies, not just of the URL: a
 *  reader switching language has to get the tree back in that language --
 *  with the titles translated, and with the pages that only exist in the
 *  fallback language marked. */
export function useProjectNav(
  projectSlug: string | undefined,
  lang?: string,
): { nav: ProjectNav | null; status: NavStatus } {
  const [nav, setNav] = useState<ProjectNav | null>(null);
  const [status, setStatus] = useState<NavStatus>("loading");

  useEffect(() => {
    if (!projectSlug) return;
    let current = true;
    setNav(null);
    setStatus("loading");
    api
      .publicGetProjectNav(projectSlug, lang)
      .then((data) => {
        if (!current) return;
        setNav(data);
        setStatus("ready");
      })
      .catch((error) => {
        if (!current) return;
        setStatus(error instanceof ApiError && error.status === 404 ? "notfound" : "failed");
      });
    // A reader clicking through the sidebar changes projectSlug faster than
    // a slow response arrives; without this the older response would land
    // last and overwrite the newer project's tree.
    return () => {
      current = false;
    };
  }, [projectSlug, lang]);

  return { nav, status };
}

/** Categories worth showing: one with nothing published in it is a dead end
 *  for a reader, and the nav endpoint deliberately leaves that call here. */
export function visibleCategories(nav: ProjectNav): NavCategory[] {
  return nav.categories.filter((c) => c.pages.length > 0);
}

/** Reading order -- the sidebar's own order flattened across categories, so
 *  the last page of one category is followed by the first of the next. */
export function readingOrder(nav: ProjectNav): { page: NavPage; category: NavCategory }[] {
  return visibleCategories(nav).flatMap((category) => category.pages.map((page) => ({ page, category })));
}
