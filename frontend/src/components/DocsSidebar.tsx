import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ProjectNav } from "@/lib/api";
import { FallbackBadge } from "@/components/FallbackBadge";
import { visibleCategories } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { cn } from "@/lib/utils";

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
  const { path } = useContentLang();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Only sections the reader has explicitly toggled land here; everything
  // else keeps following the active page as they navigate.
  const [toggled, setToggled] = useState<Record<string, boolean>>({});

  const categories = visibleCategories(nav);
  const expandAll = categories.reduce((total, c) => total + c.pages.length, 0) <= EXPAND_ALL_UP_TO;

  function toggle(slug: string, open: boolean) {
    setToggled((current) => ({ ...current, [slug]: !open }));
  }

  return (
    <div className="lg:w-60 lg:shrink-0">
      <button
        type="button"
        onClick={() => setMobileOpen((open) => !open)}
        aria-expanded={mobileOpen}
        aria-controls="docs-sidebar"
        className="flex w-full items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm font-medium lg:hidden"
      >
        {t("nav.contents")}
        {mobileOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>

      <nav
        id="docs-sidebar"
        aria-label={t("nav.contents")}
        className={cn(
          // Sticky only from lg up: on a phone it sits in the normal flow
          // above the page, where a sticky element would cover the text the
          // reader just navigated to.
          "mt-3 lg:mt-0 lg:sticky lg:top-6 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto",
          mobileOpen ? "block" : "hidden",
          "lg:block",
        )}
      >
        <Link
          to={path(`/p/${nav.project.slug}`)}
          className={cn(
            "flex items-center gap-2 text-sm font-semibold",
            activeCategorySlug || activePageSlug ? "text-[var(--ink)]" : "text-[var(--accent)]",
          )}
        >
          {nav.project.icon && <span>{nav.project.icon}</span>}
          {nav.project.name}
        </Link>

        <div className="mt-4 flex flex-col gap-4">
          {categories.map((category) => {
            const open = toggled[category.slug] ?? (expandAll || category.slug === activeCategorySlug);
            return (
              <div key={category.id}>
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
                    to={path(`/p/${nav.project.slug}/c/${category.slug}`)}
                    className={cn(
                      "text-xs font-semibold uppercase tracking-wide hover:text-[var(--accent)]",
                      category.slug === activeCategorySlug ? "text-[var(--ink)]" : "text-[var(--muted)]",
                    )}
                  >
                    {category.name}
                  </Link>
                </div>

                {open && (
                  <ul className="mt-1 flex flex-col border-l border-[var(--border)] pl-3 ml-2.5">
                    {category.pages.map((page) => {
                      const current = page.slug === activePageSlug;
                      return (
                        <li key={page.id}>
                          <Link
                            to={path(`/p/${nav.project.slug}/pages/${page.slug}`)}
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
