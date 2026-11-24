import { useEffect, useState } from "react";
import { ArrowUpCircle, X } from "lucide-react";
import { api, type UpdateCheck } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const DISMISSED_KEY = "docuwaves.updateDismissed";

function dismissedVersion(): string {
  try {
    return localStorage.getItem(DISMISSED_KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * "DocuWaves 1.2.0 is available" above the admin area, for admins only:
 * they are the ones who can update the instance. Dismissing it hides that
 * release; the next one shows again. The check itself runs on the server
 * at most once a day (backend services/update_check.py).
 */
export function UpdateNotice() {
  const { t } = useI18n();
  const [update, setUpdate] = useState<UpdateCheck | null>(null);
  const [dismissed, setDismissed] = useState(dismissedVersion);

  useEffect(() => {
    api
      .adminUpdateCheck()
      .then(setUpdate)
      .catch(() => setUpdate(null));
  }, []);

  if (!update?.newer || !update.latest || dismissed === update.latest) return null;

  function dismiss() {
    if (!update?.latest) return;
    try {
      localStorage.setItem(DISMISSED_KEY, update.latest);
    } catch {
      // Private window: it stays hidden until the next reload, which is fine.
    }
    setDismissed(update.latest);
  }

  return (
    <div
      role="status"
      className="mb-4 flex items-center gap-3 rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/10 px-3 py-2 text-sm"
    >
      <ArrowUpCircle className="h-4 w-4 shrink-0 text-[var(--accent)]" aria-hidden="true" />
      <span className="flex-1">
        {t("update.available").replace("{latest}", update.latest).replace("{current}", update.current)}{" "}
        {update.url && (
          <a href={update.url} target="_blank" rel="noreferrer" className="font-medium underline">
            {t("update.notes")}
          </a>
        )}
      </span>
      <button
        type="button"
        onClick={dismiss}
        className="rounded p-1 text-[var(--muted)] hover:text-[var(--ink)]"
        aria-label={t("update.dismiss")}
        title={t("update.dismiss")}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
