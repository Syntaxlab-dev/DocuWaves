import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { api, type ChangelogEntry, type Project } from "@/lib/api";
import { formatIsoDate } from "@/lib/dates";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CoverImage } from "@/components/CoverImage";
import { PrivateBadge } from "@/components/PrivateBadge";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { topCategories, useProjectNav } from "@/lib/nav";
import { CategoryTiles } from "@/components/CategoryTiles";
import { siteText, useDocumentTitle, useSite } from "@/lib/site";

/** How many changes the home page names; the rest are one click away. */
const RECENT_COUNT = 5;

export function PublicHome() {
  const { t, lang: uiLang } = useI18n();
  const { site } = useSite();
  const { lang, path } = useContentLang();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [recent, setRecent] = useState<ChangelogEntry[]>([]);
  const [q, setQ] = useState("");

  // No page title of its own -- the home page IS the site.
  useDocumentTitle();

  useEffect(() => {
    // Project names/descriptions come back in the reader's language, so a
    // language switch has to refetch rather than reuse the cached list.
    api.publicListProjects(lang).then((r) => setProjects(r.projects));
    // The same list as /changes, its newest few. Quietly absent when it
    // can't be had: it is a pointer, not the page's content.
    api
      .changelog(lang)
      .then((r) => setRecent(r.entries.slice(0, RECENT_COUNT)))
      .catch(() => setRecent([]));
  }, [lang]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    if (q.trim()) navigate(path(`/search?q=${encodeURIComponent(q.trim())}`));
  }

  // An instance documenting ONE thing -- which is most of them -- had a home
  // page whose entire content was a single tile in a three-column grid, and
  // a click to get past it. It shows that project's categories instead, so
  // the first screen is the documentation rather than a lobby. The hook is
  // called unconditionally with an undefined slug until there is one; it
  // fetches nothing in that state.
  const soleProject = projects && projects.length === 1 ? projects[0] : null;
  const { nav } = useProjectNav(soleProject?.slug, lang);
  const soleCategories =
    soleProject && nav && nav.project.slug === soleProject.slug ? topCategories(nav) : null;
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

  // The sole project's cover, when it has one, is the home page's banner:
  // it is the picture somebody already chose for exactly this documentation.
  const cover = showCategories ? soleProject?.image_url : null;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* The first screen asks the one question most visitors arrived with
          -- "where is the bit about X?" -- with a field big enough to be
          the obvious first move, instead of a heading and a link. */}
      <header className="home-hero relative isolate overflow-hidden rounded-2xl border border-[var(--border)] px-5 py-10 text-center sm:px-10 sm:py-14">
        {cover && (
          <img
            src={cover}
            alt=""
            className="absolute inset-0 -z-10 h-full w-full object-cover opacity-20"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        )}
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{siteText(site, "name", lang)}</h1>
        {subtitle && <p className="mx-auto mt-2 max-w-xl text-[var(--muted)] sm:text-lg">{subtitle}</p>}
        <form onSubmit={onSearch} role="search" className="mx-auto mt-6 max-w-xl">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[var(--muted)]"
              aria-hidden="true"
            />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("home.searchPlaceholder")}
              aria-label={t("home.searchPlaceholder")}
              className="h-14 w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] pl-12 pr-4 text-base shadow-[var(--shadow)] outline-none transition focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent-soft)]"
            />
          </div>
        </form>
      </header>

      {projects === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {projects !== null && projects.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("home.empty")}</p>}

      {projects !== null && projects.length > 0 && (
        <h2 className="mt-8 text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
          {showCategories ? t("project.categories") : t("home.title")}
        </h2>
      )}

      {soleProject && nav && soleCategories && soleCategories.length > 0 && (
        // Same tiles as the project page's, deliberately -- this is the
        // same list, reached from one level up.
        <CategoryTiles
          nav={nav}
          categories={soleCategories}
          href={(c) => path(`/p/${soleProject.slug}/c/${c.slug}`)}
          pageHref={(slug) => path(`/p/${soleProject.slug}/pages/${slug}`)}
        />
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
                    {p.private && <PrivateBadge compact />}
                  </div>
                </CardHeader>
                {p.description && <CardContent className="text-sm text-[var(--muted)]">{p.description}</CardContent>}
              </Card>
            </Link>
          ))}
        </div>
      )}

      {recent.length > 0 && (
        <section className="mt-12">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("home.recent")}</h2>
            <Link to={path("/changes")} className="text-sm text-[var(--accent)] hover:underline">
              {t("home.allChanges")} →
            </Link>
          </div>
          <ul className="mt-3 divide-y divide-[var(--border)] rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            {recent.map((entry) => (
              <li key={`${entry.project_slug}/${entry.page_slug}/${entry.language}`}>
                <Link
                  to={path(`/p/${entry.project_slug}/pages/${entry.page_slug}`)}
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-4 py-3 hover:bg-[var(--surface-2)]"
                >
                  <span className="font-medium">{entry.title}</span>
                  <span className="text-xs text-[var(--muted)]">
                    {soleProject ? entry.category_name : `${entry.project_name} › ${entry.category_name}`}
                  </span>
                  <time dateTime={entry.date} className="ml-auto text-xs text-[var(--muted)]">
                    {formatIsoDate(entry.date, uiLang)}
                  </time>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
