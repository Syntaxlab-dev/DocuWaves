import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Category, type Page, type Project } from "@/lib/api";
import { MarkdownView } from "@/components/MarkdownView";
import { useI18n } from "@/lib/i18n";

export function PublicPage() {
  const { projectSlug, pageSlug } = useParams<{ projectSlug: string; pageSlug: string }>();
  const { t } = useI18n();
  const [data, setData] = useState<{ project: Project; category: Category; page: Page } | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!projectSlug || !pageSlug) return;
    setData(null);
    setNotFound(false);
    api
      .publicGetPage(projectSlug, pageSlug)
      .then(setData)
      .catch(() => setNotFound(true));
  }, [projectSlug, pageSlug]);

  if (notFound) return <p className="text-[var(--muted)]">{t("common.error")}</p>;
  if (!data) return <p className="text-[var(--muted)]">{t("common.loading")}</p>;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-1 text-sm text-[var(--muted)]">
        <Link to={`/p/${data.project.slug}`} className="hover:text-[var(--accent)]">
          {data.project.name}
        </Link>
        <span>/</span>
        <Link to={`/p/${data.project.slug}/c/${data.category.slug}`} className="hover:text-[var(--accent)]">
          {data.category.name}
        </Link>
      </div>
      <h1 className="mt-2 text-2xl font-semibold">{data.page.title}</h1>
      <div className="mt-4">
        <MarkdownView
          content={data.page.markdown_content}
          projectSlug={data.project.slug}
          categorySlug={data.category.slug}
        />
      </div>
    </div>
  );
}
