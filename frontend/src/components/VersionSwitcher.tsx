import { useNavigate } from "react-router-dom";
import { History } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useDocPath, useProjectVersion } from "@/lib/version";

/**
 * Switches the documentation version while staying on the same page.
 *
 * A <select> rather than the row of links the language switcher uses: a
 * project has one row of languages but a growing list of releases, and a
 * header that gains a link per release stops being a header. Native, so it
 * costs nothing on a phone and needs no menu machinery of its own.
 *
 * "Staying on the same page" is checked, not hoped for: `available` says
 * which versions the page (or category) being read exists in, so a target
 * that doesn't have it goes to that version's home instead of to a 404.
 * `available` is null on a project's landing page, which every version has,
 * and the reader stays exactly where they are.
 *
 * Renders nothing when the reader isn't inside a project, when the project
 * has no `_versions.yml`, and when it has one but no frozen versions yet:
 * there is nothing to switch BETWEEN, and a control with one option is
 * furniture.
 */
export function VersionSwitcher() {
  const { t } = useI18n();
  const { projectSlug, version, tail, info } = useProjectVersion();
  const docPath = useDocPath();
  const navigate = useNavigate();

  if (!projectSlug || !info || info.frozen.length === 0) return null;

  const options = [
    { id: info.current_id, label: info.current_label },
    ...info.frozen.map((v) => ({ id: v.id, label: v.label })),
  ];
  const available = info.available;

  return (
    <div className="flex items-center gap-1">
      <History className="h-3.5 w-3.5 text-[var(--muted)]" aria-hidden="true" />
      <select
        aria-label={t("version.switcher")}
        title={t("version.switcher")}
        value={version || info.default}
        onChange={(e) => {
          const id = e.target.value;
          const stays = available === null || available.includes(id);
          navigate(docPath(projectSlug, stays ? tail : "", id, info));
        }}
        className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-1.5 text-sm text-[var(--ink)]"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
