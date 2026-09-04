import { useEffect, useState } from "react";
import { AlertTriangle, Check, Download, Minus, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type Diagnostics, type ExportSummary } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Bytes as a person reads them. Binary units, because that is what a disk
 *  and a container report; one decimal place, because the difference between
 *  4 MB and 4.3 MB is the only precision anyone acts on here. */
function humanBytes(bytes: number, locale: string): string {
  if (!bytes) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toLocaleString(locale, { maximumFractionDigits: exponent === 0 ? 0 : 1 })} ${units[exponent]}`;
}

/** The check ids the backend can send, mapped to their labels.
 *
 *  Spelled out rather than built as `diag.check.${id}`: the translation keys
 *  are a closed union, so a template string is not one of them -- and the
 *  compiler refusing that is the useful half of the arrangement. A check id
 *  this frontend has not been taught yet renders as the id itself, which is
 *  a readable line in an older UI talking to a newer backend rather than a
 *  blank row or a crash. */
const CHECK_LABELS = {
  content_repo_writable: "diag.check.content_repo_writable",
  content_repo_open: "diag.check.content_repo_open",
  remote_reachable: "diag.check.remote_reachable",
} as const;

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-[var(--muted)]">{label}</span>
      <span className="text-right font-mono text-xs">{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border)] px-3 py-2">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{title}</div>
      <div className="divide-y divide-[var(--border)]">{children}</div>
    </div>
  );
}

/**
 * The page an operator opens when something looks wrong, and the button that
 * gets their documentation out of the instance in one file.
 *
 * The two belong together: the questions on this page ("is the repo
 * writable, is the remote reachable, how much disk is left") are the
 * questions somebody asks either just before or just after wishing they had
 * a backup.
 *
 * Everything here is read-only except that one download. There is
 * deliberately no "repair" button: every failure this page can show is one
 * an operator fixes in their deployment, and a button that claimed to fix a
 * full disk or an unreachable remote from inside the container would be
 * lying about what it can reach.
 */
export function AdminDiagnosticsCard({ onClose }: { onClose: () => void }) {
  const { t, lang: uiLang } = useI18n();
  const [report, setReport] = useState<Diagnostics | null>(null);
  const [exportInfo, setExportInfo] = useState<ExportSummary | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    const [diagnostics, summary] = await Promise.all([
      api.adminDiagnostics().catch(() => null),
      api.adminExportSummary().catch(() => null),
    ]);
    setReport(diagnostics);
    setExportInfo(summary);
    setLoading(false);
  }

  useEffect(() => {
    void load();
  }, []);

  const conflicts = report?.operations.conflicts ?? [];

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t("diag.title")}</CardTitle>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            {t("diag.refresh")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t("common.back")}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {!report ? (
          <p className="text-sm text-[var(--muted)]">{loading ? t("common.loading") : t("common.error")}</p>
        ) : (
          <div className="flex flex-col gap-3">
            {/* The checks first: they are the only lines on this page that
                can say something is wrong, and burying them under counts
                would make the page something to read rather than to look
                at. */}
            <Section title={t("diag.checks")}>
              {report.checks.map((check) => (
                <div key={check.id} className="flex items-start gap-2 py-1.5 text-sm">
                  {check.skipped ? (
                    <Minus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                  ) : check.ok ? (
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--accent)]" aria-hidden="true" />
                  ) : (
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />
                  )}
                  <span className="flex-1">
                    {check.id in CHECK_LABELS ? t(CHECK_LABELS[check.id as keyof typeof CHECK_LABELS]) : check.id}
                    {check.skipped && <span className="ml-1.5 text-[var(--muted)]">{t("diag.notApplicable")}</span>}
                    {!check.ok && check.detail && (
                      <span className="mt-0.5 block font-mono text-xs text-[var(--muted)]">{check.detail}</span>
                    )}
                  </span>
                </div>
              ))}
            </Section>

            {/* A page that exists in the repo and is invisible on the site is
                the failure people spend longest chasing, so it gets its own
                block with the two filenames in it rather than a count. */}
            {conflicts.length > 0 && (
              <div className="rounded-lg border border-amber-500/60 bg-amber-500/10 px-3 py-2">
                <div className="text-sm font-medium">{t("diag.conflictsTitle")}</div>
                <p className="mt-0.5 text-xs text-[var(--muted)]">{t("diag.conflictsHint")}</p>
                <ul className="mt-1.5 flex flex-col gap-0.5 font-mono text-xs">
                  {conflicts.map((conflict, index) => (
                    <li key={`${conflict.project}-${conflict.slug}-${index}`}>
                      {conflict.project}/{conflict.category}/{conflict.slug}
                      {conflict.language ? `.${conflict.language}` : ""}.md
                      <span className="text-[var(--muted)]"> → {t("diag.conflictKept").replace("{category}", conflict.kept_in)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <Section title={t("diag.instance")}>
                <Row label={t("diag.database")} value={report.instance.database} />
                <Row label={t("diag.python")} value={report.instance.python} />
                <Row label={t("diag.contentPath")} value={report.instance.content_repo_path} />
                <Row
                  label={t("diag.languages")}
                  value={report.instance.languages.length ? report.instance.languages.join(", ") : t("diag.single")}
                />
                <Row label={t("diag.syncInterval")} value={`${report.instance.sync_interval_seconds}s`} />
                <Row
                  label={t("diag.publicUrl")}
                  value={report.instance.public_base_url || t("diag.autoDetected")}
                />
              </Section>

              <Section title={t("diag.content")}>
                <Row label={t("diag.projects")} value={String(report.content.projects)} />
                <Row label={t("diag.categories")} value={String(report.content.categories)} />
                <Row
                  label={t("diag.pages")}
                  value={t("diag.pagesValue")
                    .replace("{published}", String(report.content.published))
                    .replace("{drafts}", String(report.content.drafts))}
                />
                {Object.entries(report.content.versions).map(([slug, versions]) => (
                  <Row
                    key={slug}
                    label={t("diag.versionsOf").replace("{project}", slug)}
                    value={versions.length ? versions.join(", ") : t("diag.unversioned")}
                  />
                ))}
              </Section>

              <Section title={t("diag.storage")}>
                <Row
                  label={t("diag.contentSize")}
                  value={`${humanBytes(report.storage.content_bytes, uiLang)} · ${report.storage.content_files}`}
                />
                <Row label={t("diag.databaseSize")} value={
                  report.instance.database === "postgres"
                    ? t("diag.external")
                    : humanBytes(report.storage.database_bytes, uiLang)
                } />
                <Row
                  label={t("diag.diskFree")}
                  value={`${humanBytes(report.storage.disk_free_bytes, uiLang)} / ${humanBytes(report.storage.disk_total_bytes, uiLang)}`}
                />
              </Section>

              <Section title={t("diag.operations")}>
                <Row label={t("diag.apiTokens")} value={String(report.operations.api_tokens)} />
                <Row label={t("diag.previewLinks")} value={String(report.operations.preview_links)} />
                <Row label={t("diag.votes")} value={String(report.operations.feedback_votes)} />
                <Row
                  label={t("diag.lastSync")}
                  value={
                    report.operations.last_sync
                      ? new Date(report.operations.last_sync).toLocaleString(uiLang, {
                          dateStyle: "short",
                          timeStyle: "short",
                        })
                      : t("diag.never")
                  }
                />
              </Section>
            </div>

            {/* The one action on this page. Placed under the numbers because
                the numbers are what tell an operator how big it will be. */}
            <div className="rounded-lg border border-[var(--border)] px-3 py-2">
              <div className="text-sm font-medium">{t("diag.exportTitle")}</div>
              <p className="mt-0.5 text-xs text-[var(--muted)]">{t("diag.exportHint")}</p>
              <p className="mt-0.5 text-xs text-[var(--muted)]">{t("diag.exportExcludes")}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {/* A plain link, not a fetch: the archive is as big as the
                    documentation is, and pulling it into a Blob to hand it
                    straight back to the browser doubles it through memory. */}
                <a
                  href={api.adminExportUrl()}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 text-sm hover:border-[var(--accent)] hover:text-[var(--accent)]"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  {t("diag.exportDownload")}
                </a>
                {/* The size of what goes IN, not a promise about the
                    download: a zip of compressible Markdown comes out
                    smaller, and one carrying a git bundle can come out
                    larger. Saying which of the two this number is costs one
                    word and stops it being wrong. */}
                {exportInfo && (
                  <span className="text-xs text-[var(--muted)]">
                    {t("diag.exportSize")
                      .replace("{size}", humanBytes(exportInfo.bytes, uiLang))
                      .replace("{files}", String(exportInfo.files))}
                    {exportInfo.history ? ` · ${t("diag.exportHistory")}` : ` · ${t("diag.exportNoHistory")}`}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
