// The content repository's status line at the top of the admin area.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { GitBranch, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type ContentRepoStatus } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** What kind of content repository this instance has, and whether anything
 *  is wrong with it.
 *
 *  Three states, and only one of them is a problem. **Local** is the default
 *  and is reported as the plain fact it is -- content versioned here, no
 *  remote -- never as an error and never as a nudge to go and configure one:
 *  an instance with no remote is not a half-working instance. **Remote** is
 *  the same connected/unreachable line it always was. **Unrelated** is the
 *  one that needs the operator: a remote is configured that this instance
 *  cannot safely push to, so the message says so and says what to do.
 *
 *  "Sync now" is shown for the two remote states only. In local mode there
 *  is no remote to fetch from and nowhere else the files could have changed,
 *  so the button would be an action with nothing behind it; in the unrelated
 *  state it is exactly how an operator retries after fixing the remote. */
export function RepoStatusBar({
  status,
  syncing,
  canSync,
  onSync,
}: {
  canSync: boolean;
  status: ContentRepoStatus | null;
  syncing: boolean;
  onSync: () => void;
}) {
  const { t } = useI18n();
  if (!status) return null;
  const local = status.mode === "local";
  const commit = status.last_commit ? `${status.branch} · ${status.last_commit.sha} · ${status.last_commit.message}` : status.branch;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm">
      <GitBranch className="h-4 w-4 text-[var(--muted)]" />
      {local ? (
        <>
          <span>{t("admin.repoLocal")}</span>
          <span className="text-[var(--muted)]">{commit}</span>
        </>
      ) : status.mode === "unrelated" ? (
        <span className="text-red-500">
          {t("admin.repoUnrelated")}
          {status.error ? `: ${status.error}` : ""}
        </span>
      ) : status.connected ? (
        <>
          <span className="text-[var(--accent)]">{t("admin.repoConnected")}</span>
          <span className="text-[var(--muted)]">{commit}</span>
        </>
      ) : (
        <span className="text-red-500">
          {t("admin.repoDisconnected")}
          {status.error ? `: ${status.error}` : ""}
        </span>
      )}
      {/* Pulling from the remote is a POST, so a read-only account does not
          get the button -- but it keeps the bar, because which branch and
          which commit this instance is on is exactly what a reviewer wants
          to see. */}
      <RepoExposure status={status} />
      {!local && canSync && (
        <Button variant="outline" size="sm" className="ml-auto" onClick={onSync} disabled={syncing}>
          <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
          {t("admin.repoSyncNow")}
        </Button>
      )}
    </div>
  );
}

/**
 * Where the content lives, and -- for a remote -- whether anybody can read
 * it (backend services/repo_exposure.py). The loud case is a PUBLIC remote
 * while there are private projects: their files are readable there no
 * matter what the website hides. That is the one mistake with private
 * projects that nothing on the site itself would ever show.
 */
export function RepoExposure({ status }: { status: ContentRepoStatus }) {
  const { t } = useI18n();
  const exposure = status.exposure;
  if (!exposure) return null;
  if (!exposure.remote) {
    return <span className="text-xs text-[var(--muted)]">· {t("admin.repoOnlyHere")}</span>;
  }
  const where = t("admin.repoAlsoAt").replace("{remote}", exposure.remote);
  if (exposure.visibility === "public") {
    const danger = exposure.private_projects > 0;
    return (
      <span
        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
          danger ? "bg-red-500/15 text-red-600 dark:text-red-400" : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
        }`}
        role={danger ? "alert" : undefined}
      >
        {where} — {t("admin.repoExposurePublic")}
        {danger && <> · {t("admin.repoExposureDanger").replace("{count}", String(exposure.private_projects))}</>}
      </span>
    );
  }
  return (
    <span className="text-xs text-[var(--muted)]">
      · {where} ({t(exposure.visibility === "private" ? "admin.repoExposurePrivate" : "admin.repoExposureUnknown")})
    </span>
  );
}
