// The translatable-field helpers every admin form uses (LocalizedInput and friends).
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { Input } from "@/components/ui/input";
import { type LocalizedText } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { languageName } from "@/lib/lang";

/**
 * Every human-readable field the content repo lets you translate (a
 * project's or category's name and description, the site's name/tagline/
 * footer) is edited through the three helpers below.
 *
 * On a single-language instance they collapse to exactly one plain input --
 * the field keeps its own label, there are no tabs, no codes, no per-
 * language rows, nothing at all to notice. The whole feature only appears
 * once `languages:` in _site.yml names more than one, which is the same
 * rule the public site follows.
 *
 * A field is edited as a map of language code to text; "" is the key a
 * single-language instance uses, since it has no code to name.
 */
export type FieldValues = Record<string, string>;

export const SINGLE = [""];

export function fieldLanguages(languages: string[]): string[] {
  return languages.length > 1 ? languages : SINGLE;
}

/** Stored value (default-language text + mapping) -> what the inputs edit. */
export function toFieldValues(text: string, i18n: LocalizedText, languages: string[], defaultLanguage: string): FieldValues {
  if (languages.length < 2) return { "": text };
  return Object.fromEntries(
    languages.map((code) => [code, i18n[code] ?? (code === defaultLanguage ? text : "")]),
  );
}

/** ...and back: `text` is always the DEFAULT language's, because that is
 *  what slugs are derived from and what a reader of an untranslated
 *  language falls back to. */
export function fromFieldValues(
  values: FieldValues,
  languages: string[],
  defaultLanguage: string,
): { text: string; i18n: LocalizedText } {
  if (languages.length < 2) return { text: values[""] ?? "", i18n: {} };
  return { text: values[defaultLanguage] ?? "", i18n: values };
}

export function LocalizedInput({
  label,
  values,
  onChange,
  languages,
  required,
}: {
  label: string;
  values: FieldValues;
  onChange: (values: FieldValues) => void;
  languages: string[];
  required?: boolean;
}) {
  const { lang: uiLang } = useI18n();
  const codes = fieldLanguages(languages);

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      {codes.map((code) => (
        <div key={code} className="flex items-center gap-2">
          {/* No code beside the input when there is only one language --
              the single-language form has to look untouched. */}
          {code && (
            <span
              className="w-7 shrink-0 text-xs uppercase text-[var(--muted)]"
              title={languageName(code, uiLang)}
            >
              {code}
            </span>
          )}
          <Input
            value={values[code] ?? ""}
            aria-label={code ? `${label} (${languageName(code, uiLang)})` : label}
            // Required on the default language only: a translation that
            // hasn't been written yet is a normal state, not a form error.
            required={required && code === codes[0]}
            onChange={(e) => onChange({ ...values, [code]: e.target.value })}
            className="flex-1"
          />
        </div>
      ))}
    </div>
  );
}
