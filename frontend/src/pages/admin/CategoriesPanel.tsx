// A project's categories and the category form.
import { EntityIcon, IconField } from "@/components/EntityIcon";
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import {
  ArrowDown,
  ArrowUp,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { askConfirm } from "@/components/ConfirmDialog";
import { api, ApiError, type Category } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSite } from "@/lib/site";
import { categoryTree, parentChoices, siblingsOf } from "@/lib/categoryTree";
import { type FieldValues, toFieldValues, fromFieldValues, LocalizedInput } from "./shared";
import { CoverField } from "./ProjectsPanel";
import { CATEGORY_MIME, PAGE_MIME, carries, lowerHalf, reorder } from "@/lib/dragOrder";

/** Create OR edit, one form -- see ProjectForm, which this mirrors. */
export function CategoryForm({
  projectId,
  projectSlug,
  category,
  categories,
  onDone,
}: {
  projectId: number;
  /** The project the cover is uploaded into -- a category has no assets/
   *  folder of its own, its images live in the project's. */
  projectSlug: string;
  category: Category | null;
  /** The version's categories, for the "inside" choice. */
  categories: Category[];
  onDone: (slug?: string) => void;
}) {
  const { t } = useI18n();
  const { site } = useSite();
  const languages = site.languages;
  const [name, setName] = useState<FieldValues>(() =>
    category ? toFieldValues(category.name, category.name_i18n, languages, site.default_language) : {},
  );
  const [icon, setIcon] = useState(category?.icon ?? "");
  const [image, setImage] = useState(category?.image ?? "");
  const [imageUrl, setImageUrl] = useState<string | null>(category?.image_url ?? null);
  const [parent, setParent] = useState(category?.parent ?? "");
  const [saving, setSaving] = useState(false);
  const choices = parentChoices(categories, category?.slug ?? null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const resolved = fromFieldValues(name, languages, site.default_language);
    const data = { name: resolved.text, name_i18n: resolved.i18n, icon, image, parent };
    setSaving(true);
    try {
      if (category) {
        const saved = await api.adminUpdateCategory(category.id, data);
        onDone(saved.slug);
      } else {
        const created = await api.adminCreateCategory(projectId, data);
        onDone(created.slug);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mt-2 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
      <LocalizedInput label={t("admin.categoryName")} values={name} onChange={setName} languages={languages} required />
      <IconField placeholder={t("admin.categoryIcon")} value={icon} onChange={setIcon} />
      {/* Only when there is somewhere to nest it: in a project with one
          category, the choice would have a single answer. */}
      {(choices.length > 0 || parent) && (
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.categoryParent")}
          <select
            value={parent}
            onChange={(e) => setParent(e.target.value)}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm text-[var(--ink)]"
          >
            <option value="">{t("admin.categoryTopLevel")}</option>
            {choices.map(({ category: c, depth }) => (
              <option key={c.id} value={c.slug}>
                {`${"\u00a0\u00a0".repeat(depth)}${c.name}`}
              </option>
            ))}
          </select>
        </label>
      )}
      <CoverField
        projectSlug={projectSlug}
        // `_category.yml` sits one directory below assets/, exactly like a
        // page does -- so it stores the identical `../assets/x.png` a page's
        // Markdown does, and for the same reason: it resolves in GitHub's
        // own preview of the file too.
        pathOf={(asset) => asset.markdown_path}
        value={image}
        previewUrl={imageUrl}
        onChange={(next, url) => {
          setImage(next);
          setImageUrl(url);
        }}
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving}>
          {t("admin.save")}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => onDone()}>
          {t("admin.cancel")}
        </Button>
      </div>
    </form>
  );
}

