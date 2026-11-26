import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, ListFilter, Menu, Search, X } from "lucide-react";
import type { NavCategory, ProjectNav } from "@/lib/api";
import { FallbackBadge } from "@/components/FallbackBadge";
import { categoryAncestors, visibleCategories } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocPath } from "@/lib/version";
import { cn } from "@/lib/utils";
import { readStored, writeStored } from "@/lib/theme";

/**
 * Up to this many published pages in a project, every section starts open:
 * the whole tree is then still roughly a screenful in the sticky column, so
 * collapsing it would hide navigation to save space that isn't scarce, and
 * cost a reader a click to see what a small project even contains. Beyond
 * it, only the section the reader is currently in opens and the rest are
 * one click away -- which is also about where an all-open tree starts
 * needing a scrollbar of its own next to the page's.
 */
const EXPAND_ALL_UP_TO = 12;

export function DocsSidebar({
  nav,
  activeCategorySlug,
  activePageSlug,
}: {
  nav: ProjectNav;
  activeCategorySlug?: string;
  activePageSlug?: string;
}) {
  const { t } = useI18n();
  const docPath = useDocPath();
  const { path } = useContentLang();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [q, setQ] = useState("");
  // Only sections the reader has explicitly toggled land here; everything
  // else keeps following the active page as they navigate. Remembered per
  // project in this browser, so a section closed yesterday stays closed.
  const storageKey = `docuwaves-sidebar:${nav.project.slug}`;
  const [toggled, setToggled] = useState<Record<string, boolean>>(() => loadToggled(storageKey));
  const [toggledFor, setToggledFor] = useState(storageKey);
  if (toggledFor !== storageKey) {
    setToggledFor(storageKey);
    setToggled(loadToggled(storageKey));
  }
  const [filter, setFilter] = useState("");

  const categories = visibleCategories(nav);
  const expandAll = categories.reduce((total, c) => total + c.pages.length, 0) <= EXPAND_ALL_UP_TO;

  // The section being read and every section it sits in start open, so the
  // reader can see where they are however deep that is.
  const activeChain = new Set(
    activeCategorySlug ? [activeCategorySlug, ...categoryAncestors(nav, activeCategorySlug).map((c) => c.slug)] : [],
  );
  // Filtering: the pages whose title has the text in it, plus every page of
  // a section whose name does; each section with a match, and the sections
  // around it, shown open. Everything else is out of the way until the
  // field is empty again.
  const needle = filter.trim().toLocaleLowerCase();
  const matches = needle ? filterNav(categories, needle, (slug) => categoryAncestors(nav, slug)) : null;
  const isOpen = (slug: string) =>
    matches ? matches.sections.has(slug) : (toggled[slug] ?? (expandAll || activeChain.has(slug)));

  function toggle(slug: string, open: boolean) {
    setToggled((current) => {
      const next = { ...current, [slug]: !open };
      writeStored(storageKey, JSON.stringify(next));
      return next;
    });
  }

  // On a phone the contents are a drawer over the page. It closes when the
  // reader goes somewhere (which is what they opened it for), on Escape,
  // and on a tap beside it; while open, the page under it stays put.
  // Adjusting state during render rather than in an effect: the drawer
  // must already be shut in the render that shows the new page.
  const [drawerPath, setDrawerPath] = useState(pathname);
  if (drawerPath !== pathname) {
    setDrawerPath(pathname);
    setMobileOpen(false);
  }
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMobileOpen(false);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [mobileOpen]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    if (q.trim()) navigate(path(`/search?q=${encodeURIComponent(q.trim())}`));
  }

  return (
    <div className="lg:w-60 lg:shrink-0">
      <button
        type="button"
        onClick={() => setMobileOpen((open) => !open)}
        aria-expanded={mobileOpen}
        aria-controls="docs-sidebar"
        className="flex w-full items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm font-medium lg:hidden"
      >
        <Menu className="h-4 w-4" aria-hidden="true" />
        {t("nav.contents")}
      </button>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" aria-hidden="true" onClick={() => setMobileOpen(false)} />
      )}

      <nav
        id="docs-sidebar"
        aria-label={t("nav.contents")}
        className={cn(
          // Sticky only from lg up: on a phone it sits in the normal flow
          // above the page, where a sticky element would cover the text the
          // reader just navigated to.
          // Below lg it is a drawer from the left, over the page.
          "lg:sticky lg:top-6 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto",
          "max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-50 max-lg:w-80 max-lg:max-w-[85vw] max-lg:overflow-y-auto",
          "max-lg:border-r max-lg:border-[var(--border)] max-lg:bg-[var(--bg)] max-lg:p-4 max-lg:shadow-2xl",
          "docs-drawer",
          mobileOpen ? "block" : "hidden",
          "lg:block",
        )}
      >
        <div className="mb-4 flex items-center gap-2 lg:hidden">
          <form onSubmit={onSearch} role="search" className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted)]"
              aria-hidden="true"
            />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("nav.search")}
              aria-label={t("nav.search")}
              className="h-10 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] pl-8 pr-2 text-sm outline-none focus:border-[var(--accent)]"
            />
          </form>
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label={t("reader.close")}
            className="rounded-lg p-2 text-[var(--muted)] hover:bg-[var(--surface-2)]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <Link
          to={docPath(nav.project.slug, "")}
          className={cn(
            "flex items-center gap-2 text-sm font-semibold",
            activeCategorySlug || activePageSlug ? "text-[var(--ink)]" : "text-[var(--accent)]",
          )}
        >
          {nav.project.icon && <span>{nav.project.icon}</span>}
          {nav.project.name}
        </Link>

        {!expandAll && (
          <div className="relative mt-3">
            <ListFilter
              className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted)]"
              aria-hidden="true"
            />
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && filter && (e.stopPropagation(), setFilter(""))}
              placeholder={t("reader.filter")}
              aria-label={t("reader.filter")}
              className="h-8 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] pl-8 pr-2 text-sm outline-none focus:border-[var(--accent)]"
            />
          </div>
        )}
        {matches && matches.sections.size === 0 && (
          <p className="mt-4 text-sm text-[var(--muted)]">{t("reader.filterEmpty")}</p>
        )}

        <div className="mt-4 flex flex-col gap-4">
          {categories.map((category) => {
            if (matches && !matches.sections.has(category.slug)) return null;
            const shown = matches ? category.pages.filter((page) => matches.pages.has(page.id)) : category.pages;
            // A subsection is drawn only while every section above it is
            // open -- a closed section closes everything under it.
            const ancestors = categoryAncestors(nav, category.slug);
            if (!ancestors.every((a) => isOpen(a.slug))) return null;
            const open = isOpen(category.slug);
            const depth = ancestors.length;
            return (
              <div key={category.id} style={depth ? { marginLeft: `${depth * 0.75}rem`, marginTop: "-0.5rem" } : undefined}>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => toggle(category.slug, open)}
                    aria-expanded={open}
                    aria-label={category.name}
                    className="rounded p-0.5 text-[var(--muted)] hover:bg-[var(--surface-2)]"
                  >
                    {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </button>
                  <Link
                    to={docPath(nav.project.slug, `/c/${category.slug}`)}
                    className={cn(
                      "flex min-w-0 items-center gap-1.5 text-sm hover:text-[var(--accent)]",
                      // The top level reads as a section by weight and its
                      // icon, not by shouting in capitals; a subsection is
                      // an entry inside it.
                      depth ? "font-medium" : "font-semibold",
                      category.slug === activeCategorySlug
                        ? "text-[var(--ink)]"
                        : depth
                          ? "text-[var(--muted)]"
                          : "text-[var(--ink)] opacity-80",
                    )}
                  >
                    {!depth && category.icon && (
                      <span className="w-5 shrink-0 text-center text-base leading-none" aria-hidden="true">
                        {category.icon}
                      </span>
                    )}
                    <span className="truncate">{category.name}</span>
                  </Link>
                </div>

                {open && shown.length > 0 && (
                  <ul className="mt-1 flex flex-col border-l border-[var(--border)] pl-3 ml-2.5">
                    {shown.map((page) => {
                      const current = page.slug === activePageSlug;
                      return (
                        <li key={page.id}>
                          <Link
                            to={docPath(nav.project.slug, `/pages/${page.slug}`)}
                            // aria-current is what tells a screen reader
                            // which entry is the page being read; the
                            // colour alone says it to nobody else.
                            aria-current={current ? "page" : undefined}
                            className={cn(
                              "-ml-3 block border-l-2 py-1 pl-3 text-sm",
                              current
                                ? "border-[var(--accent)] font-medium text-[var(--accent)]"
                                : "border-transparent text-[var(--muted)] hover:text-[var(--ink)]",
                            )}
                          >
                            {page.title}
                            {/* Listed like any other page -- it is
                                readable -- but marked, so the language it
                                opens in isn't a surprise. */}
                            {page.fallback && <FallbackBadge language={page.language ?? ""} />}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function loadToggled(key: string): Record<string, boolean> {
  try {
    const raw = JSON.parse(readStored(key) ?? "{}");
    return raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

/** What a sidebar filter leaves standing: the matching pages (by id) and
 *  the sections to show -- those with a match and everything around them. */
export function filterNav(
  categories: NavCategory[],
  needle: string,
  ancestors: (slug: string) => { slug: string }[],
): { pages: Set<number>; sections: Set<string> } {
  const pages = new Set<number>();
  const sections = new Set<string>();
  for (const c of categories) {
    const whole = c.name.toLocaleLowerCase().includes(needle);
    const hits = c.pages.filter((p) => whole || p.title.toLocaleLowerCase().includes(needle));
    if (!whole && hits.length === 0) continue;
    hits.forEach((p) => pages.add(p.id));
    sections.add(c.slug);
    ancestors(c.slug).forEach((a) => sections.add(a.slug));
  }
  return { pages, sections };
}
