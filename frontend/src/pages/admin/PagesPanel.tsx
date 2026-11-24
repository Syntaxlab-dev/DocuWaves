// A category's pages, one row per page whatever languages it exists in.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useEffect, useState } from "react";
import { Plus, PencilLine, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReviewMark } from "@/components/ReviewWorkflow";
import { api, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { languageName } from "@/lib/lang";
import { useSite } from "@/lib/site";

/**
 * What the editor was opened on. A page and one of its translations are the
 * same page, so the editor is addressed by SLUG plus language rather than
 * by the numeric id of one language's row -- "translate this page" has to
 * mean "the English version of this same slug", never "a new page called
 * whatever the English title turned out to be".
 */
export type EditorTarget =
  /** A page that doesn't exist yet: no slug until it is first saved.
   *  `title` prefills it (a page started from the gaps radar). */
  | { kind: "new"; title?: string; body?: string }
  /** An existing page, opened in one of the languages it exists in. */
  | { kind: "page"; slug: string; language: string }
  /** A translation that does not exist yet, of a page that does. */
  | { kind: "translation"; slug: string; language: string };

/** The language variants of one page, keyed by language code. */
export interface PageGroup {
  slug: string;
  title: string;
  variants: Map<string, Page>;
}

/** One entry per page, however many languages it exists in -- the admin
 *  list endpoint returns a row per translation, and a list showing
 *  "Installation" three times would be a list of files, not of pages. */
export function groupPages(pages: Page[], defaultLanguage: string): PageGroup[] {
  const groups = new Map<string, PageGroup>();
  for (const page of pages) {
    const group = groups.get(page.slug) ?? { slug: page.slug, title: page.title, variants: new Map() };
    group.variants.set(page.language, page);
    // The default language's title labels the group: it is the one that
    // always exists (a translation is written from it) and the one the slug
    // came from.
    if (page.language === defaultLanguage || group.variants.size === 1) group.title = page.title;
    groups.set(page.slug, group);
  }
  return [...groups.values()];
}

export function PagesPanel({
  pages,
  readOnly,
  onEdit,
  onChanged,
}: {
  pages: Page[];
  /** A frozen version is being viewed: its pages open read-only, and there
   *  is nothing here to create or delete. */
  readOnly: boolean;
  onEdit: (target: EditorTarget) => void;
  onChanged: () => void;
}) {
  const { t, lang: uiLang } = useI18n();
  const { site } = useSite();
  const multilingual = site.languages.length > 1;
  const groups = groupPages(pages, site.default_language);
  // Which of these pages somebody has open in the editor right now
  // (services/editing_presence.py), refreshed every 30 s.
  const categoryId = pages[0]?.category_id ?? null;
  const { status: auth } = useAuth();
  const [editing, setEditing] = useState<Record<string, { username: string; dirty: boolean }[]>>({});
  useEffect(() => {
    if (categoryId === null) return;
    let alive = true;
    const load = () =>
      api
        .adminCategoryPresence(categoryId)
        .then((r) => alive && setEditing(r.pages))
        .catch(() => {});
    load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [categoryId]);

  async function onDelete(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
    await api.adminDeletePage(id);
    onChanged();
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.pages")}</h2>
        {!readOnly && (
          <Button variant="outline" size="sm" onClick={() => onEdit({ kind: "new" })}>
            <Plus className="h-3.5 w-3.5" />
            {t("admin.newPage")}
          </Button>
        )}
      </div>
      <div className="mt-2 flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
        {groups.map((group) => {
          // Opening the row itself lands on the default language, which is
          // the version that always exists.
          const primary = group.variants.get(site.default_language) ?? [...group.variants.values()][0];
          return (
            <div key={group.slug} className="flex items-center gap-2 px-3 py-2 text-sm">
              <button
                type="button"
                onClick={() => onEdit({ kind: "page", slug: group.slug, language: primary.language })}
                className="flex-1 text-left"
              >
                {group.title}
              </button>
              {(() => {
                // Others only: your own open editor is not news to you.
                const names = [...group.variants.values()]
                  .flatMap((v) => editing[String(v.id)] ?? [])
                  .filter((n) => n.username !== auth?.username);
                if (names.length === 0) return null;
                const label = t("presence.listMark").replace(
                  "{names}",
                  [...new Set(names.map((n) => n.username))].join(", "),
                );
                return (
                  <span className="inline-flex items-center text-amber-600 dark:text-amber-400" title={label} aria-label={label}>
                    <PencilLine className="h-3.5 w-3.5" />
                  </span>
                );
              })()}

              {/* Which languages this page exists in, and which are still
                  missing -- one row of codes, each a link into the editor
                  on that language. A missing one is dimmed and dashed,
                  clicking it starts the translation. Nothing of this shows
                  on a single-language instance. */}
              <ReviewMark variants={[...group.variants.values()]} />

              {multilingual && (
                <div className="flex items-center gap-1" aria-label={t("admin.pageLanguages")}>
                  {site.languages.map((code) => {
                    const variant = group.variants.get(code);
                    return (
                      <button
                        key={code}
                        type="button"
                        title={
                          variant
                            ? `${languageName(code, uiLang)} — ${variant.published ? t("admin.published") : t("admin.draft")}`
                            : `${languageName(code, uiLang)} — ${t("admin.createTranslation")}`
                        }
                        // A missing translation is not something to start
                        // in a frozen version, so the dashed "create" click
                        // is simply not offered there.
                        disabled={readOnly && !variant}
                        onClick={() =>
                          onEdit(
                            variant
                              ? { kind: "page", slug: group.slug, language: code }
                              : { kind: "translation", slug: group.slug, language: code },
                          )
                        }
                        className={
                          variant
                            ? `rounded border border-[var(--border)] px-1 text-[10px] uppercase leading-4 ${
                                variant.published ? "text-[var(--accent)]" : "text-[var(--muted)]"
                              }`
                            : "rounded border border-dashed border-[var(--border)] px-1 text-[10px] uppercase leading-4 text-[var(--muted)] opacity-60"
                        }
                      >
                        {code}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* On a single-language instance this is the same published/
                  draft label it always was; with languages the state is per
                  translation and lives on the codes above instead. */}
              {!multilingual && primary && (
                <span className={`text-xs ${primary.published ? "text-[var(--accent)]" : "text-[var(--muted)]"}`}>
                  {primary.published ? t("admin.published") : t("admin.draft")}
                </span>
              )}

              {!readOnly && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  aria-label={t("admin.delete")}
                  onClick={() => onDelete(primary.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
