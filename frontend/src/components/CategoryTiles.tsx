import { Link } from "react-router-dom";
import { EntityIcon } from "@/components/EntityIcon";
import { ChevronRight } from "lucide-react";
import { CoverImage } from "@/components/CoverImage";
import type { NavCategory, ProjectNav } from "@/lib/api";
import { subtreePageCount } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";

/** How many of a category's pages a tile names. Three is a taste of what is
 *  in there; more turns the tile into the category page itself. */
const TOP_PAGES = 3;

/** The category tiles of a project's home, of the instance's home when it
 *  has one project, and of a category's subcategories -- one tile, so the
 *  three stay the same list reached from different levels. The count is
 *  everything under the tile, subsections included: a section holding only
 *  subsections is not "0 pages".
 *
 *  With `pageHref`, a tile also names its first pages, so a reader looking
 *  for "Mains connection" can go there in one click instead of two. The
 *  whole tile stays a target for the category: its title link is stretched
 *  over the card, and the page links sit above that layer. */
export function CategoryTiles({
  nav,
  categories,
  href,
  pageHref,
}: {
  nav: ProjectNav;
  categories: NavCategory[];
  href: (category: NavCategory) => string;
  pageHref?: (slug: string) => string;
}) {
  const { t } = useI18n();
  return (
    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {categories.map((c) => {
        const count = subtreePageCount(nav, c.slug);
        const top = pageHref ? c.pages.slice(0, TOP_PAGES) : [];
        const more = count - top.length;
        return (
          <div
            key={c.id}
            className={`group relative flex h-full flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)] transition hover:-translate-y-0.5 hover:border-[var(--accent)]${
              c.image_url ? " overflow-hidden" : ""
            }`}
          >
            <CoverImage url={c.image_url} />
            <div className="flex flex-1 flex-col p-5">
              <div className="flex items-center gap-2">
                {c.icon && (
                  <span className="text-lg" aria-hidden="true">
                    <EntityIcon icon={c.icon} className="h-5 w-5" />
                  </span>
                )}
                <Link
                  to={href(c)}
                  className="font-semibold text-[var(--ink)] after:absolute after:inset-0 after:rounded-xl group-hover:text-[var(--accent)]"
                >
                  {c.name}
                  {/* The total, for whoever hears the link rather than
                      sees the tile: the visible line below may say "and
                      4 more" instead. */}
                  <span className="sr-only">
                    {" "}
                    {count} {t("category.pages")}
                  </span>
                </Link>
              </div>
              {top.length > 0 && (
                <ul className="relative z-10 mt-3 space-y-1 text-sm">
                  {top.map((p) => (
                    <li key={p.id}>
                      <Link
                        to={pageHref!(p.slug)}
                        className="flex items-center gap-1 text-[var(--muted)] hover:text-[var(--accent)]"
                      >
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" aria-hidden="true" />
                        <span className="truncate">{p.title}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-auto pt-3 text-xs text-[var(--muted)]">
                {top.length > 0 && more > 0
                  ? t("category.morePages").replace("{n}", String(more))
                  : `${count} ${t("category.pages")}`}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
