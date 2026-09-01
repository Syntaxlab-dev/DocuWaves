import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Languages } from "lucide-react";
import { ApiError, api, type Category, type Page, type Project, type VersionInfo } from "@/lib/api";
import { MarkdownView } from "@/components/MarkdownView";
import { DocsShell } from "@/components/DocsShell";
import { NotFound } from "@/components/NotFound";
import { PageFooterNav } from "@/components/PageFooterNav";
import { TableOfContents } from "@/components/TableOfContents";
import { collectHeadings } from "@/lib/headings";
import { useProjectNav, type NavStatus } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { languageName, useContentLang } from "@/lib/lang";
import { useDocPath, useReportProjectVersion } from "@/lib/version";
import { useDocumentTitle } from "@/lib/site";

/** Below this, a contents list is just the page's own outline restated --
 *  one entry is never worth a column, and two is where it starts telling a
 *  reader something the text above the fold didn't already. */
const MIN_TOC_HEADINGS = 2;

/** "2026-08-31" as the reader's own locale spells a date.
 *
 *  Built from the parts rather than handed to `new Date(iso)`: that parses a
 *  bare date as UTC midnight, which renders as the previous day for every
 *  reader west of Greenwich -- a "last updated" line that is a day off is
 *  worse than none. An unparseable value is shown as it came, which is also
 *  what happens if the backend ever answers with something else. */
function formatIsoDate(iso: string, locale: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Date(year, month - 1, day).toLocaleDateString(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function PublicPage() {
  const { projectSlug, pageSlug, version } = useParams<{
    projectSlug: string;
    pageSlug: string;
    version: string;
  }>();
  const { hash } = useLocation();
  const { t, lang: uiLang } = useI18n();
  const { lang } = useContentLang();
  const docPath = useDocPath();
  const { nav, status: navStatus } = useProjectNav(projectSlug, lang, version);
  const [data, setData] = useState<{
    project: Project;
    category: Category;
    page: Page & { fallback: boolean };
    versions: VersionInfo | null;
    last_updated: string;
  } | null>(null);
  const [pageStatus, setPageStatus] = useState<NavStatus>("loading");

  useEffect(() => {
    if (!projectSlug || !pageSlug) return;
    let current = true;
    setData(null);
    setPageStatus("loading");
    api
      .publicGetPage(projectSlug, pageSlug, lang, version)
      .then((result) => {
        if (!current) return;
        setData(result);
        setPageStatus("ready");
      })
      .catch((error) => {
        if (!current) return;
        setPageStatus(error instanceof ApiError && error.status === 404 ? "notfound" : "failed");
      });
    return () => {
      current = false;
    };
    // lang included: switching language keeps the reader on this same page
    // (the slug is shared by its translations) and reloads its content.
    // version likewise -- the same slug in another version is another file.
  }, [projectSlug, pageSlug, lang, version]);

  // `versions.available` here is the versions this page is PUBLISHED in, so
  // the switcher can stay on the page where it exists and land on the
  // version's home where it doesn't -- never on a 404.
  useReportProjectVersion({
    projectSlug: projectSlug ?? "",
    version: version ?? "",
    tail: pageSlug ? `/pages/${pageSlug}` : "",
    info: data?.versions ?? null,
  });

  // Before the early returns below -- a hook can't sit behind a condition.
  // Undefined while loading, which just leaves the site name in the tab.
  useDocumentTitle(data?.page.title);

  const headings = useMemo(() => (data ? collectHeadings(data.page.markdown_content) : []), [data]);

  useEffect(() => {
    if (!data || !hash) return;
    // A deep link into a section arrives before the Markdown does: by the
    // time the heading exists the browser has long since given up trying to
    // scroll to the fragment on its own.
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView();
  }, [data, hash]);

  if (pageStatus === "notfound" || navStatus === "notfound") return <NotFound />;
  if (pageStatus === "failed" || navStatus === "failed")
    return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.error")}</p>;
  if (!data || !nav) return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.loading")}</p>;

  const showToc = headings.length >= MIN_TOC_HEADINGS;

  return (
    <DocsShell
      nav={nav}
      activeCategorySlug={data.category.slug}
      activePageSlug={data.page.slug}
      aside={showToc ? <TableOfContents headings={headings} variant="column" /> : undefined}
    >
      <div className="flex flex-wrap items-center gap-1 text-sm text-[var(--muted)]">
        <Link to={docPath(data.project.slug, "")} className="hover:text-[var(--accent)]">
          {data.project.name}
        </Link>
        <span>/</span>
        <Link to={docPath(data.project.slug, `/c/${data.category.slug}`)} className="hover:text-[var(--accent)]">
          {data.category.name}
        </Link>
      </div>
      <h1 className="mt-2 mb-4 text-2xl font-semibold">{data.page.title}</h1>
      {/* Between the title and the text, where it is read before the page
          is: what follows is not in the language that was asked for, and
          saying so plainly is the whole point -- the alternative would be
          either a 404 over a translation nobody has written yet, or text
          silently passed off as translated. */}
      {data.page.fallback && (
        <p
          lang={data.page.language || undefined}
          className="mb-5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]"
        >
          <Languages className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
          {t("page.notTranslatedPrefix")}
          {languageName(data.page.language, lang)}
          {t("page.notTranslatedSuffix")}
        </p>
      )}
      {showToc && <TableOfContents headings={headings} variant="inline" />}
      {/* versionDir is the page file's own directory name, not the URL
          segment: `../assets/x.png` in the source resolves against
          content/<project>/<version>/<category>/, and "" (an unversioned
          project) makes that exactly the path it always was. */}
      <MarkdownView
        content={data.page.markdown_content}
        title={data.page.title}
        projectSlug={data.project.slug}
        categorySlug={data.category.slug}
        versionDir={data.page.version}
      />
      {/* One quiet line under the text. The date comes from the content
          repo's own log, not from the page's `updated_at` column -- that one
          moves whenever the index is rebuilt, which would tell a reader the
          page changed on a day nothing about it did.
          A date and nothing else: who changed it, why, and the diff all
          exist, and all of it stays behind the admin login (the content repo
          is private, and its commit messages are its own business). */}
      {data.last_updated && (
        <p className="mt-8 text-xs text-[var(--muted)]">
          {t("page.lastUpdated")} <time dateTime={data.last_updated}>{formatIsoDate(data.last_updated, uiLang)}</time>
        </p>
      )}
      <PageFooterNav nav={nav} pageSlug={data.page.slug} />
    </DocsShell>
  );
}
