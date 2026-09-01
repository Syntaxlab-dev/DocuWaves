import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Languages } from "lucide-react";
import { ApiError, api, type Category, type Page, type Project } from "@/lib/api";
import { MarkdownView } from "@/components/MarkdownView";
import { DocsShell } from "@/components/DocsShell";
import { NotFound } from "@/components/NotFound";
import { PageFooterNav } from "@/components/PageFooterNav";
import { TableOfContents } from "@/components/TableOfContents";
import { collectHeadings } from "@/lib/headings";
import { useProjectNav, type NavStatus } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { languageName, useContentLang } from "@/lib/lang";
import { useDocumentTitle } from "@/lib/site";

/** Below this, a contents list is just the page's own outline restated --
 *  one entry is never worth a column, and two is where it starts telling a
 *  reader something the text above the fold didn't already. */
const MIN_TOC_HEADINGS = 2;

export function PublicPage() {
  const { projectSlug, pageSlug } = useParams<{ projectSlug: string; pageSlug: string }>();
  const { hash } = useLocation();
  const { t } = useI18n();
  const { lang, path } = useContentLang();
  const { nav, status: navStatus } = useProjectNav(projectSlug, lang);
  const [data, setData] = useState<{
    project: Project;
    category: Category;
    page: Page & { fallback: boolean };
  } | null>(null);
  const [pageStatus, setPageStatus] = useState<NavStatus>("loading");

  useEffect(() => {
    if (!projectSlug || !pageSlug) return;
    let current = true;
    setData(null);
    setPageStatus("loading");
    api
      .publicGetPage(projectSlug, pageSlug, lang)
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
  }, [projectSlug, pageSlug, lang]);

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
        <Link to={path(`/p/${data.project.slug}`)} className="hover:text-[var(--accent)]">
          {data.project.name}
        </Link>
        <span>/</span>
        <Link to={path(`/p/${data.project.slug}/c/${data.category.slug}`)} className="hover:text-[var(--accent)]">
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
      <MarkdownView
        content={data.page.markdown_content}
        projectSlug={data.project.slug}
        categorySlug={data.category.slug}
      />
      <PageFooterNav nav={nav} pageSlug={data.page.slug} />
    </DocsShell>
  );
}
