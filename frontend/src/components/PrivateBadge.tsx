import { Lock } from "lucide-react";
import { useI18n } from "@/lib/i18n";

/** Marks a private project (backend services/visibility.py) wherever its
 *  name appears -- so a signed-in reader knows what strangers do not see. */
export function PrivateBadge({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--muted)]"
      title={t("project.privateHint")}
    >
      <Lock className="h-3 w-3" aria-hidden="true" />
      {compact ? <span className="sr-only">{t("project.private")}</span> : t("project.private")}
    </span>
  );
}
