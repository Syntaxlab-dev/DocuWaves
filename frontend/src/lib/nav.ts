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
 *  fallback language marked. `version` likewise: each documentation version
 *  has its own categories and pages. Both are "" on an instance/project that
 *  has neither, and the request is then the one it always was. */
export function useProjectNav(
  projectSlug: string | undefined,
  lang?: string,
  version?: string,
): { nav: ProjectNav | null; status: NavStatus } {
  const [nav, setNav] = useState<ProjectNav | null>(null);
  const [status, setStatus] = useState<NavStatus>("loading");

  useEffect(() => {
    if (!projectSlug) return;
    let current = true;
    setNav(null);
    setStatus("loading");
    api
      .publicGetProjectNav(projectSlug, lang, version)
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
    // `version` is a dependency for the same reason `lang` is: a reader who
    // switches version needs that version's own tree, since a category or
    // page can exist in one version and not in another.
  }, [projectSlug, lang, version]);

  return { nav, status };
}

/** Published pages in a category and everything nested under it. */
export function subtreePageCount(nav: ProjectNav, slug: string): number {
  return nav.categories.reduce(
    (total, c) => total + (c.slug === slug || categoryAncestors(nav, c.slug).some((a) => a.slug === slug) ? c.pages.length : 0),
    0,
  );
}

/** Categories worth showing: one with nothing published in it -- or under
 *  it -- is a dead end for a reader, and the nav endpoint deliberately
 *  leaves that call here. A section that holds only subsections stays: its
 *  subsections are reached through it. In the nav's own order, which is
 *  reading order (each category followed by the ones nested under it). */
export function visibleCategories(nav: ProjectNav): NavCategory[] {
  return nav.categories.filter((c) => subtreePageCount(nav, c.slug) > 0);
}

/** The visible categories at the top level -- the project's own tiles. */
export function topCategories(nav: ProjectNav): NavCategory[] {
  return visibleCategories(nav).filter((c) => !c.parent);
}

/** The visible categories directly under `slug`. */
export function subcategories(nav: ProjectNav, slug: string): NavCategory[] {
  return visibleCategories(nav).filter((c) => c.parent === slug);
}

/** The categories above `slug`, outermost first -- its breadcrumb. The
 *  server has already ruled out loops; the bound is only so a malformed
 *  response can never hang the page. */
export function categoryAncestors(nav: ProjectNav, slug: string): NavCategory[] {
  const bySlug = new Map(nav.categories.map((c) => [c.slug, c]));
  const chain: NavCategory[] = [];
  let cursor = bySlug.get(slug)?.parent;
  while (cursor && bySlug.has(cursor) && chain.length < 8) {
    const parent = bySlug.get(cursor)!;
    chain.unshift(parent);
    cursor = parent.parent;
  }
  return chain;
}

/** Reading order -- the sidebar's own order flattened across categories, so
 *  the last page of one category is followed by the first of the next (a
 *  category's own pages come before its subcategories'). */
export function readingOrder(nav: ProjectNav): { page: NavPage; category: NavCategory }[] {
  return visibleCategories(nav).flatMap((category) => category.pages.map((page) => ({ page, category })));
}
