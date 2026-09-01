import { Link, useParams } from "react-router-dom";
import { FileText } from "lucide-react";
import { DocsShell } from "@/components/DocsShell";
import { NotFound } from "@/components/NotFound";
import { useProjectNav, visibleCategories } from "@/lib/nav";
import { FallbackBadge } from "@/components/FallbackBadge";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocumentTitle } from "@/lib/site";

export function PublicCategory() {
  const { projectSlug, categorySlug } = useParams<{ projectSlug: string; categorySlug: string }>();
  const { t } = useI18n();
  const { lang, path } = useContentLang();
  const { nav, status } = useProjectNav(projectSlug, lang);

  // A category with nothing published in it is 404 here for the same reason
  // it isn't a tile on the project page: it exists in the content repo, but
  // there is nothing behind it a visitor is allowed to read. Resolved before
  // the early returns below so the title hook can sit above them too.
  const category = nav ? visibleCategories(nav).find((c) => c.slug === categorySlug) : undefined;

  useDocumentTitle(category?.name);

  if (status === "notfound") return <NotFound />;
  if (status === "failed") return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.error")}</p>;
  if (!nav) return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.loading")}</p>;
  if (!category) return <NotFound />;

  return (
    <DocsShell nav={nav} activeCategorySlug={category.slug}>
      <Link to={path(`/p/${nav.project.slug}`)} className="text-sm text-[var(--accent)]">
        ← {nav.project.name}
      </Link>
      <div className="mt-2 flex items-center gap-2">
        {category.icon && <span className="text-2xl">{category.icon}</span>}
        <h1 className="text-2xl font-semibold">{category.name}</h1>
      </div>

      <div className="mt-6 flex flex-col divide-y divide-[var(--border)] rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        {category.pages.map((p) => (
          <Link
            key={p.id}
            to={path(`/p/${nav.project.slug}/pages/${p.slug}`)}
            className="flex items-center gap-2 px-4 py-3 text-sm hover:bg-[var(--surface-2)]"
          >
            <FileText className="h-4 w-4 text-[var(--muted)]" />
            {p.title}
            {p.fallback && <FallbackBadge language={p.language ?? ""} />}
          </Link>
        ))}
      </div>
    </DocsShell>
  );
}
