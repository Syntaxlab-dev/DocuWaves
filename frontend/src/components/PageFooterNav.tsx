import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { api, type ProjectNav } from "@/lib/api";
import { readingOrder } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { excerpt } from "@/lib/textStats";
import { useDocPath } from "@/lib/version";

/**
 * Where a reader goes when they've finished a page: the neighbours in
 * reading order, which crosses category boundaries (see readingOrder()) --
 * the end of "Getting started" leads into the first page of "Guides", not
 * into a dead end.
 *
 * Cards rather than bare arrows: the title, the category it is in, and the
 * first line of its text, so "Next" says whether the next page is worth
 * reading. The teasers load after the page itself and are simply left out
 * when they can't be had (offline, a page that went away).
 */
export function PageFooterNav({
  nav,
  pageSlug,
  lang,
  version,
}: {
  nav: ProjectNav;
  pageSlug: string;
  lang?: string;
  version?: string;
}) {
  const { t } = useI18n();
  const docPath = useDocPath();

  const order = readingOrder(nav);
  const index = order.findIndex((entry) => entry.page.slug === pageSlug);
  const previous = index > 0 ? order[index - 1] : null;
  const next = index !== -1 && index < order.length - 1 ? order[index + 1] : null;

  const [teasers, setTeasers] = useState<Record<string, string>>({});
  const previousSlug = previous?.page.slug;
  const nextSlug = next?.page.slug;
  useEffect(() => {
    let current = true;
    setTeasers({});
    for (const slug of [previousSlug, nextSlug]) {
      if (!slug) continue;
      api
        .publicGetPage(nav.project.slug, slug, lang, version)
        .then((result) => {
          if (current) setTeasers((all) => ({ ...all, [slug]: excerpt(result.page.markdown_content) }));
        })
        .catch(() => {});
    }
    return () => {
      current = false;
    };
  }, [nav.project.slug, previousSlug, nextSlug, lang, version]);

  if (!previous && !next) return null;

  const card = (entry: NonNullable<typeof previous>, direction: "previous" | "next") => {
    const isNext = direction === "next";
    const teaser = teasers[entry.page.slug];
    return (
      <Link
        to={docPath(nav.project.slug, `/pages/${entry.page.slug}`)}
        // "[" and "]" follow these (see Shortcuts.tsx).
        data-page-nav={direction}
        className={`group flex flex-col gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 transition-colors hover:border-[var(--accent)] ${
          isNext ? "text-right sm:col-start-2" : ""
        }`}
      >
        <span className={`flex items-center gap-1.5 text-xs text-[var(--muted)] ${isNext ? "justify-end" : ""}`}>
          {!isNext && <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" aria-hidden="true" />}
          {t(isNext ? "page.next" : "page.previous")}
          <span aria-hidden="true">·</span>
          <span className="truncate">{entry.category.name}</span>
          {isNext && <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />}
        </span>
        <span className="truncate font-medium group-hover:text-[var(--accent)]">{entry.page.title}</span>
        {teaser && <span className="line-clamp-2 text-sm text-[var(--muted)]">{teaser}</span>}
      </Link>
    );
  };

  return (
    // col-start-2 on "next" so a first page's lone "next" still sits on the
    // right, where the reader's eye already is.
    <nav className="mt-12 grid gap-3 border-t border-[var(--border)] pt-6 sm:grid-cols-2" aria-label={t("page.pageNav")}>
      {previous && card(previous, "previous")}
      {next && card(next, "next")}
    </nav>
  );
}