export function CategoriesPanel({
  projectId,
  projectSlug,
  categories,
  selected,
  readOnly,
  onSelect,
  onChanged,
  onPageMoved,
}: {
  projectId: number;
  projectSlug: string;
  categories: Category[];
  selected: Category | null;
  /** A frozen version is being viewed: browse it, don't change it. */
  readOnly: boolean;
  onSelect: (c: Category) => void;
  onChanged: (slug?: string) => void;
  /** A page was dropped onto a category and moved there. */
  onPageMoved?: () => void;
}) {
  const { t } = useI18n();
  const [showForm, setShowForm] = useState(false);
  // Drag and drop: which category is being dragged, and where it would land
  // (before or after which sibling), or which category a page would go into.
  const [dragId, setDragId] = useState<number | null>(null);
  const [dropAt, setDropAt] = useState<{ id: number; after: boolean } | null>(null);
  const [pageInto, setPageInto] = useState<number | null>(null);

  async function dropCategory(target: Category, after: boolean) {
    const moving = categories.find((c) => c.id === dragId);
    setDragId(null);
    setDropAt(null);
    if (!moving || moving.parent !== target.parent) return;
    const siblings = siblingsOf(categories, target);
    const next = reorder(siblings, moving, target, after);
    if (next === siblings) return;
    try {
      await api.adminOrderCategories(next.map((c) => c.id));
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  async function dropPage(target: Category, pageId: number) {
    setPageInto(null);
    try {
      const result = await api.adminBulkPages("move", [pageId], target.id);
      if (result.done.length) toast.success(t("dnd.pageMoved").replace("{category}", target.name));
      else toast.error(result.skipped[0]?.reason || t("common.error"));
      onPageMoved?.();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }
  const [editingId, setEditingId] = useState<number | null>(null);

  async function onDelete(id: number) {
    const name = categories.find((x) => x.id === id)?.name ?? "";
    const ok = await askConfirm({
      title: t("admin.deleteCategoryTitle").replace("{name}", name),
      message: t("admin.deleteConfirm"),
      confirmLabel: t("admin.delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.adminDeleteCategory(id);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.categories")}</h2>
        {!readOnly && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              setShowForm((v) => !v);
              setEditingId(null);
            }}
            aria-label="add"
          >
            <Plus className="h-4 w-4" />
          </Button>
        )}
      </div>

      {showForm && !readOnly && (
        <CategoryForm
          projectId={projectId}
          projectSlug={projectSlug}
          category={null}
          categories={categories}
          onDone={(slug) => {
            setShowForm(false);
            if (slug) onChanged(slug);
          }}
        />
      )}

      <div className="mt-2 flex flex-col gap-1">
        {categoryTree(categories).map(({ category: c, depth }) => {
          // The arrows move a category among its siblings only -- the
          // server does the same.
          const siblings = siblingsOf(categories, c);
          const i = siblings.findIndex((s) => s.id === c.id);
          return (
          <div key={c.id} style={depth ? { marginLeft: `${depth * 0.75}rem` } : undefined}>
            <div
              data-category-row={c.slug}
              draggable={!readOnly && editingId !== c.id}
              onDragStart={(e) => {
                e.dataTransfer.setData(CATEGORY_MIME, String(c.id));
                e.dataTransfer.effectAllowed = "move";
                setDragId(c.id);
              }}
              onDragEnd={() => {
                setDragId(null);
                setDropAt(null);
              }}
              onDragOver={(e) => {
                if (readOnly) return;
                if (carries(e, PAGE_MIME)) {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  setPageInto(c.id);
                  return;
                }
                const moving = categories.find((x) => x.id === dragId);
                if (!carries(e, CATEGORY_MIME) || !moving || moving.id === c.id || moving.parent !== c.parent) return;
                e.preventDefault();
                const after = lowerHalf(e, e.currentTarget);
                if (dropAt?.id !== c.id || dropAt.after !== after) setDropAt({ id: c.id, after });
              }}
              onDragLeave={() => {
                setPageInto((id) => (id === c.id ? null : id));
                setDropAt((at) => (at?.id === c.id ? null : at));
              }}
              onDrop={(e) => {
                e.preventDefault();
                const page = Number(e.dataTransfer.getData(PAGE_MIME));
                if (page) void dropPage(c, page);
                else if (dropAt?.id === c.id) void dropCategory(c, dropAt.after);
              }}
              className={`group relative flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm ${
                selected?.id === c.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--surface-2)]"
              } ${pageInto === c.id ? "ring-2 ring-[var(--accent)]" : ""} ${dragId === c.id ? "opacity-50" : ""}`}
            >
              {dropAt?.id === c.id && (
                <span
                  aria-hidden="true"
                  className={`pointer-events-none absolute inset-x-1 h-0.5 rounded bg-[var(--accent)] ${dropAt.after ? "-bottom-0.5" : "-top-0.5"}`}
                />
              )}
              <button
                type="button"
                onClick={() => onSelect(c)}
                title={c.name}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <EntityIcon icon={c.icon} />
                <span className="truncate">{c.name}</span>
              </button>
              {!readOnly && (
                <span className="hover-reveal tree-actions flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={t("admin.edit")}
                    onClick={() => {
                      setShowForm(false);
                      setEditingId((current) => (current === c.id ? null : c.id));
                    }}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" aria-label={t("dnd.moveUp")} disabled={i === 0} onClick={() => api.adminMoveCategory(c.id, -1).then(() => onChanged())}>
                    <ArrowUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={t("dnd.moveDown")}
                    disabled={i === siblings.length - 1}
                    onClick={() => api.adminMoveCategory(c.id, 1).then(() => onChanged())}
                  >
                    <ArrowDown className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" aria-label={t("admin.delete")} onClick={() => onDelete(c.id)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </span>
              )}
            </div>
            {editingId === c.id && !readOnly && (
              <CategoryForm
                key={`${c.id}-${c.slug}`}
                projectId={projectId}
                projectSlug={projectSlug}
                category={c}
                categories={categories}
                onDone={(slug) => {
                  setEditingId(null);
                  if (slug) onChanged(slug);
                }}
              />
            )}
          </div>
          );
        })}
      </div>
    </div>
  );
}
