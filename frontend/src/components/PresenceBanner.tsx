import { Users } from "lucide-react";
import type { PresenceEntry } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function since(seconds: number, t: (key: never) => string): string {
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return t("presence.justNow" as never);
  if (minutes < 60) return t("presence.minutes" as never).replace("{n}", String(minutes));
  return t("presence.hours" as never).replace("{n}", String(Math.floor(minutes / 60)));
}

/** "Michel is editing this page (for 5 min) -- with unsaved changes."
 *  A warning, not a lock: saving still works, and the save itself refuses
 *  to overwrite text that changed in the meantime. */
export function PresenceBanner({ others }: { others: PresenceEntry[] }) {
  const { t } = useI18n();
  if (others.length === 0) return null;
  return (
    <div
      className="mb-3 flex gap-2 rounded-lg border border-amber-400/60 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300"
      role="status"
    >
      <Users className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div>
        {others.map((o) => (
          <p key={`${o.username}-${o.since}`}>
            {o.same_account
              ? t("presence.otherTab")
              : t("presence.editing").replace("{name}", o.username).replace("{since}", since(o.seconds, t))}
            {o.dirty && ` ${t("presence.dirty")}`}
          </p>
        ))}
        <p className="mt-0.5 text-xs opacity-80">{t("presence.hint")}</p>
      </div>
    </div>
  );
}
