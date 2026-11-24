import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type PageSchedule } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** A local `datetime-local` value ("2026-12-01T09:00") as an ISO moment
 *  WITH this browser's offset -- the backend refuses a time without one. */
function withOffset(local: string): string {
  return new Date(local).toISOString();
}

/**
 * Publish this draft at a set time (backend services/scheduled_publish.py).
 * Offered for a saved draft outside projects that require approval -- there
 * going live is what the approval does, and the backend refuses it too.
 */
export function SchedulePanel({ pageId, readOnly }: { pageId: number; readOnly: boolean }) {
  const { t, lang } = useI18n();
  const [schedule, setSchedule] = useState<PageSchedule | null>(null);
  const [open, setOpen] = useState(false);
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSchedule(null);
    setOpen(false);
    api
      .adminPageSchedule(pageId)
      .then((r) => setSchedule(r.schedule))
      .catch(() => setSchedule(null));
  }, [pageId]);

  const shown = (iso: string) =>
    new Date(iso).toLocaleString(lang === "de" ? "de-DE" : "en-GB", { dateStyle: "full", timeStyle: "short" });

  async function save() {
    if (!when) return;
    setBusy(true);
    try {
      const r = await api.adminSetPageSchedule(pageId, withOffset(when));
      setSchedule(r.schedule);
      setOpen(false);
      toast.success(t("schedule.set").replace("{when}", shown(r.schedule.publish_at)));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      await api.adminCancelPageSchedule(pageId);
      setSchedule(null);
      toast.success(t("schedule.cancelled"));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  if (schedule) {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm">
        <CalendarClock className="h-4 w-4 text-[var(--accent)]" />
        <span>
          {t("schedule.goesLive").replace("{when}", shown(schedule.publish_at)).replace("{by}", schedule.scheduled_by)}
        </span>
        {!readOnly && (
          <Button variant="ghost" size="sm" className="ml-auto h-7" disabled={busy} onClick={() => void cancel()}>
            <X className="h-3.5 w-3.5" /> {t("schedule.cancel")}
          </Button>
        )}
      </div>
    );
  }
  if (readOnly) return null;
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 inline-flex items-center gap-1.5 self-start text-sm text-[var(--muted)] hover:text-[var(--ink)]"
      >
        <CalendarClock className="h-4 w-4" />
        {t("schedule.open")}
      </button>
    );
  }
  return (
    <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm">
      <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
        {t("schedule.when")}
        <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="h-8" />
      </label>
      <Button size="sm" disabled={busy || !when} onClick={() => void save()}>
        {t("schedule.save")}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
        {t("schedule.dismiss")}
      </Button>
      <span className="basis-full text-xs text-[var(--muted)]">{t("schedule.hint")}</span>
    </div>
  );
}
