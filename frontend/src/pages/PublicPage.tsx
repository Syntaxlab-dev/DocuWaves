import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError, api, type Category, type Page, type Project } from "@/lib/api";
import { MarkdownView } from "@/components/MarkdownView";
import { DocsShell } from "@/components/DocsShell";
import { NotFound } from "@/components/NotFound";
import { PageFooterNav } from "@/components/PageFooterNav";
import { TableOfContents } from "@/components/TableOfContents";
import { collectHeadings } from "@/lib/headings";
import { useProjectNav, type NavStatus } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { useDocumentTitle } from "@/lib/site";

/** Below this, a contents list is just the page's own outline restated --
 *  one entry is never worth a column, and two is where it starts telling a
 *  reader something the text above the fold didn't already. */
const MIN_TOC_HEADINGS = 2;

export function PublicPage() {
  const { projectSlug, pageSlug } = useParams<{ projectSlug: string; pageSlug: string }>();
  const { hash } = useLocation();
  const { t } = useI18n();
  const { nav, status: navStatus } = useProjectNav(projectSlug);
  const [data, setData] = useState<{ project: Project; category: Category; page: Page } | null>(null);
  const [pageStatus, setPageStatus] = useState<NavStatus>("loading");

  useEffect(() => {
    if (!projectSlug || !pageSlug) return;
    let current = true;
    setData(null);
    setPageStatus("loading");
    api
      .publicGetPage(projectSlug, pageSlug)
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
  }, [projectSlug, pageSlug]);

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
        <Link to={`/p/${data.project.slug}`} className="hover:text-[var(--accent)]">
          {data.project.name}
        </Link>
        <span>/</span>
        <Link to={`/p/${data.project.slug}/c/${data.category.slug}`} className="hover:text-[var(--accent)]">
          {data.category.name}
        </Link>
      </div>
      <h1 className="mt-2 mb-4 text-2xl font-semibold">{data.page.title}</h1>
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
