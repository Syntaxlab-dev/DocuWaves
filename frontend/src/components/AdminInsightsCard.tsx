import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type FeedbackSummary } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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
export function AdminInsightsCard({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [feedback, setFeedback] = useState<FeedbackSummary[] | null>(null);
  const [broken, setBroken] = useState<Broken[] | null>(null);

  async function load() {
    const [f, b] = await Promise.all([
      api.adminFeedback().catch(() => ({ pages: [] as FeedbackSummary[] })),
      api.adminLinkCheck().catch(() => ({ broken: [] as Broken[] })),
    ]);
    setFeedback(f.pages);
    setBroken(b.broken);
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
                  <Button variant="ghost" size="sm" onClick={() => clearVotes(row.project_slug, row.page_slug)}>
                    {t("insights.clear")}
                  </Button>
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
