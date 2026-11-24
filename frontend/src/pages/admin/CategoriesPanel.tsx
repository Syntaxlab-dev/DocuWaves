// A project's categories and the category form.
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
import { Input } from "@/components/ui/input";
import { api, ApiError, type Category } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSite } from "@/lib/site";
import { type FieldValues, toFieldValues, fromFieldValues, LocalizedInput } from "./shared";
import { CoverField } from "./ProjectsPanel";

/** Create OR edit, one form -- see ProjectForm, which this mirrors. */
export function CategoryForm({
  projectId,
  projectSlug,
  category,
  onDone,
}: {
  projectId: number;
  /** The project the cover is uploaded into -- a category has no assets/
   *  folder of its own, its images live in the project's. */
  projectSlug: string;
  category: Category | null;
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
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const resolved = fromFieldValues(name, languages, site.default_language);
    const data = { name: resolved.text, name_i18n: resolved.i18n, icon, image };
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
      <Input placeholder={t("admin.categoryIcon")} value={icon} onChange={(e) => setIcon(e.target.value)} />
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
}: {
  projectId: number;
  projectSlug: string;
  categories: Category[];
  selected: Category | null;
  /** A frozen version is being viewed: browse it, don't change it. */
  readOnly: boolean;
  onSelect: (c: Category) => void;
  onChanged: (slug?: string) => void;
}) {
  const { t } = useI18n();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  async function onDelete(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
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
          onDone={(slug) => {
            setShowForm(false);
            if (slug) onChanged(slug);
          }}
        />
      )}

      <div className="mt-2 flex flex-col gap-1">
        {categories.map((c, i) => (
          <div key={c.id}>
            <div
              className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm ${
                selected?.id === c.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--surface-2)]"
              }`}
            >
              <button type="button" onClick={() => onSelect(c)} className="flex flex-1 items-center gap-2 text-left">
                {c.icon && <span>{c.icon}</span>}
                {c.name}
              </button>
              {!readOnly && (
                <>
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
                  <Button variant="ghost" size="icon" className="h-6 w-6" disabled={i === 0} onClick={() => api.adminMoveCategory(c.id, -1).then(() => onChanged())}>
                    <ArrowUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    disabled={i === categories.length - 1}
                    onClick={() => api.adminMoveCategory(c.id, 1).then(() => onChanged())}
                  >
                    <ArrowDown className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(c.id)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </>
              )}
            </div>
            {editingId === c.id && !readOnly && (
              <CategoryForm
                key={`${c.id}-${c.slug}`}
                projectId={projectId}
                projectSlug={projectSlug}
                category={c}
                onDone={(slug) => {
                  setEditingId(null);
                  if (slug) onChanged(slug);
                }}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
