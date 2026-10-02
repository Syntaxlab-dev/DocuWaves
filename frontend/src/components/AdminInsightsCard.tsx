import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FilePlus2, X } from "lucide-react";
import { api, type FeedbackSummary, type SearchGap } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { usePermissions } from "@/lib/auth";

type Broken = {
  project_slug: string;
  page_slug: string;
  page_title: string;
  version: string;
  target: string;
  reason: string;
};

/**
 * What the documentation itself says about its own state: which pages
 * readers said did not help, and which links no longer go anywhere.
 *
 * Both are read-only reports plus one destructive action each (forgetting a
 * page's votes), so they share a card rather than each taking a place in the
 * header. They are also both things an author looks at occasionally and not
 * while writing.
 */
export function AdminInsightsCard({
  onClose,
  onCreatePage,
}: {
  onClose: () => void;
  /** Starts a new page with this title, in this project when the search
   *  was scoped to one ("" = the one currently selected). */
  onCreatePage: (title: string, projectSlug: string) => void;
}) {
  const { t } = useI18n();
  // Forgetting a page's votes is a DELETE, so a read-only account does not
  // get the button. Both reports themselves are reading and stay -- they
  // are, in fact, most of what a reviewer account is for.
  const { canWrite } = usePermissions();
  const [feedback, setFeedback] = useState<FeedbackSummary[] | null>(null);
  const [broken, setBroken] = useState<Broken[] | null>(null);
  const [gaps, setGaps] = useState<{ enabled: boolean; gaps: SearchGap[] } | null>(null);

  async function load() {
    const [f, b, g] = await Promise.all([
      api.adminFeedback().catch(() => ({ pages: [] as FeedbackSummary[] })),
      api.adminLinkCheck().catch(() => ({ broken: [] as Broken[] })),
      api.adminSearchGaps().catch(() => ({ enabled: true, gaps: [] as SearchGap[] })),
    ]);
    setFeedback(f.pages);
    setBroken(b.broken);
    setGaps(g);
  }

  async function forgetGap(id: number | null) {
    if (id === null && !confirm(t("gaps.clearConfirm"))) return;
    try {
      await (id === null ? api.adminClearSearchGaps() : api.adminForgetSearchGap(id));
      await load();
    } catch {
      toast.error(t("common.error"));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function clearVotes(projectSlug: string, pageSlug: string) {
    try {
      const { cleared } = await api.adminClearFeedback(projectSlug, pageSlug);
      toast.success(t("insights.cleared").replace("{n}", String(cleared)));
      await load();
    } catch {
      toast.error(t("common.error"));
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t("insights.title")}</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("common.back")}
        </Button>
      </CardHeader>
      <CardContent className="grid gap-8 lg:grid-cols-2">
        {/* First and full width: of the three, the only one that says what
            is MISSING rather than what is wrong with what exists. */}
        <section className="lg:col-span-2">
          <div className="mb-1 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("gaps.title")}</h3>
            {canWrite && gaps && gaps.gaps.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => void forgetGap(null)}>
                {t("gaps.clearAll")}
              </Button>
            )}
          </div>
          <p className="mb-3 text-xs text-[var(--muted)]">{t("gaps.hint")}</p>
          {gaps === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {gaps && !gaps.enabled && <p className="text-sm text-[var(--muted)]">{t("gaps.off")}</p>}
          {gaps?.enabled && gaps.gaps.length === 0 && (
            <p className="text-sm text-[var(--muted)]">{t("gaps.none")}</p>
          )}
          {gaps?.enabled && gaps.gaps.length > 0 && (
            <ul className="grid gap-2 md:grid-cols-2">
              {gaps.gaps.map((gap) => (
                <li
                  key={gap.id}
                  className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">„{gap.query}“</span>
                    <span className="block truncate text-xs text-[var(--muted)]">
                      {t("gaps.count").replace("{n}", String(gap.hits))}
                      {gap.project_slug && ` · ${gap.project_slug}`}
                      {gap.language && ` · ${gap.language.toUpperCase()}`}
                      {` · ${gap.last_seen}`}
                    </span>
                  </span>
                  {canWrite && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        title={t("gaps.createPage")}
                        aria-label={t("gaps.createPage")}
                        onClick={() => onCreatePage(gap.query, gap.project_slug)}
                      >
                        <FilePlus2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        title={t("gaps.forget")}
                        aria-label={t("gaps.forget")}
                        onClick={() => void forgetGap(gap.id)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="mb-1 text-sm font-semibold">{t("insights.feedbackTitle")}</h3>
          <p className="mb-3 text-xs text-[var(--muted)]">{t("insights.feedbackHint")}</p>
          {feedback === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {feedback?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("insights.noFeedback")}</p>}
          {feedback && feedback.length > 0 && (
            <ul className="flex flex-col gap-2">
              {feedback.map((row) => (
                <li
                  key={`${row.project_slug}/${row.version}/${row.page_slug}/${row.language}`}
                  className="flex items-center gap-3 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {row.project_slug} / {row.page_slug}
                    {row.version && <span className="text-[var(--muted)]"> · {row.version}</span>}
                  </span>
                  <span className="shrink-0 tabular-nums text-[var(--muted)]">
                    {row.helpful} / {row.total}
                  </span>
                  {canWrite && (
                    <Button variant="ghost" size="sm" onClick={() => clearVotes(row.project_slug, row.page_slug)}>
                      {t("insights.clear")}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="mb-1 text-sm font-semibold">{t("insights.linksTitle")}</h3>
          {/* Said plainly rather than left to be discovered: someone who
              expects external URLs to be checked would read an empty list as
              "everything is fine". */}
          <p className="mb-3 text-xs text-[var(--muted)]">{t("insights.linksHint")}</p>
          {broken === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {broken?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("insights.noBroken")}</p>}
          {broken && broken.length > 0 && (
            <ul className="flex flex-col gap-2">
              {broken.map((row, index) => (
                <li
                  key={`${row.project_slug}/${row.page_slug}/${row.target}/${index}`}
                  className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <div className="truncate font-medium">{row.page_title}</div>
                  <div className="truncate text-xs text-[var(--muted)]">
                    <code>{row.target}</code> — {row.reason}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
