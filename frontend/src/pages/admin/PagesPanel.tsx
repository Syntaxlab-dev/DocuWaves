// A category's pages, one row per page whatever languages it exists in.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useEffect, useRef, useState } from "react";
import { GripVertical, Plus, PencilLine, Trash2 } from "lucide-react";
import { PAGE_MIME, carries, lowerHalf, reorder } from "@/lib/dragOrder";
import { Button } from "@/components/ui/button";
import { ReviewMark } from "@/components/ReviewWorkflow";
import { askConfirm } from "@/components/ConfirmDialog";
import { SkeletonLines } from "@/components/Skeleton";
import { toast } from "sonner";
import { api, ApiError, type BulkAction, type Category, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { relativeTime } from "@/lib/time";
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

/** How long "Undo" is offered after deleting a page. */
const UNDO_MS = 6000;

export function PagesPanel({
  pages,
  loading = false,
  readOnly,
  categories = [],
  onEdit,
  onChanged,
}: {
  pages: Page[];
  /** The list is still being fetched: placeholders instead of rows. */
  loading?: boolean;
  /** The project's categories in this version: where "move" can go. */
  categories?: Category[];
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

  // Bulk actions: which pages (by the slug that groups their languages)
  // are ticked. Cleared whenever the list itself changes.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const listKey = groups.map((g) => g.slug).join("|");
  useEffect(() => setSelected(new Set()), [listKey, categoryId]);
  const allSelected = groups.length > 0 && selected.size === groups.length;
  function toggle(slug: string, on: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (on) next.add(slug);
      else next.delete(slug);
      return next;
    });
  }

  // Drag and drop (and Alt+arrow keys): the order of the pages, by slug.
  const [dragSlug, setDragSlug] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<{ slug: string; after: boolean } | null>(null);
  const [order, setOrder] = useState<string[] | null>(null);
  useEffect(() => setOrder(null), [listKey]);
  const sorted = order
    ? order.map((slug) => groups.find((g) => g.slug === slug)).filter((g): g is (typeof groups)[number] => !!g)
    : groups;

  async function saveOrder(next: string[]) {
    if (categoryId === null) return;
    setOrder(next);
    const ids = next
      .map((slug) => groups.find((g) => g.slug === slug))
      .filter((g): g is (typeof groups)[number] => !!g)
      .map((g) => (g.variants.get(site.default_language) ?? [...g.variants.values()][0]).id);
    try {
      await api.adminOrderPages(categoryId, ids);
      onChanged();
    } catch (err) {
      setOrder(null);
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  function dropOn(target: string, after: boolean) {
    const moving = dragSlug;
    setDragSlug(null);
    setDropAt(null);
    if (!moving) return;
    const slugs = sorted.map((g) => g.slug);
    const next = reorder(slugs, moving, target, after);
    if (next !== slugs) void saveOrder(next);
  }

  function nudge(slug: string, direction: -1 | 1) {
    const slugs = sorted.map((g) => g.slug);
    const at = slugs.indexOf(slug);
    const to = at + direction;
    if (at < 0 || to < 0 || to >= slugs.length) return;
    void saveOrder(reorder(slugs, slug, slugs[to], direction === 1));
  }

  async function runBulk(action: BulkAction, categoryTarget?: number) {
    // The default-language row stands for the page: publishing acts on it
    // (a half-done translation stays a draft), deleting and moving take
    // every language along anyway.
    const ids = groups
      .filter((g) => selected.has(g.slug))
      .map((g) => (g.variants.get(site.default_language) ?? [...g.variants.values()][0]).id);
    if (ids.length === 0) return;
    if (
      action === "delete" &&
      !(await askConfirm({
        title: t("bulk.deleteTitle").replace("{n}", String(ids.length)),
        message: t("bulk.deleteConfirm").replace("{n}", String(ids.length)),
        confirmLabel: t("admin.delete"),
        danger: true,
      }))
    )
      return;
    setBusy(true);
    try {
      const result = await api.adminBulkPages(action, ids, categoryTarget);
      const message = t("bulk.done").replace("{n}", String(result.done.length));
      if (result.skipped.length > 0) {
        toast.warning(`${message} ${t("bulk.skipped").replace("{n}", String(result.skipped.length))}`);
      } else {
        toast.success(message);
      }
      setSelected(new Set());
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  // Deleting a page asks nothing up front: the row goes at once and a toast
  // offers "Undo" for a few seconds, and only then is the delete sent. A
  // delete still waiting when the list goes away (another category opened)
  // is sent right then; closing the tab inside the window keeps the page.
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const pendingDeletes = useRef(new Map<string, { timer: number; run: () => void }>());
  useEffect(() => {
    const pending = pendingDeletes.current;
    return () => {
      for (const { timer, run } of pending.values()) {
        window.clearTimeout(timer);
        run();
      }
    };
  }, []);

  function setDeletingSlug(slug: string, on: boolean) {
    setDeleting((current) => {
      const next = new Set(current);
      if (on) next.add(slug);
      else next.delete(slug);
      return next;
    });
  }

  function onDelete(group: PageGroup, id: number) {
    const slug = group.slug;
    const run = () => {
      pendingDeletes.current.delete(slug);
      api
        .adminDeletePage(id)
        .then(() => onChanged())
        .catch((err) => {
          setDeletingSlug(slug, false);
          toast.error(err instanceof ApiError ? err.message : t("common.error"));
        });
    };
    const timer = window.setTimeout(run, UNDO_MS);
    pendingDeletes.current.set(slug, { timer, run });
    setDeletingSlug(slug, true);
    toast(t("admin.pageDeleted").replace("{title}", group.title), {
      duration: UNDO_MS,
      action: {
        label: t("common.undo"),
        onClick: () => {
          window.clearTimeout(timer);
          pendingDeletes.current.delete(slug);
          setDeletingSlug(slug, false);
        },
      },
    });
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
      {!readOnly && selected.size > 0 && (
        <div
          role="toolbar"
          aria-label={t("bulk.toolbar")}
          className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-[var(--accent)] bg-[var(--surface-2)] px-3 py-1.5 text-sm"
        >
          <span className="font-medium">{t("bulk.selected").replace("{n}", String(selected.size))}</span>
          <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void runBulk("publish")}>
            {t("bulk.publish")}
          </Button>
          <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void runBulk("unpublish")}>
            {t("bulk.unpublish")}
          </Button>
          {categories.length > 1 && (
            <select
              aria-label={t("bulk.moveTo")}
              disabled={busy}
              value=""
              onChange={(e) => e.target.value && void runBulk("move", Number(e.target.value))}
              className="h-7 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-xs"
            >
              <option value="">{t("bulk.moveTo")}</option>
              {categories
                .filter((c) => c.id !== categoryId)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </select>
          )}
          <Button size="sm" variant="outline" className="h-7 text-red-600" disabled={busy} onClick={() => void runBulk("delete")}>
            {t("bulk.delete")}
          </Button>
          <Button size="sm" variant="ghost" className="ml-auto h-7" onClick={() => setSelected(new Set())}>
            {t("bulk.clear")}
          </Button>
        </div>
      )}
      <div className="mt-2 flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
        {!readOnly && groups.length > 1 && (
          <label className="flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--muted)]">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={(e) => setSelected(e.target.checked ? new Set(groups.map((g) => g.slug)) : new Set())}
            />
            {t("bulk.selectAll")}
          </label>
        )}
        {loading && <div className="px-3 py-2"><SkeletonLines rows={4} label={t("common.loading")} /></div>}
        {!loading && groups.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-[var(--muted)]">
            <p>{t("admin.noPages")}</p>
            {!readOnly && (
              <Button size="sm" variant="outline" className="mt-3" onClick={() => onEdit({ kind: "new" })}>
                <Plus className="h-3.5 w-3.5" />
                {t("admin.newPage")}
              </Button>
            )}
          </div>
        )}
        {!loading && sorted.filter((group) => !deleting.has(group.slug)).map((group) => {
          // Opening the row itself lands on the default language, which is
          // the version that always exists.
          const primary = group.variants.get(site.default_language) ?? [...group.variants.values()][0];
          return (
            <div
              key={group.slug}
              data-page-row={group.slug}
              draggable={!readOnly}
              onDragStart={(e) => {
                e.dataTransfer.setData(PAGE_MIME, String(primary.id));
                e.dataTransfer.setData("text/plain", group.title);
                e.dataTransfer.effectAllowed = "move";
                setDragSlug(group.slug);
              }}
              onDragEnd={() => {
                setDragSlug(null);
                setDropAt(null);
              }}
              onDragOver={(e) => {
                if (readOnly || !dragSlug || dragSlug === group.slug || !carries(e, PAGE_MIME)) return;
                e.preventDefault();
                const after = lowerHalf(e, e.currentTarget);
                if (dropAt?.slug !== group.slug || dropAt.after !== after) setDropAt({ slug: group.slug, after });
              }}
              onDrop={(e) => {
                e.preventDefault();
                if (dropAt?.slug === group.slug) dropOn(group.slug, dropAt.after);
              }}
              onKeyDown={(e) => {
                if (readOnly || !e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
                e.preventDefault();
                nudge(group.slug, e.key === "ArrowUp" ? -1 : 1);
              }}
              className={`group relative flex items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--surface-2)] ${
                dragSlug === group.slug ? "opacity-50" : ""
              }`}
            >
              {dropAt?.slug === group.slug && (
                <span
                  aria-hidden="true"
                  className={`pointer-events-none absolute inset-x-2 h-0.5 rounded bg-[var(--accent)] ${dropAt.after ? "-bottom-px" : "-top-px"}`}
                />
              )}
              {!readOnly && (
                <GripVertical
                  className="hover-reveal drag-grip h-3.5 w-3.5 shrink-0 cursor-grab text-[var(--muted)]"
                  aria-hidden="true"
                >
                  <title>{t("dnd.dragHint")}</title>
                </GripVertical>
              )}
              {!readOnly && (
                <input
                  type="checkbox"
                  aria-label={t("bulk.select").replace("{title}", group.title)}
                  checked={selected.has(group.slug)}
                  onChange={(e) => toggle(group.slug, e.target.checked)}
                />
              )}
              <button
                type="button"
                onClick={() => onEdit({ kind: "page", slug: group.slug, language: primary.language })}
                className="min-w-0 flex-1 text-left"
              >
                <span className="block truncate">{group.title}</span>
                {(() => {
                  // The newest change across the page's languages.
                  const last = [...group.variants.values()]
                    .map((v) => v.last_change)
                    .filter((c): c is { date: string; author: string } => !!c)
                    .sort((a, b) => b.date.localeCompare(a.date))[0];
                  if (!last) return null;
                  return (
                    <span className="block truncate text-xs text-[var(--muted)]" title={new Date(last.date).toLocaleString(uiLang)}>
                      {t("admin.lastChange")
                        .replace("{when}", relativeTime(last.date, uiLang))
                        .replace("{who}", last.author)}
                    </span>
                  );
                })()}
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
                <StatusChip published={primary.published} />
              )}

              {!readOnly && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="hover-reveal h-6 w-6"
                  aria-label={t("admin.delete")}
                  onClick={() => onDelete(group, primary.id)}
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

/** Published or draft as a small pill: green dot for live, grey for draft. */
export function StatusChip({ published }: { published: boolean }) {
  const { t } = useI18n();
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 text-[11px] font-medium leading-5 ${
        published
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "bg-[var(--surface-2)] text-[var(--muted)]"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${published ? "bg-emerald-500" : "bg-[var(--muted)]"}`} aria-hidden="true" />
      {published ? t("admin.published") : t("admin.draft")}
    </span>
  );
}
