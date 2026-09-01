import { Link, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DocsShell } from "@/components/DocsShell";
import { NotFound } from "@/components/NotFound";
import { useProjectNav, visibleCategories } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { useDocumentTitle } from "@/lib/site";

export function PublicProject() {
  const { projectSlug } = useParams<{ projectSlug: string }>();
  const { t } = useI18n();
  // The nav endpoint returns this project plus every category and its
  // published pages, which is a superset of what the tiles need -- so the
  // sidebar costs no extra request here, and the tiles can't disagree with
  // the tree standing next to them.
  const { nav, status } = useProjectNav(projectSlug);

  useDocumentTitle(nav?.project.name);

  if (status === "notfound") return <NotFound />;
  if (status === "failed") return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.error")}</p>;
  if (!nav) return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.loading")}</p>;

  const categories = visibleCategories(nav);

  return (
    <DocsShell nav={nav}>
      <div className="flex items-center gap-2">
        {nav.project.icon && <span className="text-2xl">{nav.project.icon}</span>}
        <h1 className="text-2xl font-semibold">{nav.project.name}</h1>
      </div>
      {nav.project.description && <p className="mt-1 text-[var(--muted)]">{nav.project.description}</p>}

      <h2 className="mt-8 text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
        {t("project.categories")}
      </h2>
      {categories.length === 0 && <p className="mt-4 text-[var(--muted)]">{t("project.empty")}</p>}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {categories.map((c) => (
          <Link key={c.id} to={`/p/${nav.project.slug}/c/${c.slug}`}>
            <Card className="h-full transition-transform hover:-translate-y-0.5">
              <CardHeader>
                <div className="flex items-center gap-2">
                  {c.icon && <span className="text-lg">{c.icon}</span>}
                  <CardTitle className="text-base font-semibold text-[var(--ink)]">{c.name}</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="text-sm text-[var(--muted)]">
                {c.pages.length} {t("category.pages")}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </DocsShell>
  );
}
