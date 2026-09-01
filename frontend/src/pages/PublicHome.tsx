import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/lib/i18n";
import { useDocumentTitle, useSite } from "@/lib/site";

export function PublicHome() {
  const { t } = useI18n();
  const { site } = useSite();
  const [projects, setProjects] = useState<Project[] | null>(null);

  // No page title of its own -- the home page IS the site.
  useDocumentTitle();

  useEffect(() => {
    api.publicListProjects().then((r) => setProjects(r.projects));
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">{site.name}</h1>
      {/* The configured tagline is what this instance is FOR; the generic
          "choose a project" line stands in until someone writes one. */}
      <p className="mt-1 text-[var(--muted)]">{site.tagline || t("home.subtitle")}</p>

      {projects === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {projects !== null && projects.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("home.empty")}</p>}

      {projects !== null && projects.length > 0 && (
        <h2 className="mt-8 text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("home.title")}</h2>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
