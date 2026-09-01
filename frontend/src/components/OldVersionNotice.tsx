import { Link } from "react-router-dom";
import { History } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useDocPath, useProjectVersion } from "@/lib/version";

/**
 * "You are reading the documentation for 2.0. The current version is
 * Current." -- shown on every page of a frozen version, above the content.
 *
 * NOT dismissible, deliberately. Which version you are reading is a
 * permanent property of the page, not a notification: a reader who
 * dismissed it once and lands here again from a search engine three weeks
 * later would be reading a superseded install guide with nothing on screen
 * saying so, which is exactly the failure this notice exists to prevent.
 * What it can be is quiet -- one line, the muted surface colour the
 * fallback-language notice already uses, no icon shouting, no colour that
 * says "error" about a page that is perfectly correct for its release.
 *
 * The link goes to the SAME page in the current version when that page
 * exists there, and to the current version's home when it doesn't -- the
 * same rule the switcher follows, for the same reason: an old page's reader
 * is looking for today's answer, and a 404 isn't one.
 */
export function OldVersionNotice() {
  const { t } = useI18n();
  const { projectSlug, tail, info } = useProjectVersion();
  const docPath = useDocPath();

  if (!projectSlug || !info || !info.is_frozen) return null;

  const label = info.frozen.find((v) => v.id === info.selected)?.label ?? info.selected;
  const stays = info.available === null || info.available.includes(info.current_id);
  const target = docPath(projectSlug, stays ? tail : "", info.current_id, info);

  return (
    <p className="mb-5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
      <History className="mr-1.5 inline h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
      {t("version.oldPrefix")}
      <strong className="font-medium text-[var(--ink)]">{label}</strong>
      {t("version.oldMiddle")}
      <Link to={target} className="text-[var(--accent)] hover:underline">
        {info.current_label}
      </Link>
      {t("version.oldSuffix")}
    </p>
  );
}
