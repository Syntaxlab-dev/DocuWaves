import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ProjectNav } from "@/lib/api";
import { readingOrder } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";

/**
 * Where a reader goes when they've finished a page: the neighbours in
 * reading order, which crosses category boundaries (see readingOrder()) --
 * the end of "Getting started" leads into the first page of "Guides", not
 * into a dead end.
 *
 * Titles rather than bare arrows: "Next" tells nobody whether the next page
 * is worth reading, and on a phone the two links are all that's on screen.
 */
export function PageFooterNav({ nav, pageSlug }: { nav: ProjectNav; pageSlug: string }) {
  const { t } = useI18n();

  const order = readingOrder(nav);
  const index = order.findIndex((entry) => entry.page.slug === pageSlug);
  if (index === -1) return null;

  const previous = index > 0 ? order[index - 1] : null;
  const next = index < order.length - 1 ? order[index + 1] : null;
  if (!previous && !next) return null;

  return (
    <nav className="mt-12 grid gap-3 border-t border-[var(--border)] pt-6 sm:grid-cols-2" aria-label={t("page.pageNav")}>
      {previous && (
        <Link
          to={`/p/${nav.project.slug}/pages/${previous.page.slug}`}
          className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 hover:bg-[var(--surface-2)]"
        >
          <ChevronLeft className="h-4 w-4 shrink-0 text-[var(--muted)]" />
          <span className="min-w-0">
            <span className="block text-xs text-[var(--muted)]">{t("page.previous")}</span>
            <span className="block truncate text-sm font-medium">{previous.page.title}</span>
          </span>
        </Link>
      )}
      {next && (
        // col-start-2 so a first page's lone "next" still sits on the right,
        // where the reader's eye already is, instead of sliding left into
        // the gap the missing "previous" left behind.
        <Link
          to={`/p/${nav.project.slug}/pages/${next.page.slug}`}
          className="flex items-center justify-end gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-right hover:bg-[var(--surface-2)] sm:col-start-2"
        >
          <span className="min-w-0">
            <span className="block text-xs text-[var(--muted)]">{t("page.next")}</span>
            <span className="block truncate text-sm font-medium">{next.page.title}</span>
          </span>
          <ChevronRight className="h-4 w-4 shrink-0 text-[var(--muted)]" />
        </Link>
      )}
    </nav>
  );
}
