// Documentation versions: the version switcher, the frozen notice and freezing a release.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useState } from "react";
import { toast } from "sonner";
import { History, Puzzle, Lock, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError, type AdminVersions, type Project } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { normalizeVersionId } from "@/lib/version";

/**
 * Documentation versions for the selected project.
 *
 * The bar is always there (an unversioned project needs a way to reach
 * "Freeze a version" too), but it only grows a version picker once the
 * project HAS frozen versions -- a picker with one option would be a
 * control that does nothing on every project that never versions anything.
 */
export function VersionsBar({
  versions,
  viewing,
  onView,
  open,
  onToggle,
  onToggleSnippets,
}: {
  versions: AdminVersions | null;
  viewing: string;
  onView: (version: string) => void;
  open: boolean;
  onToggle: () => void;
  onToggleSnippets: () => void;
}) {
  const { t } = useI18n();
  const hasFrozen = Boolean(versions && versions.versions.length > 0);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {hasFrozen && versions && (
        <>
          <span className="text-sm text-[var(--muted)]">{t("admin.versionViewing")}</span>
          <select
            aria-label={t("admin.versionViewing")}
            value={viewing}
            onChange={(e) => onView(e.target.value)}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
          >
            <option value={versions.writable}>{t("admin.versionCurrent")}</option>
            {versions.versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </>
      )}
      <Button variant="ghost" size="sm" className={hasFrozen ? "" : "ml-auto"} onClick={onToggle}>
        <History className="h-3.5 w-3.5" />
        {t("admin.versions")}
      </Button>
      <Button variant="ghost" size="sm" onClick={onToggleSnippets}>
        <Puzzle className="h-3.5 w-3.5" />
        {t("snippets.title")}
      </Button>
      {open && <span className="sr-only">{t("admin.versionsIntro")}</span>}
    </div>
  );
}

/** Shown above every panel while a frozen version is selected, so the
 *  missing buttons below are explained rather than merely absent. */
export function FrozenNotice({ projectSlug, version }: { projectSlug: string; version: string }) {
  const { t } = useI18n();
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>
        {t("admin.versionReadOnly").replace("{project}", projectSlug).replace("{version}", version)}
      </span>
    </div>
  );
}

/**
 * The version list plus the freeze form.
 *
 * Freezing spells out what it is about to do BEFORE it does it, and the
 * first freeze of a project spells out more, because that is the one that
 * moves the project's existing directories down a level. `would_move`
 * comes from the server (it lists what is actually on disk right now), so
 * the confirmation names the real folders rather than a generic promise.
 */
export function VersionsCard({
  project,
  versions,
  onChanged,
}: {
  project: Project;
  versions: AdminVersions;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  // What the id will actually be on disk. Shown in the confirmation rather
  // than the raw text, so nobody agrees to "copy to V 3.0/" and gets
  // "v-3.0/" -- the backend normalizes identically and is the authority.
  const normalizedId = normalizeVersionId(id);

  async function onFreeze() {
    setBusy(true);
    try {
      await api.adminFreezeVersion(project.slug, id.trim(), label.trim());
      toast.success(t("admin.versionFrozen"));
      setId("");
      setLabel("");
      setConfirming(false);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(versionId: string, versionLabel: string) {
    const message = t("admin.versionDeleteConfirm")
      .replace("{label}", versionLabel)
      .replace("{project}", project.slug)
      .replace("{id}", versionId);
    if (!confirm(message)) return;
    try {
      await api.adminDeleteVersion(project.slug, versionId);
      toast.success(t("admin.versionDeleted"));
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("admin.versions")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-[var(--muted)]">{t("admin.versionsIntro")}</p>

        {versions.versions.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">{t("admin.versionNone")}</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {versions.versions.map((v) => (
              <div key={v.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                <Lock className="h-3.5 w-3.5 text-[var(--muted)]" aria-hidden="true" />
                <span className="font-medium">{v.label}</span>
                <span className="font-mono text-xs text-[var(--muted)]">{v.id}</span>
                {v.released && (
                  <span className="text-xs text-[var(--muted)]">
                    {t("admin.versionReleased")} {v.released}
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="ml-auto h-6 w-6"
                  aria-label={t("admin.delete")}
                  onClick={() => onDelete(v.id, v.label)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <span className="text-sm font-medium">{t("admin.versionFreeze")}</span>
          <div className="flex flex-wrap gap-2">
            <Input
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                setConfirming(false);
              }}
              placeholder={t("admin.versionId")}
              className="max-w-[16rem] font-mono"
            />
            <Input
              value={label}
              onChange={(e) => {
                setLabel(e.target.value);
                setConfirming(false);
              }}
              placeholder={t("admin.versionLabel")}
              className="max-w-[12rem]"
            />
            <Button
              variant="outline"
              disabled={!normalizedId || !label.trim() || busy}
              onClick={() => setConfirming(true)}
            >
              {t("admin.versionFreeze")}
            </Button>
          </div>

          {confirming && (
            <div className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm">
              <p className="font-medium">{t("admin.versionFreezeConfirmTitle")}</p>
              <ul className="mt-2 list-disc pl-5 text-[var(--muted)]">
                {!versions.versioned && versions.would_move.length > 0 && (
                  <li>
                    {t("admin.versionFreezeStepMove")}{" "}
                    <span className="font-mono text-[var(--ink)]">{versions.would_move.join("  ")}</span>
                  </li>
                )}
                <li>{t("admin.versionFreezeStepCopy").replace("{id}", normalizedId)}</li>
                {!versions.versioned && <li>{t("admin.versionFreezeStepAssets")}</li>}
                <li>{t("admin.versionFreezeStepCommit")}</li>
              </ul>
              <div className="mt-3 flex gap-2">
                <Button size="sm" disabled={busy} onClick={onFreeze}>
                  {t("admin.versionFreezeGo")}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
                  {t("admin.cancel")}
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
