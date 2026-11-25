// The project list and the project form.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { toast } from "sonner";
import {
  ArrowDown,
  ArrowUp,
  ImagePlus,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PrivateBadge } from "@/components/PrivateBadge";
import { api, ApiError, type Asset, type Project } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSite } from "@/lib/site";
import { type FieldValues, toFieldValues, fromFieldValues, LocalizedInput } from "./shared";

/**
 * A cover image slot, shared by the project and the category form.
 *
 * The upload always goes into the PROJECT's own assets/ folder -- that is
 * the on-disk convention for every image in this app (content/<project>/
 * [<version>/]assets/), and it is what lets a cover be re-used on a page, or
 * a page's screenshot be re-used as a cover, without a second copy of the
 * file. Only the way the path is SPELLED differs, because the two files that
 * hold it sit at different depths: `assets/x.png` from a `_project.yml`,
 * `../assets/x.png` from a `_category.yml`. That difference is `pathOf`, and
 * both spellings come straight from the upload response rather than being
 * assembled here -- the server knows whether the project is versioned, and a
 * second guess at it in the browser is a second thing to keep in step.
 *
 * Uploading commits the file immediately (that is what gives it a URL to
 * preview); which file the tile USES is only decided when the form is saved
 * -- the same split the branding image fields make.
 */
export function CoverField({
  projectSlug,
  pathOf,
  value,
  previewUrl,
  onChange,
}: {
  /** The project whose assets/ folder receives the upload. "" while a
   *  project is being created and has no directory in the repo yet. */
  projectSlug: string;
  pathOf: (asset: Asset) => string;
  /** The stored path, exactly as it will be written to the YAML file. */
  value: string;
  /** The resolved URL to preview, or null when the path names no real
   *  image -- which is also what a stale path looks like, so the preview
   *  going blank is the honest signal that the tile has no cover either. */
  previewUrl: string | null;
  onChange: (image: string, previewUrl: string | null) => void;
}) {
  const { t } = useI18n();
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Cleared right away so picking the SAME file again still fires change.
    e.target.value = "";
    if (!file || !projectSlug) return;
    setUploading(true);
    try {
      const asset = await api.adminUploadAsset(projectSlug, file);
      onChange(pathOf(asset), asset.url);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{t("admin.cover")}</span>
      <div className="flex items-center gap-2">
        {previewUrl ? (
          // 16:9, the same crop the public tile uses, so what is judged
          // here is what will actually be on the tile.
          <img
            src={previewUrl}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-10 w-[4.5rem] shrink-0 rounded border border-[var(--border)] bg-[var(--surface-2)] object-cover"
          />
        ) : (
          <span className="text-xs text-[var(--muted)]">{t("admin.coverNone")}</span>
        )}
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--muted)]" title={value}>
          {value}
        </span>
        {value && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label={t("admin.coverRemove")}
            // Clearing only drops the reference; the image file itself stays
            // in assets/, where another page or category may well be using
            // it. Deleting the file is a separate, deliberate act in the
            // editor's image panel.
            onClick={() => onChange("", null)}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={uploading || !projectSlug}
        onClick={() => inputRef.current?.click()}
      >
        <ImagePlus className="h-3.5 w-3.5" />
        {uploading ? t("admin.uploadingImage") : t("admin.coverUpload")}
      </Button>
      {/* A project has no assets/ folder until it exists in the repo, so a
          cover is something you add on the second visit to this form. Said
          out loud rather than left as a button that would 404. */}
      {!projectSlug && <span className="text-xs text-[var(--muted)]">{t("admin.coverSaveFirst")}</span>}
      <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.avif,.svg" className="hidden" onChange={onPick} />
    </div>
  );
}

/** Create OR edit, one form -- `project` null is "new". Both write the same
 *  `_project.yml`, and having two forms would mean two places for the cover
 *  (and the next field after it) to be forgotten in. */
