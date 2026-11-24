import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type ActivityEntry } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const PAGE = 50;
// An import touches hundreds of pages; a few name the commit well enough.
const SHOWN_PAGES = 8;

/**
 * Who changed what, lately: the content repo's history, newest first, with
 * the pages each commit touched (backend services/activity.py). Includes
 * drafts, proposals and changes made directly in Git -- everything the
 * public changelog leaves out on purpose.
 */
export function ActivityCard({ onClose }: { onClose: () => void }) {
  const { t, lang } = useI18n();
  const [entries, setEntries] = useState<ActivityEntry[] | null>(null);
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => {
    api
      .adminActivity(limit)
      .then((r) => setEntries(r.entries))
      .catch(() => setEntries([]));
  }, [limit]);

  const when = (iso: string) =>
    new Date(iso).toLocaleString(lang === "de" ? "de-DE" : "en-GB", { dateStyle: "medium", timeStyle: "short" });

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t("activity.title")}</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("common.back")}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-[var(--muted)]">{t("activity.intro")}</p>
        {entries === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
        {entries?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("activity.none")}</p>}
        {entries && entries.length > 0 && (
          <ol className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {entries.map((entry) => (
              <li key={entry.sha} className="flex flex-col gap-1 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-medium">{entry.author}</span>
                  <span className="min-w-0 flex-1 truncate">{entry.message}</span>
                  <time className="shrink-0 text-xs text-[var(--muted)]" dateTime={entry.date}>
                    {when(entry.date)}
                  </time>
                </div>
                {(entry.pages.length > 0 || entry.other_files > 0) && (
                  <div className="flex flex-wrap gap-1.5 text-xs">
                    {entry.pages.slice(0, SHOWN_PAGES).map((page) => (
                      <span
                        key={`${page.project_slug}/${page.version}/${page.slug}/${page.language}/${page.pending}`}
                        className="rounded border border-[var(--border)] px-1.5 py-0.5 text-[var(--muted)]"
                      >
                        {page.status === "D" ? "− " : page.status === "A" ? "+ " : ""}
                        {page.project_name} /{" "}
                        {page.title ? (
                          <a
                            href={`/p/${page.project_slug}/${page.version ? `${page.version}/` : ""}pages/${page.slug}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-[var(--ink)] hover:underline"
                          >
                            {page.title}
                          </a>
                        ) : (
                          <span className="line-through">{page.slug}</span>
                        )}
                        {page.language && ` · ${page.language}`}
                        {page.version && ` · ${page.version}`}
                        {page.pending && ` · ${t("activity.proposal")}`}
                      </span>
                    ))}
                    {entry.pages.length > SHOWN_PAGES && (
                      <span className="px-1.5 py-0.5 text-[var(--muted)]">
                        {t("activity.morePages").replace("{n}", String(entry.pages.length - SHOWN_PAGES))}
                      </span>
                    )}
                    {entry.other_files > 0 && (
                      <span className="px-1.5 py-0.5 text-[var(--muted)]">
                        {t("activity.otherFiles").replace("{n}", String(entry.other_files))}
                      </span>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
        {entries && entries.length >= limit && limit < 200 && (
          <Button variant="outline" size="sm" className="mt-3" onClick={() => setLimit((l) => Math.min(200, l + PAGE))}>
            {t("activity.more")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
