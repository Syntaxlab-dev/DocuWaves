import { useI18n } from "@/lib/i18n";
import { languageName, useContentLang } from "@/lib/lang";

/**
 * Marks a navigation entry whose page exists only in the site's default
 * language -- in the sidebar, and in a category's page list.
 *
 * The restrained treatment is deliberate: a small muted language code
 * ("DE") after the title, in the same muted colour the rest of the
 * navigation's secondary text already uses, with the full sentence in its
 * `title`/`aria-label` for anyone who wants it. Not an icon (one more
 * symbol to learn), not a colour (nothing here is wrong or urgent), and not
 * a hidden entry: the page IS readable, and a reader who follows the link
 * gets the notice on the page itself. All this badge has to do is stop the
 * language on the other side from being a surprise.
 */
export function FallbackBadge({ language }: { language: string }) {
  const { t } = useI18n();
  const { lang } = useContentLang();
  if (!language) return null;
  const label = `${t("page.fallbackBadge")}${languageName(language, lang)}${t("page.fallbackBadgeSuffix")}`;
  return (
    <span
      title={label}
      aria-label={label}
      className="ml-1.5 shrink-0 rounded border border-[var(--border)] px-1 text-[10px] uppercase leading-4 tracking-wide text-[var(--muted)]"
    >
      {language}
    </span>
  );
}
