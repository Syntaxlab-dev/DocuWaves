import { useI18n, type Lang } from "@/lib/i18n";

const LANGS: Lang[] = ["de", "en"];

/** The interface language, as two segments with the active one marked.
 *
 *  It used to be one button labelled with the language it would switch TO
 *  ("EN" on a German page), which read as the language currently shown --
 *  exactly backwards for anyone who did not already know the convention.
 *  Showing both, with the current one highlighted, says what is set and
 *  what the other choice is at the same time. */
export function UiLanguageToggle({ lang, onChange }: { lang: Lang; onChange: (lang: Lang) => void }) {
  const { t } = useI18n();
  return (
    <div
      role="group"
      aria-label={t("nav.language")}
      className="inline-flex h-8 items-center rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium"
    >
      {LANGS.map((code) => {
        const active = code === lang;
        return (
          <button
            key={code}
            type="button"
            aria-pressed={active}
            onClick={() => !active && onChange(code)}
            className={`rounded-md px-2 py-1 uppercase transition-colors ${
              active
                ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                : "text-[var(--muted)] hover:text-[var(--ink)]"
            }`}
          >
            {code}
          </button>
        );
      })}
    </div>
  );
}
