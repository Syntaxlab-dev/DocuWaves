import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type AdminLogEntry } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const PAGE = 100;

/**
 * What administrators did to the instance: accounts, API tokens, branding
 * and exports (backend services/admin_log.py). Changes to the
 * documentation itself are commits and live in Activity instead.
 */
export function AdminLogCard({ onClose }: { onClose: () => void }) {
  const { t, lang } = useI18n();
  const [entries, setEntries] = useState<AdminLogEntry[] | null>(null);
  const [more, setMore] = useState(false);

  async function load(before?: number) {
    try {
      const r = await api.adminLog(PAGE, before);
      setEntries((current) => (before && current ? [...current, ...r.entries] : r.entries));
      setMore(r.entries.length === PAGE);
    } catch {
      setEntries((current) => current ?? []);
      setMore(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, []);

  const when = (iso: string) =>
    new Date(iso).toLocaleString(lang === "de" ? "de-DE" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
  // A known action gets its sentence; one the backend recorded generically
  // ("POST /api/admin/...") is shown as it is.
  const label = (action: string) => {
    const key = `adminLog.action.${action}`;
    const text = t(key as never);
    return text === key ? action : text;
  };

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t("adminLog.title")}</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("common.back")}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-[var(--muted)]">{t("adminLog.intro")}</p>
        {entries === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
        {entries?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("adminLog.none")}</p>}
        {entries && entries.length > 0 && (
          <ol className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {entries.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-baseline gap-x-2 px-3 py-2 text-sm">
                <span className="font-medium">{entry.actor || "—"}</span>
                <span>{label(entry.action)}</span>
                {entry.target && <span className="font-medium">{entry.target}</span>}
                {entry.detail && <span className="text-[var(--muted)]">({entry.detail})</span>}
                <span className="flex-1" />
                <span className="text-xs text-[var(--muted)]">{entry.address}</span>
                <time className="shrink-0 text-xs text-[var(--muted)]" dateTime={entry.at}>
                  {when(entry.at)}
                </time>
              </li>
            ))}
          </ol>
        )}
        {more && entries && (
          <Button variant="outline" size="sm" className="mt-3" onClick={() => void load(entries[entries.length - 1].id)}>
            {t("adminLog.more")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
