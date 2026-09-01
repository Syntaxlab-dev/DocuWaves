import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  EyeOff,
  GitBranch,
  ImagePlus,
  Moon,
  Plus,
  RefreshCw,
  Sun,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarkdownView } from "@/components/MarkdownView";
import {
  api,
  ApiError,
  type Asset,
  type Category,
  type ContentRepoStatus,
  type FooterLink,
  type Page,
  type PageSummary,
  type Project,
  type SiteAsset,
  type SiteBranding,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { logoForTheme, useDocumentTitle, useSite } from "@/lib/site";
import { accentVariables, applyTheme, getPreferredTheme } from "@/lib/theme";

export function AdminApp() {
  const { t, lang, setLang } = useI18n();
  const { refresh } = useAuth();
  const { site } = useSite();
  const [isDark, setIsDark] = useState(getPreferredTheme() === "dark");

  useDocumentTitle(t("nav.admin"));

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null);
  const [pages, setPages] = useState<PageSummary[]>([]);
  const [editingPageId, setEditingPageId] = useState<number | "new" | null>(null);
  const [showAccount, setShowAccount] = useState(false);
  const [showBranding, setShowBranding] = useState(false);
  const [repoStatus, setRepoStatus] = useState<ContentRepoStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  function loadRepoStatus() {
    api.contentRepoStatus().then(setRepoStatus);
  }
  useEffect(loadRepoStatus, []);

  async function onSyncNow() {
    setSyncing(true);
    try {
      await api.contentRepoSync();
      toast.success(t("admin.repoSyncDone"));
      loadRepoStatus();
      loadProjects();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t("admin.repoSyncFailed"));
    } finally {
      setSyncing(false);
    }
  }

  function loadProjects() {
    api.adminListProjects().then((r) => setProjects(r.projects));
  }
  useEffect(loadProjects, []);

  function loadCategories(projectId: number) {
    api.adminListCategories(projectId).then((r) => setCategories(r.categories));
  }
  useEffect(() => {
    if (selectedProject) loadCategories(selectedProject.id);
    else {
      setCategories([]);
      setSelectedCategory(null);
    }
  }, [selectedProject]);

  function loadPages(categoryId: number) {
    api.adminListPages(categoryId).then((r) => setPages(r.pages));
  }
  useEffect(() => {
    if (selectedCategory) loadPages(selectedCategory.id);
    else setPages([]);
  }, [selectedCategory]);

  function toggleTheme() {
    const next = isDark ? "light" : "dark";
    applyTheme(next);
    setIsDark(next === "dark");
  }

  async function onLogout() {
    await api.logout();
    await refresh();
  }

  return (
    <div className="min-h-screen">
      <header className="flex items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3">
        {logoForTheme(site, isDark) && (
          <img src={logoForTheme(site, isDark)!} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />
        )}
        <span className="text-lg font-semibold">{site.name}</span>
        <span className="text-sm text-[var(--muted)]">{t("nav.admin")}</span>
        <div className="ml-auto flex items-center gap-2">
          <Link to="/" className="text-sm text-[var(--accent)]">
            {t("nav.public")}
          </Link>
          <Button variant="ghost" size="sm" onClick={() => setShowBranding((v) => !v)}>
            {t("admin.branding")}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setShowAccount((v) => !v)}>
            {t("admin.account")}
          </Button>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="theme">
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setLang(lang === "de" ? "en" : "de")}>
            {lang === "de" ? "EN" : "DE"}
          </Button>
          <Button variant="outline" size="sm" onClick={onLogout}>
            {t("nav.logout")}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-6">
        {showAccount && <AccountCard onClose={() => setShowAccount(false)} />}
        {showBranding && <BrandingCard isDark={isDark} onClose={() => setShowBranding(false)} />}

        <RepoStatusBar status={repoStatus} syncing={syncing} onSync={onSyncNow} />

        {repoStatus && !repoStatus.configured ? (
          <Card>
            <CardHeader>
              <CardTitle>{t("admin.repoNotConfiguredTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="whitespace-pre-line text-sm text-[var(--muted)]">
              {t("admin.repoNotConfiguredBody")}
            </CardContent>
          </Card>
        ) : (
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <ProjectsPanel
            projects={projects}
            selected={selectedProject}
            onSelect={(p) => {
              setSelectedProject(p);
              setSelectedCategory(null);
              setEditingPageId(null);
            }}
            onChanged={loadProjects}
          />

          <div>
            {!selectedProject && <p className="text-[var(--muted)]">{t("admin.selectProject")}</p>}

            {selectedProject && (
              <div className="grid gap-4 md:grid-cols-[220px_1fr]">
                <CategoriesPanel
                  projectId={selectedProject.id}
                  categories={categories}
                  selected={selectedCategory}
                  onSelect={(c) => {
                    setSelectedCategory(c);
                    setEditingPageId(null);
                  }}
                  onChanged={() => loadCategories(selectedProject.id)}
                />

                <div>
                  {!selectedCategory && <p className="text-[var(--muted)]">{t("admin.selectCategory")}</p>}

                  {selectedCategory && editingPageId === null && (
                    <PagesPanel
                      pages={pages}
                      onEdit={(id) => setEditingPageId(id)}
                      onChanged={() => loadPages(selectedCategory.id)}
                    />
                  )}

                  {selectedCategory && editingPageId !== null && (
                    <PageEditor
                      pageId={editingPageId}
                      projectSlug={selectedProject.slug}
                      categoryId={selectedCategory.id}
                      categories={categories}
                      onDone={() => {
                        setEditingPageId(null);
                        loadPages(selectedCategory.id);
                      }}
                    />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}

function RepoStatusBar({
  status,
  syncing,
  onSync,
}: {
  status: ContentRepoStatus | null;
  syncing: boolean;
  onSync: () => void;
}) {
  const { t } = useI18n();
  if (!status || !status.configured) return null;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm">
      <GitBranch className="h-4 w-4 text-[var(--muted)]" />
      {status.connected ? (
        <>
          <span className={status.connected ? "text-[var(--accent)]" : ""}>{t("admin.repoConnected")}</span>
          <span className="text-[var(--muted)]">
            {status.branch} · {status.last_commit?.sha} · {status.last_commit?.message}
          </span>
        </>
      ) : (
        <span className="text-red-500">
          {t("admin.repoDisconnected")}
          {status.error ? `: ${status.error}` : ""}
        </span>
      )}
      <Button variant="outline" size="sm" className="ml-auto" onClick={onSync} disabled={syncing}>
        <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
        {t("admin.repoSyncNow")}
      </Button>
    </div>
  );
}

function AccountCard({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      toast.success(t("admin.passwordChanged"));
      setCurrentPassword("");
      setNewPassword("");
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("admin.account")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex flex-1 flex-col gap-1.5">
            <label className="text-sm font-medium">{t("admin.currentPassword")}</label>
            <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required />
          </div>
          <div className="flex flex-1 flex-col gap-1.5">
            <label className="text-sm font-medium">{t("admin.newPassword")}</label>
            <Input type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
          </div>
          <Button type="submit" disabled={submitting}>
            {t("admin.changePassword")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/** The instance's own identity: name, tagline, accent colour, logo/favicon
 *  and footer. Saving writes content/_site.yml (plus any uploaded image into
 *  content/_site/) and pushes it, exactly like every other admin write --
 *  branding is content-repo state, not a database row, so it survives a
 *  reindex and travels with the repo (see the backend's site_branding.py).
 *
 *  The whole form edits a local draft and shows it in the preview above the
 *  fields; nothing reaches the live site until Save, at which point the site
 *  context is reloaded so the surrounding admin header updates too. */
function BrandingCard({ isDark, onClose }: { isDark: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const { reload } = useSite();
  const [draft, setDraft] = useState<SiteBranding | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .adminGetSite()
      .then(setDraft)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t("common.error")));
    // t is stable for a given language and the form is a one-shot load --
    // re-running this on a language switch would throw away the user's edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function patch(changes: Partial<SiteBranding>) {
    setDraft((current) => (current ? { ...current, ...changes } : current));
  }

  async function onSave() {
    if (!draft) return;
    setSaving(true);
    try {
      // The response is the branding as it now READS BACK -- a value the
      // backend rejected (a colour that isn't a colour, a javascript: link)
      // disappears from the form here rather than sitting in it looking saved.
      const saved = await api.adminUpdateSite({
        name: draft.name,
        tagline: draft.tagline,
        logo: draft.logo,
        logo_dark: draft.logo_dark,
        favicon: draft.favicon,
        accent: draft.accent,
        footer_text: draft.footer_text,
        footer_links: draft.footer_links,
      });
      setDraft(saved);
      await reload();
      toast.success(t("admin.brandingSaved"));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("admin.branding")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-[var(--muted)]">{t("admin.brandingIntro")}</p>

        {!draft ? (
          <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>
        ) : (
          <div className="flex flex-col gap-4">
            <BrandingPreview draft={draft} isDark={isDark} />

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                {t("admin.brandingName")}
                <Input value={draft.name} onChange={(e) => patch({ name: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                {t("admin.brandingTagline")}
                <Input value={draft.tagline} onChange={(e) => patch({ tagline: e.target.value })} />
              </label>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t("admin.brandingAccent")}</span>
              <div className="flex items-center gap-2">
                {/* The picker always needs a concrete colour to sit on, so
                    it falls back to the built-in light-mode accent while
                    none is configured -- the text field next to it is what
                    actually shows whether one IS ("" = default). */}
                <input
                  type="color"
                  aria-label={t("admin.brandingAccent")}
                  value={draft.accent || "#4f6df5"}
                  onChange={(e) => patch({ accent: e.target.value })}
                  className="h-9 w-12 cursor-pointer rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1"
                />
                <Input
                  value={draft.accent}
                  onChange={(e) => patch({ accent: e.target.value })}
                  placeholder="#4f6df5"
                  className="max-w-[10rem] font-mono"
                />
                <Button variant="outline" size="sm" onClick={() => patch({ accent: "" })}>
                  {t("admin.brandingAccentReset")}
                </Button>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <BrandingImageField
                label={t("admin.brandingLogo")}
                filename={draft.logo}
                url={draft.logo_url}
                onPicked={(asset) => patch({ logo: asset.filename, logo_url: asset.url })}
                onCleared={() => patch({ logo: "", logo_url: null })}
              />
              <BrandingImageField
                label={t("admin.brandingLogoDark")}
                filename={draft.logo_dark}
                url={draft.logo_dark_url}
                onPicked={(asset) => patch({ logo_dark: asset.filename, logo_dark_url: asset.url })}
                onCleared={() => patch({ logo_dark: "", logo_dark_url: null })}
              />
              <BrandingImageField
                label={t("admin.brandingFavicon")}
                filename={draft.favicon}
                url={draft.favicon_url}
                onPicked={(asset) => patch({ favicon: asset.filename, favicon_url: asset.url })}
                onCleared={() => patch({ favicon: "", favicon_url: null })}
              />
            </div>

            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("admin.brandingFooterText")}
              <Input value={draft.footer_text} onChange={(e) => patch({ footer_text: e.target.value })} />
            </label>

            <FooterLinksEditor links={draft.footer_links} onChange={(footer_links) => patch({ footer_links })} />

            <div className="flex gap-2">
              <Button onClick={onSave} disabled={saving}>
                {t("admin.save")}
              </Button>
              <Button variant="outline" onClick={onClose}>
                {t("admin.cancel")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** The public header as the current draft would render it -- same logo/name
 *  arrangement as PublicLayout, and the accent scoped to this box through
 *  the same derivation the live site uses, so a colour can be judged before
 *  it is saved onto every page. */
function BrandingPreview({ draft, isDark }: { draft: SiteBranding; isDark: boolean }) {
  const { t } = useI18n();
  const logoUrl = logoForTheme(draft, isDark);
  return (
    <div>
      <span className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
        {t("admin.brandingPreview")}
      </span>
      <div
        className="mt-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)]"
        style={accentVariables(draft.accent) ?? undefined}
      >
        <div className="flex items-center gap-3 border-b border-[var(--border)] px-3 py-2.5">
          {logoUrl && <img src={logoUrl} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />}
          <span className="text-lg font-semibold">{draft.name || "DocuWaves"}</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm text-[var(--accent)]">{t("nav.public")}</span>
            <Button size="sm">{t("admin.save")}</Button>
          </div>
        </div>
        {(draft.tagline || draft.footer_text || draft.footer_links.length > 0) && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-sm text-[var(--muted)]">
            {draft.tagline && <span>{draft.tagline}</span>}
            {draft.footer_text && <span>{draft.footer_text}</span>}
            {draft.footer_links.map((link) => (
              <span key={`${link.label}-${link.url}`} className="text-[var(--accent)]">
                {link.label}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** One image slot (logo / dark logo / favicon). Uploading commits the file
 *  into content/_site/ immediately -- that's what gives it a URL to preview
 *  -- but which file the SITE uses is only decided when the form is saved. */
function BrandingImageField({
  label,
  filename,
  url,
  onPicked,
  onCleared,
}: {
  label: string;
  filename: string;
  url: string | null;
  onPicked: (asset: SiteAsset) => void;
  onCleared: () => void;
}) {
  const { t } = useI18n();
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Cleared right away so picking the SAME file again still fires change.
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      onPicked(await api.adminUploadSiteAsset(file));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-[var(--border)] p-3">
      <span className="text-sm font-medium">{label}</span>
      <div className="flex items-center gap-2">
        {url ? (
          <img src={url} alt="" className="h-8 w-8 rounded object-contain" />
        ) : (
          <span className="text-xs text-[var(--muted)]">{t("admin.brandingNoImage")}</span>
        )}
        <span className="min-w-0 flex-1 truncate text-xs text-[var(--muted)]" title={filename}>
          {filename}
        </span>
        {filename && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label={t("admin.brandingRemoveImage")}
            onClick={onCleared}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
      <Button variant="outline" size="sm" disabled={uploading} onClick={() => inputRef.current?.click()}>
        <Upload className="h-3.5 w-3.5" />
        {uploading ? t("admin.uploadingImage") : t("admin.brandingUpload")}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.gif,.webp,.avif,.svg"
        className="hidden"
        onChange={onPick}
      />
    </div>
  );
}

function FooterLinksEditor({ links, onChange }: { links: FooterLink[]; onChange: (links: FooterLink[]) => void }) {
  const { t } = useI18n();

  function update(index: number, changes: Partial<FooterLink>) {
    onChange(links.map((link, i) => (i === index ? { ...link, ...changes } : link)));
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium">{t("admin.brandingFooterLinks")}</span>
      {links.map((link, index) => (
        // Index-keyed on purpose: these rows have no id of their own and
        // their label/url are exactly what's being edited, so a value-based
        // key would remount the input on every keystroke and lose focus.
        <div key={index} className="flex items-center gap-2">
          <Input
            value={link.label}
            placeholder={t("admin.brandingLinkLabel")}
            onChange={(e) => update(index, { label: e.target.value })}
            className="max-w-[12rem]"
          />
          <Input
            value={link.url}
            placeholder={t("admin.brandingLinkUrl")}
            onChange={(e) => update(index, { url: e.target.value })}
            className="flex-1"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={t("admin.delete")}
            onClick={() => onChange(links.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => onChange([...links, { label: "", url: "" }])}
      >
        <Plus className="h-3.5 w-3.5" />
        {t("admin.brandingAddLink")}
      </Button>
    </div>
  );
}

function ProjectsPanel({
  projects,
  selected,
  onSelect,
  onChanged,
}: {
  projects: Project[];
  selected: Project | null;
  onSelect: (p: Project) => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [color, setColor] = useState("");
  const [description, setDescription] = useState("");

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    await api.adminCreateProject({ name, icon, color, description });
    setName("");
    setIcon("");
    setColor("");
    setDescription("");
    setShowForm(false);
    onChanged();
  }

  async function onDelete(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
    await api.adminDeleteProject(id);
    onChanged();
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.projects")}</h2>
        <Button variant="ghost" size="icon" onClick={() => setShowForm((v) => !v)} aria-label="add">
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {showForm && (
        <form onSubmit={onCreate} className="mt-2 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <Input placeholder={t("admin.projectName")} value={name} onChange={(e) => setName(e.target.value)} required />
          <Input placeholder={t("admin.projectIcon")} value={icon} onChange={(e) => setIcon(e.target.value)} />
          <Input placeholder={t("admin.projectColor")} value={color} onChange={(e) => setColor(e.target.value)} />
          <Input
            placeholder={t("admin.projectDescription")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Button type="submit" size="sm">
            {t("admin.save")}
          </Button>
        </form>
      )}

      <div className="mt-2 flex flex-col gap-1">
        {projects.map((p, i) => (
          <div
            key={p.id}
            className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm ${
              selected?.id === p.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--surface-2)]"
            }`}
          >
            <button type="button" onClick={() => onSelect(p)} className="flex flex-1 items-center gap-2 text-left">
              {p.icon && <span>{p.icon}</span>}
              {p.name}
            </button>
            <Button variant="ghost" size="icon" className="h-6 w-6" disabled={i === 0} onClick={() => api.adminMoveProject(p.id, -1).then(onChanged)}>
              <ArrowUp className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              disabled={i === projects.length - 1}
              onClick={() => api.adminMoveProject(p.id, 1).then(onChanged)}
            >
              <ArrowDown className="h-3 w-3" />
            </Button>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(p.id)}>
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function CategoriesPanel({
  projectId,
  categories,
  selected,
  onSelect,
  onChanged,
}: {
  projectId: number;
  categories: Category[];
  selected: Category | null;
  onSelect: (c: Category) => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    await api.adminCreateCategory(projectId, { name, icon });
    setName("");
    setIcon("");
    setShowForm(false);
    onChanged();
  }

  async function onDelete(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
    await api.adminDeleteCategory(id);
    onChanged();
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.categories")}</h2>
        <Button variant="ghost" size="icon" onClick={() => setShowForm((v) => !v)} aria-label="add">
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {showForm && (
        <form onSubmit={onCreate} className="mt-2 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <Input placeholder={t("admin.categoryName")} value={name} onChange={(e) => setName(e.target.value)} required />
          <Input placeholder={t("admin.categoryIcon")} value={icon} onChange={(e) => setIcon(e.target.value)} />
          <Button type="submit" size="sm">
            {t("admin.save")}
          </Button>
        </form>
      )}

      <div className="mt-2 flex flex-col gap-1">
        {categories.map((c, i) => (
          <div
            key={c.id}
            className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm ${
              selected?.id === c.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--surface-2)]"
            }`}
          >
            <button type="button" onClick={() => onSelect(c)} className="flex flex-1 items-center gap-2 text-left">
              {c.icon && <span>{c.icon}</span>}
              {c.name}
            </button>
            <Button variant="ghost" size="icon" className="h-6 w-6" disabled={i === 0} onClick={() => api.adminMoveCategory(c.id, -1).then(onChanged)}>
              <ArrowUp className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              disabled={i === categories.length - 1}
              onClick={() => api.adminMoveCategory(c.id, 1).then(onChanged)}
            >
              <ArrowDown className="h-3 w-3" />
            </Button>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(c.id)}>
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function PagesPanel({
  pages,
  onEdit,
  onChanged,
}: {
  pages: Page[] | PageSummary[];
  onEdit: (id: number | "new") => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();

  async function onDelete(id: number) {
    if (!confirm(t("admin.deleteConfirm"))) return;
    await api.adminDeletePage(id);
    onChanged();
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.pages")}</h2>
        <Button variant="outline" size="sm" onClick={() => onEdit("new")}>
          <Plus className="h-3.5 w-3.5" />
          {t("admin.newPage")}
        </Button>
      </div>
      <div className="mt-2 flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
        {pages.map((p) => (
          <div key={p.id} className="flex items-center gap-2 px-3 py-2 text-sm">
            <button type="button" onClick={() => onEdit(p.id)} className="flex-1 text-left">
              {p.title}
            </button>
            {"published" in p && (
              <span className={`text-xs ${p.published ? "text-[var(--accent)]" : "text-[var(--muted)]"}`}>
                {p.published ? t("admin.published") : t("admin.draft")}
              </span>
            )}
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(p.id)}>
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function PageEditor({
  pageId,
  projectSlug,
  categoryId,
  categories,
  onDone,
}: {
  pageId: number | "new";
  projectSlug: string;
  categoryId: number;
  categories: Category[];
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [targetCategoryId, setTargetCategoryId] = useState(categoryId);
  const [published, setPublished] = useState(false);
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [saving, setSaving] = useState(false);
  const [loadedId, setLoadedId] = useState<number | null>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  // The page's own category, not the one it was opened from: the dropdown
  // above can move it, and a `../assets/x.png` in the body has to resolve
  // against wherever the page will actually be saved.
  const targetCategorySlug = categories.find((c) => c.id === targetCategoryId)?.slug;

  useEffect(() => {
    if (pageId === "new") {
      setTitle("");
      setContent("");
      setTargetCategoryId(categoryId);
      setPublished(false);
      setLoadedId(null);
    } else {
      api.adminGetPage(pageId).then((p) => {
        setTitle(p.title);
        setContent(p.markdown_content);
        setTargetCategoryId(p.category_id);
        setPublished(p.published);
        setLoadedId(p.id);
      });
    }
  }, [pageId, categoryId]);

  async function onSave() {
    setSaving(true);
    try {
      if (loadedId === null) {
        const created = await api.adminCreatePage({ title, markdown_content: content, category_id: targetCategoryId });
        await api.adminPublishPage(created.id, published);
        setLoadedId(created.id);
      } else {
        await api.adminUpdatePage(loadedId, { title, markdown_content: content, category_id: targetCategoryId });
        await api.adminPublishPage(loadedId, published);
      }
      toast.success(t("admin.save"));
      onDone();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  function insertSnippet(snippet: string) {
    // Always land back on the Markdown tab first -- the textarea isn't
    // mounted while the preview is showing, so there'd be no cursor to
    // insert at and the snippet would silently go to the very end.
    setTab("edit");
    const el = editorRef.current;
    if (!el) {
      setContent((current) => current + snippet);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    setContent(content.slice(0, start) + snippet + content.slice(end));
    // After React has re-rendered with the new value, or setting the
    // caret would immediately be overwritten by the controlled update.
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + snippet.length, start + snippet.length);
    });
  }

  return (
    <div>
      <div className="flex items-center gap-2">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("admin.pageTitle")} className="flex-1 text-base font-medium" />
        <select
          value={targetCategoryId}
          onChange={(e) => setTargetCategoryId(Number(e.target.value))}
          className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
        >
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <Button variant="outline" size="icon" onClick={() => setPublished((v) => !v)} title={published ? t("admin.published") : t("admin.draft")}>
          {published ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        </Button>
      </div>

      <div className="mt-3 flex gap-1 border-b border-[var(--border)]">
        <button
          type="button"
          onClick={() => setTab("edit")}
          className={`px-3 py-1.5 text-sm ${tab === "edit" ? "border-b-2 border-[var(--accent)] font-medium" : "text-[var(--muted)]"}`}
        >
          {t("admin.editorTab")}
        </button>
        <button
          type="button"
          onClick={() => setTab("preview")}
          className={`px-3 py-1.5 text-sm ${tab === "preview" ? "border-b-2 border-[var(--accent)] font-medium" : "text-[var(--muted)]"}`}
        >
          {t("admin.previewTab")}
        </button>
      </div>

      <ImagesPanel
        projectSlug={projectSlug}
        onInsert={(asset) => insertSnippet(`![](${asset.markdown_path})`)}
      />

      <div className="mt-3">
        {tab === "edit" ? (
          <Textarea
            ref={editorRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-[420px] font-mono"
          />
        ) : (
          <div className="min-h-[420px] rounded-lg border border-[var(--border)] p-4">
            <MarkdownView content={content} projectSlug={projectSlug} categorySlug={targetCategorySlug} />
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <Button onClick={onSave} disabled={saving || !title.trim()}>
          {t("admin.save")}
        </Button>
        <Button variant="outline" onClick={onDone}>
          {t("admin.cancel")}
        </Button>
      </div>
    </div>
  );
}

/** Upload button + the project's existing images, so re-using one on a
 *  second page is a click rather than another upload of the same file. An
 *  image belongs to the PROJECT, not to the page being edited -- that's the
 *  on-disk convention (content/<project>/assets/), and it's what makes the
 *  `../assets/x.png` a page pastes work from any of its categories. */
function ImagesPanel({ projectSlug, onInsert }: { projectSlug: string; onInsert: (asset: Asset) => void }) {
  const { t } = useI18n();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function loadAssets() {
    api
      .adminListAssets(projectSlug)
      .then((r) => setAssets(r.assets))
      .catch(() => setAssets([]));
  }
  useEffect(loadAssets, [projectSlug]);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Cleared right away so picking the SAME file again still fires change.
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const asset = await api.adminUploadAsset(projectSlug, file);
      onInsert(asset);
      toast.success(t("admin.imageUploaded"));
      loadAssets();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(filename: string) {
    if (!confirm(t("admin.imageDeleteConfirm"))) return;
    try {
      await api.adminDeleteAsset(projectSlug, filename);
      loadAssets();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-[var(--border)] p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.images")}</h3>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          <ImagePlus className="h-3.5 w-3.5" />
          {uploading ? t("admin.uploadingImage") : t("admin.insertImage")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.webp,.avif,.svg"
          className="hidden"
          onChange={onPick}
        />
      </div>

      {assets.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--muted)]">{t("admin.imagesEmpty")}</p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {assets.map((a) => (
            <div
              key={a.filename}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1.5 text-xs"
            >
              <img src={a.url} alt="" className="h-8 w-8 rounded object-cover" loading="lazy" decoding="async" />
              <span className="max-w-[10rem] truncate" title={a.filename}>
                {a.filename}
              </span>
              <button type="button" className="text-[var(--accent)]" onClick={() => onInsert(a)}>
                {t("admin.imageInsert")}
              </button>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(a.filename)}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
