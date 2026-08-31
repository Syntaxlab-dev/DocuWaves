import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FileText } from "lucide-react";
import { api, type Category, type PageSummary, type Project } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function PublicCategory() {
  const { projectSlug, categorySlug } = useParams<{ projectSlug: string; categorySlug: string }>();
  const { t } = useI18n();
  const [data, setData] = useState<{ project: Project; category: Category; pages: PageSummary[] } | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!projectSlug || !categorySlug) return;
    setData(null);
    setNotFound(false);
    api
      .publicGetCategory(projectSlug, categorySlug)
      .then(setData)
      .catch(() => setNotFound(true));
  }, [projectSlug, categorySlug]);

  if (notFound) return <p className="text-[var(--muted)]">{t("common.error")}</p>;
  if (!data) return <p className="text-[var(--muted)]">{t("common.loading")}</p>;

  return (
    <div>
      <Link to={`/p/${data.project.slug}`} className="text-sm text-[var(--accent)]">
        ← {data.project.name}
      </Link>
      <div className="mt-2 flex items-center gap-2">
        {data.category.icon && <span className="text-2xl">{data.category.icon}</span>}
        <h1 className="text-2xl font-semibold">{data.category.name}</h1>
      </div>

      <div className="mt-6 flex flex-col divide-y divide-[var(--border)] rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        {data.pages.map((p) => (
          <Link
            key={p.id}
            to={`/p/${data.project.slug}/pages/${p.slug}`}
            className="flex items-center gap-2 px-4 py-3 text-sm hover:bg-[var(--surface-2)]"
          >
            <FileText className="h-4 w-4 text-[var(--muted)]" />
            {p.title}
          </Link>
        ))}
      </div>
    </div>
  );
}
