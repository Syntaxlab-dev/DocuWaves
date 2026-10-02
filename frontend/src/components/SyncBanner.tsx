/** A docs-as-code project (backend services/docs_sync.py): where its pages
 *  come from, that they are changed there and not here, and what the last
 *  syncs did. Shown above the project's categories and pages, which are
 *  read-only while it is. */
import { useEffect, useState } from "react";
import { GitBranch } from "lucide-react";
import { api, type ProjectSource, type SyncRun } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function when(iso: string, lang: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(lang === "de" ? "de-DE" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export function SyncBanner({ projectSlug, source }: { projectSlug: string; source: ProjectSource }) {
  const { t, lang } = useI18n();
  const [runs, setRuns] = useState<SyncRun[] | null>(null);

  useEffect(() => {
    api
      .adminProjectSync(projectSlug)
      .then((r) => setRuns(r.runs))
      .catch(() => setRuns([]));
  }, [projectSlug]);

  const last = runs?.[0];
  const where = [source.path || "/", source.branch].filter(Boolean).join(" · ");

  return (
    <div className="mb-4 rounded-lg border border-sky-400/60 bg-sky-500/10 px-3 py-2 text-sm text-sky-900 dark:text-sky-200">
      <div className="flex items-start gap-2">
        <GitBranch className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p>
            {t("sync.bannerFrom")}{" "}
            {source.repo ? (
              <a href={source.repo} target="_blank" rel="noreferrer noopener" className="font-medium underline">
                {source.repo.replace(/^https?:\/\//, "")}
              </a>
            ) : (
              <span className="font-medium">{t("sync.bannerRepoUnknown")}</span>
            )}{" "}
            <span className="opacity-80">({where})</span>
          </p>
          <p className="text-xs opacity-80">{t("sync.bannerReadOnly")}</p>
          {!source.repo && <p className="text-xs opacity-80">{t("sync.bannerAddRepo")}</p>}
          {runs !== null && (
            <p className="mt-1 text-xs">
              {last
                ? t("sync.lastRun")
                    .replace("{when}", when(last.synced_at, lang))
                    .replace("{ref}", last.ref || "—")
                    .replace("{added}", String(last.added))
                    .replace("{changed}", String(last.changed))
                    .replace("{removed}", String(last.removed))
                : t("sync.noRunsYet")}
            </p>
          )}
          {runs && runs.length > 1 && (
            <details className="mt-1 text-xs">
              <summary className="cursor-pointer">{t("sync.history")}</summary>
              <ul className="mt-1 flex flex-col gap-0.5">
                {runs.map((run, i) => (
                  <li key={i} className="tabular-nums">
                    {when(run.synced_at, lang)} · <code>{run.ref || "—"}</code> · +{run.added} ~{run.changed} −
                    {run.removed}
                    {!run.committed && ` · ${t("sync.unchanged")}`}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
