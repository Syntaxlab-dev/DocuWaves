import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CoverImage } from "@/components/CoverImage";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useProjectNav, visibleCategories } from "@/lib/nav";
import { siteText, useDocumentTitle, useSite } from "@/lib/site";

export function PublicHome() {
  const { t } = useI18n();
  const { site } = useSite();
  const { lang, path } = useContentLang();
  const [projects, setProjects] = useState<Project[] | null>(null);

  // No page title of its own -- the home page IS the site.
  useDocumentTitle();

  useEffect(() => {
    // Project names/descriptions come back in the reader's language, so a
    // language switch has to refetch rather than reuse the cached list.
    api.publicListProjects(lang).then((r) => setProjects(r.projects));
  }, [lang]);

  // An instance documenting ONE thing -- which is most of them -- had a home
  // page whose entire content was a single tile in a three-column grid, and
  // a click to get past it. It shows that project's categories instead, so
  // the first screen is the documentation rather than a lobby. The hook is
  // called unconditionally with an undefined slug until there is one; it
  // fetches nothing in that state.
  const soleProject = projects && projects.length === 1 ? projects[0] : null;
  const { nav } = useProjectNav(soleProject?.slug, lang);
  const soleCategories =
    soleProject && nav && nav.project.slug === soleProject.slug ? visibleCategories(nav) : null;
  // A project with no categories yet falls back to the tile: the alternative
  // is a heading with nothing under it, which is emptier than what we set
  // out to fix.
  const showCategories = soleCategories !== null && soleCategories.length > 0;

  // The configured tagline is what this instance is FOR; the generic "choose
  // a project" line stands in until someone writes one -- but only where
  // there IS a project to choose. Showing the sole project's categories
  // instead, that sentence describes a choice the page no longer offers, so
  // the project's own description stands in, and nothing at all if it has
  // none. A missing subtitle is better than a wrong one.
  const subtitle =
    siteText(site, "tagline", lang) || (showCategories ? soleProject?.description || "" : t("home.subtitle"));

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">{siteText(site, "name", lang)}</h1>
      {subtitle && <p className="mt-1 text-[var(--muted)]">{subtitle}</p>}

      {projects === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {projects !== null && projects.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("home.empty")}</p>}

      {projects !== null && projects.length > 0 && (
        <h2 className="mt-8 text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
          {showCategories ? t("project.categories") : t("home.title")}
        </h2>
      )}

      {soleProject && soleCategories && soleCategories.length > 0 && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {soleCategories.map((c) => (
            <Link key={c.id} to={path(`/p/${soleProject.slug}/c/${c.slug}`)}>
              {/* Same tile as the project page's, deliberately -- this is
                  the same list, reached from one level up. */}
              <Card className={`h-full transition-transform hover:-translate-y-0.5${c.image_url ? " overflow-hidden" : ""}`}>
                <CoverImage url={c.image_url} />
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
      )}

      {!showCategories && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects?.map((p) => (
            <Link key={p.id} to={path(`/p/${p.slug}`)}>
              {/* overflow-hidden only when there IS a cover to clip, so a
                  project without one renders the tile it always did, class
                  for class. */}
              <Card className={`h-full transition-transform hover:-translate-y-0.5${p.image_url ? " overflow-hidden" : ""}`}>
                <CoverImage url={p.image_url} />
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
      )}
    </div>
  );
}
