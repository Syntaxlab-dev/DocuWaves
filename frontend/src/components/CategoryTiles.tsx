import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CoverImage } from "@/components/CoverImage";
import type { NavCategory, ProjectNav } from "@/lib/api";
import { subtreePageCount } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";

/** The category tiles of a project's home, of the instance's home when it
 *  has one project, and of a category's subcategories -- one tile, so the
 *  three stay the same list reached from different levels. The count is
 *  everything under the tile, subsections included: a section holding only
 *  subsections is not "0 pages". */
export function CategoryTiles({
  nav,
  categories,
  href,
}: {
  nav: ProjectNav;
  categories: NavCategory[];
  href: (category: NavCategory) => string;
}) {
  const { t } = useI18n();
  return (
    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {categories.map((c) => (
        <Link key={c.id} to={href(c)}>
          {/* The conditional overflow-hidden -- see CoverImage. */}
          <Card className={`h-full transition-transform hover:-translate-y-0.5${c.image_url ? " overflow-hidden" : ""}`}>
            <CoverImage url={c.image_url} />
            <CardHeader>
              <div className="flex items-center gap-2">
                {c.icon && <span className="text-lg">{c.icon}</span>}
                <CardTitle className="text-base font-semibold text-[var(--ink)]">{c.name}</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="text-sm text-[var(--muted)]">
              {subtreePageCount(nav, c.slug)} {t("category.pages")}
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
