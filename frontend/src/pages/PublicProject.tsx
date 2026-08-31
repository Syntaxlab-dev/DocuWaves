import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Category, type Project } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n";

export function PublicProject() {
  const { projectSlug } = useParams<{ projectSlug: string }>();
  const { t } = useI18n();
  const [data, setData] = useState<{ project: Project; categories: Category[] } | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!projectSlug) return;
    setData(null);
    setNotFound(false);
    api
      .publicGetProject(projectSlug)
      .then(setData)
      .catch(() => setNotFound(true));
  }, [projectSlug]);

  if (notFound) return <p className="text-[var(--muted)]">{t("common.error")}</p>;
  if (!data) return <p className="text-[var(--muted)]">{t("common.loading")}</p>;

  return (
    <div>
      <div className="flex items-center gap-2">
        {data.project.icon && <span className="text-2xl">{data.project.icon}</span>}
        <h1 className="text-2xl font-semibold">{data.project.name}</h1>
      </div>
      {data.project.description && <p className="mt-1 text-[var(--muted)]">{data.project.description}</p>}

      <h2 className="mt-8 text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
        {t("project.categories")}
      </h2>
      {data.categories.length === 0 && <p className="mt-4 text-[var(--muted)]">{t("project.empty")}</p>}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.categories.map((c) => (
          <Link key={c.id} to={`/p/${data.project.slug}/c/${c.slug}`}>
            <Card className="h-full transition-transform hover:-translate-y-0.5">
              <CardHeader>
                <div className="flex items-center gap-2">
                  {c.icon && <span className="text-lg">{c.icon}</span>}
                  <CardTitle className="text-base font-semibold text-[var(--ink)]">{c.name}</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="text-sm text-[var(--muted)]">
                {c.page_count} {t("category.pages")}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
