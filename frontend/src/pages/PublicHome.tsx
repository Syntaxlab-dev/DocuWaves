import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n";

export function PublicHome() {
  const { t } = useI18n();
  const [projects, setProjects] = useState<Project[] | null>(null);

  useEffect(() => {
    api.publicListProjects().then((r) => setProjects(r.projects));
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">{t("home.title")}</h1>
      <p className="mt-1 text-[var(--muted)]">{t("home.subtitle")}</p>

      {projects === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {projects !== null && projects.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("home.empty")}</p>}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects?.map((p) => (
          <Link key={p.id} to={`/p/${p.slug}`}>
            <Card className="h-full transition-transform hover:-translate-y-0.5">
              <CardHeader>
                <div className="flex items-center gap-2">
                  {p.icon && <span className="text-xl">{p.icon}</span>}
                  <CardTitle className="text-base font-semibold text-[var(--ink)]">{p.name}</CardTitle>
                </div>
              </CardHeader>
              {p.description && <CardContent className="text-sm text-[var(--muted)]">{p.description}</CardContent>}
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