export function ProjectForm({ project, onDone }: { project: Project | null; onDone: (slug?: string) => void }) {
  const { t } = useI18n();
  const { site } = useSite();
  const languages = site.languages;
  const [name, setName] = useState<FieldValues>(() =>
    project ? toFieldValues(project.name, project.name_i18n, languages, site.default_language) : {},
  );
  const [icon, setIcon] = useState(project?.icon ?? "");
  const [color, setColor] = useState(project?.color ?? "");
  const [description, setDescription] = useState<FieldValues>(() =>
    project ? toFieldValues(project.description, project.description_i18n, languages, site.default_language) : {},
  );
  const [image, setImage] = useState(project?.image ?? "");
  const [imageUrl, setImageUrl] = useState<string | null>(project?.image_url ?? null);
  const [isPrivate, setIsPrivate] = useState(project?.private ?? false);
  const [reviewRequired, setReviewRequired] = useState(project?.review_required ?? false);
  const [reviewEvery, setReviewEvery] = useState(String(project?.review_every_days ?? 0));
  const [fromRepo, setFromRepo] = useState(Boolean(project?.source));
  const [repo, setRepo] = useState(project?.source?.repo ?? "");
  const [branch, setBranch] = useState(project?.source?.branch ?? "main");
  const [docsPath, setDocsPath] = useState(project?.source?.path ?? "docs");
  const [acknowledged, setAcknowledged] = useState(false);
  // Whether the content repo is readable by anybody (backend
  // services/repo_exposure.py). Asked here rather than passed in: the form
  // is the one place where the answer changes what may be saved.
  const [publicRepo, setPublicRepo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .contentRepoStatus()
      .then((s) => setPublicRepo(s.exposure?.visibility === "public" ? s.exposure.remote : null))
      .catch(() => setPublicRepo(null));
  }, []);

  // Turning a project private on a public repo hides it on the website only;
  // the backend refuses that without an explicit acknowledgement.
  const needsAck = isPrivate && !project?.private && publicRepo !== null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (needsAck && !acknowledged) {
      toast.error(t("admin.publicRepoAckRequired"));
      return;
    }
    const resolvedName = fromFieldValues(name, languages, site.default_language);
    const resolvedDescription = fromFieldValues(description, languages, site.default_language);
    const data = {
      name: resolvedName.text,
      name_i18n: resolvedName.i18n,
      icon,
      color,
      image,
      description: resolvedDescription.text,
      description_i18n: resolvedDescription.i18n,
      private: isPrivate,
      acknowledge_public_repo: needsAck && acknowledged,
      review_required: reviewRequired,
      review_every_days: Math.max(0, Math.min(3650, Number.parseInt(reviewEvery, 10) || 0)),
      // Sent on every save: a save that left it out would switch a synced
      // project back to editable without anyone asking for that.
      source: fromRepo ? { repo: repo.trim(), branch: branch.trim() || "main", path: docsPath.trim() } : null,
    };
    setSaving(true);
    try {
      if (project) {
        const saved = await api.adminUpdateProject(project.id, data);
        onDone(saved.slug);
      } else {
        const created = await api.adminCreateProject(data);
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
      <LocalizedInput label={t("admin.projectName")} values={name} onChange={setName} languages={languages} required />
      <Input placeholder={t("admin.projectIcon")} value={icon} onChange={(e) => setIcon(e.target.value)} />
      <Input placeholder={t("admin.projectColor")} value={color} onChange={(e) => setColor(e.target.value)} />
      <LocalizedInput
        label={t("admin.projectDescription")}
        values={description}
        onChange={setDescription}
        languages={languages}
      />
      <CoverField
        projectSlug={project?.slug ?? ""}
        // `_project.yml` sits in the project directory itself, so the path
        // it stores is the one relative to THAT directory.
        pathOf={(asset) => asset.project_path}
        value={image}
        previewUrl={imageUrl}
        onChange={(next, url) => {
          setImage(next);
          setImageUrl(url);
        }}
      />
      <fieldset className="flex flex-col gap-1.5 rounded-md border border-[var(--border)] p-2">
        <legend className="px-1 text-xs font-medium text-[var(--muted)]">{t("admin.visibility")}</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="visibility" checked={!isPrivate} onChange={() => setIsPrivate(false)} />
          {t("admin.visibilityPublic")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="visibility" checked={isPrivate} onChange={() => setIsPrivate(true)} />
          {t("admin.visibilityPrivate")}
        </label>
        {isPrivate && <p className="text-xs text-[var(--muted)]">{t("admin.visibilityHint")}</p>}
        {isPrivate && publicRepo !== null && (
          <div className="rounded-md border border-red-400/60 bg-red-500/10 p-2 text-xs text-red-600 dark:text-red-400" role="alert">
            <p>{t("admin.publicRepoWarning").replace("{remote}", publicRepo)}</p>
            {needsAck && (
              <label className="mt-1.5 flex items-start gap-2">
                <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
                {t("admin.publicRepoAck")}
              </label>
            )}
          </div>
        )}
      </fieldset>
      <fieldset className="flex flex-col gap-1.5 rounded-md border border-[var(--border)] p-2">
        <legend className="px-1 text-xs font-medium text-[var(--muted)]">{t("review.projectLegend")}</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={reviewRequired} onChange={(e) => setReviewRequired(e.target.checked)} />
          {t("review.projectRequired")}
        </label>
        <p className="text-xs text-[var(--muted)]">{t("review.projectHint")}</p>
        <label className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          {t("reviewDue.everyLabel")}
          <Input
            type="number"
            min={0}
            max={3650}
            value={reviewEvery}
            onChange={(e) => setReviewEvery(e.target.value)}
            className="h-8 w-24"
          />
          {t("reviewDue.everyDays")}
        </label>
        <p className="text-xs text-[var(--muted)]">{t("reviewDue.everyHint")}</p>
      </fieldset>
      <fieldset className="flex flex-col gap-1.5 rounded-md border border-[var(--border)] p-2">
        <legend className="px-1 text-xs font-medium text-[var(--muted)]">{t("sync.sourceLegend")}</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="source" checked={!fromRepo} onChange={() => setFromRepo(false)} />
          {t("sync.sourceEditor")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="source" checked={fromRepo} onChange={() => setFromRepo(true)} />
          {t("sync.sourceRepo")}
        </label>
        {fromRepo && (
          <>
            <Input placeholder={t("sync.repoPlaceholder")} value={repo} onChange={(e) => setRepo(e.target.value)} />
            <div className="flex gap-2">
              <Input placeholder="main" value={branch} onChange={(e) => setBranch(e.target.value)} />
              <Input placeholder="docs" value={docsPath} onChange={(e) => setDocsPath(e.target.value)} />
            </div>
            <p className="text-xs text-[var(--muted)]">{t("sync.sourceHint")}</p>
          </>
        )}
      </fieldset>
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

export function ProjectsPanel({
  projects,
  readOnly,
  selected,
  onSelect,
  onChanged,
}: {
  projects: Project[];
  /** A read-only account: browse the projects, don't change them. (Unlike
   *  the panels below, this one has no frozen-version case -- versions are
   *  a property of a project, not of the list of them.) */
  readOnly: boolean;
  selected: Project | null;
  onSelect: (p: Project) => void;
  /** `slug` is the slug the saved project now has -- see loadProjects(). */
  onChanged: (slug?: string) => void;
}) {
  const { t } = useI18n();
  const [showForm, setShowForm] = useState(false);
  /** The project whose form is open, or null when none is. */
  const [editingId, setEditingId] = useState<number | null>(null);

  async function onDelete(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
    try {
      await api.adminDeleteProject(id);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.projects")}</h2>
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

      {showForm && (
        <ProjectForm
          project={null}
          onDone={(slug) => {
            setShowForm(false);
            if (slug) onChanged(slug);
          }}
        />
      )}

      <div className="mt-2 flex flex-col gap-1">
        {projects.map((p, i) => (
          <div key={p.id}>
            <div
              className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm ${
                selected?.id === p.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--surface-2)]"
              }`}
            >
              <button type="button" onClick={() => onSelect(p)} className="flex flex-1 items-center gap-2 text-left">
                {p.icon && <span>{p.icon}</span>}
                {p.name}
                {p.private && <PrivateBadge compact />}
              </button>
              {!readOnly && (
                <span className="hover-reveal flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={t("admin.edit")}
                    onClick={() => {
                      setShowForm(false);
                      setEditingId((current) => (current === p.id ? null : p.id));
                    }}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" disabled={i === 0} onClick={() => api.adminMoveProject(p.id, -1).then(() => onChanged())}>
                    <ArrowUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    disabled={i === projects.length - 1}
                    onClick={() => api.adminMoveProject(p.id, 1).then(() => onChanged())}
                  >
                    <ArrowDown className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(p.id)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </span>
              )}
            </div>
            {editingId === p.id && (
              // Keyed by id AND slug: a save renames the directory, so the
              // row that comes back is a different one and the form has to
              // re-seed from it rather than keep the values it was opened
              // with.
              <ProjectForm
                key={`${p.id}-${p.slug}`}
                project={p}
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
