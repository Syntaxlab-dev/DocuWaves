import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Moon, Sun, Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AdminInsightsCard } from "@/components/AdminInsightsCard";
import { AdminDiagnosticsCard } from "@/components/AdminDiagnosticsCard";
import { UpdateNotice } from "@/components/UpdateNotice";
import { AdminUsersCard } from "@/components/AdminUsersCard";
import { ActivityCard } from "@/components/ActivityCard";
import { TwoFactorCard } from "@/components/TwoFactorCard";
import { NotificationsCard } from "@/components/NotificationsCard";
import { SnippetsCard } from "@/components/SnippetsCard";
import { ImportCard } from "@/components/ImportCard";
import { SyncBanner } from "@/components/SyncBanner";
import { UiLanguageToggle } from "@/components/UiLanguageToggle";
import { ReviewQueueCard } from "@/components/ReviewWorkflow";
import {
  api,
  ApiError,
  type AdminVersions,
  type Category,
  type ContentRepoStatus,
  type Page,
  type Project,
  type ReviewQueueEntry,
} from "@/lib/api";
import { useAuth, usePermissions } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { logoForTheme, useDocumentTitle, useSite } from "@/lib/site";
import { applyTheme, getPreferredTheme } from "@/lib/theme";
import { RepoStatusBar } from "./admin/RepoStatus";
import { AccountCard } from "./admin/AccountCard";
import { ApiTokensCard } from "./admin/ApiTokensCard";
import { BrandingCard } from "./admin/BrandingCard";
import { VersionsBar, FrozenNotice, VersionsCard } from "./admin/Versions";
import { ProjectsPanel } from "./admin/ProjectsPanel";
import { CategoriesPanel } from "./admin/CategoriesPanel";
import { type EditorTarget, PagesPanel } from "./admin/PagesPanel";
import { PageEditor } from "./admin/PageEditor";

type AdminPanel = "account" | "activity" | "branding" | "insights" | "tokens" | "diagnostics" | "users" | "reviews" | "import";

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
  // Every language variant as its own row (the admin list endpoint does not
  // collapse them) -- PagesPanel groups them by slug for display.
  const [pages, setPages] = useState<Page[]>([]);
  const [editing, setEditing] = useState<EditorTarget | null>(null);
  // The header's areas (Branding, Accounts, Insights, ...): ONE at a time,
  // shown in place of the projects. Opening another replaces it; its own
  // menu item, × or Escape closes it. They used to be eight independent
  // switches, and opening a few stacked them all above the projects.
  const [panel, setPanel] = useState<AdminPanel | null>(null);
  const panelSetter = (key: AdminPanel) => (value: boolean | ((open: boolean) => boolean)) =>
    setPanel((current) => {
      const open = current === key;
      const next = typeof value === "function" ? value(open) : value;
      if (next) return key;
      return open ? null : current;
    });
  const showAccount = panel === "account";
  const setShowAccount = panelSetter("account");
  const showBranding = panel === "branding";
  const setShowBranding = panelSetter("branding");
  const showActivity = panel === "activity";
  const setShowActivity = panelSetter("activity");
  const showInsights = panel === "insights";
  const setShowInsights = panelSetter("insights");
  const showTokens = panel === "tokens";
  const setShowTokens = panelSetter("tokens");
  const showDiagnostics = panel === "diagnostics";
  const setShowDiagnostics = panelSetter("diagnostics");
  const showUsers = panel === "users";
  const setShowUsers = panelSetter("users");
  // The approval queue (services/page_review.py): its count in the header,
  // re-read after every save so it never claims work that was just done.
  const showReviews = panel === "reviews";
  const setShowReviews = panelSetter("reviews");
  const showImport = panel === "import";
  const setShowImport = panelSetter("import");
  useEffect(() => {
    if (!panel) return;
    window.scrollTo({ top: 0 });
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setPanel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel]);
  const [reviewCount, setReviewCount] = useState(0);
  const [reviewsKey, setReviewsKey] = useState(0);
  /** A queue entry being opened: the project, then the category, then the
   *  editor -- each waits for the list it needs to have loaded. */
  const [opening, setOpening] = useState<ReviewQueueEntry | null>(null);
  const [repoStatus, setRepoStatus] = useState<ContentRepoStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  // The selected project's documentation versions, and which one the panels
  // below are showing. `viewing` is the WRITABLE version by default -- the
  // one the editor writes to, and the project directory itself while the
  // project has no versions at all, where every panel behaves exactly as it
  // did before versions existed.
  const [versions, setVersions] = useState<AdminVersions | null>(null);
  const [viewing, setViewing] = useState("");
  const [showVersions, setShowVersions] = useState(false);
  const [showSnippets, setShowSnippets] = useState(false);
  // Read-only: a frozen version is a snapshot of a release. Every control
  // that writes is hidden while one is being viewed, and the API refuses
  // the write anyway (see the backend's content_versions.ensure_writable) --
  // this is the half that stops someone reaching for a button that would
  // then fail.
  const frozen = Boolean(versions && viewing && viewing !== versions.writable);
  const { canWrite, isAdmin, canWriteProject, canWriteSomewhere } = usePermissions();
  // Writes inside the open project follow its permission, which can differ
  // from the account's role (permissions per project).
  const canWriteHere = canWriteProject(selectedProject?.slug);
  // A frozen version and a read-only account are the same thing to every
  // panel below: browse it, don't change it. One flag rather than two, so
  // no panel can end up honouring one and not the other.
  const readOnly = frozen || !canWriteHere;
  // Docs-as-code: the pages and categories come from a code repository and
  // are changed there (backend services/docs_sync.py). Snippets, versions
  // and images are not the sync's, so only these panels follow it.
  const synced = Boolean(selectedProject?.source);
  const contentReadOnly = readOnly || synced;

  useEffect(() => {
    api
      .adminReviewQueue()
      .then((r) => setReviewCount(r.count))
      .catch(() => setReviewCount(0));
  }, [reviewsKey]);
  const refreshReviews = () => setReviewsKey((k) => k + 1);

  function openReview(entry: ReviewQueueEntry) {
    const project = projects.find((p) => p.slug === entry.project_slug);
    if (!project) return;
    setOpening(entry);
    setEditing(null);
    if (selectedProject?.id === project.id) {
      // Same project: the categories are already there (or on their way).
      const category = categories.find((c) => c.id === entry.category_id);
      if (category) {
        setSelectedCategory(category);
        setEditing({ kind: "page", slug: entry.slug, language: entry.language });
        setOpening(null);
      }
    } else {
      setSelectedProject(project);
      setSelectedCategory(null);
    }
  }

  useEffect(() => {
    if (!opening) return;
    const category = categories.find((c) => c.id === opening.category_id);
    if (!category) return;
    setSelectedCategory(category);
    setEditing({ kind: "page", slug: opening.slug, language: opening.language });
    setOpening(null);
  }, [categories, opening]);

  /** A page started from the gaps radar: the search words become its title.
   *  The category is the author's choice -- the radar knows what readers
   *  looked for, not where it belongs -- so the editor opens once one is
   *  picked. */
  const [newPage, setNewPage] = useState<{ title: string; body?: string } | null>(null);
  function startPageFromGap(title: string, projectSlug: string, body?: string) {
    const project = projects.find((p) => p.slug === projectSlug) ?? selectedProject;
    const nice = title.charAt(0).toUpperCase() + title.slice(1);
    setShowInsights(false);
    setEditing(null);
    setSelectedCategory(null);
    if (project && project.id !== selectedProject?.id) setSelectedProject(project);
    setNewPage({ title: nice, body });
    toast.info(
      (project ? t("gaps.pickCategory") : t("gaps.pickProject")).replace("{title}", nice),
    );
  }
  useEffect(() => {
    if (newPage === null || !selectedCategory) return;
    setEditing({ kind: "new", title: newPage.title, body: newPage.body });
    setNewPage(null);
  }, [newPage, selectedCategory]);

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

  /** `selectSlug` is the slug a just-saved project now has -- passed in
   *  because editing a project's name RENAMES its directory, and the
   *  reindex that follows keys rows by slug, so the saved project comes
   *  back with a new id as well as a new slug. Without it the selection
   *  would either point at a row that no longer exists or keep addressing
   *  the old directory in every version/asset call below. Falling back to
   *  the id keeps a plain refresh (or a delete) behaving sensibly. */
  function loadProjects(selectSlug?: string) {
    api.adminListProjects().then((r) => {
      setProjects(r.projects);
      setSelectedProject((current) => {
        if (!current) return null;
        const wanted = selectSlug ?? current.slug;
        return r.projects.find((p) => p.slug === wanted) ?? r.projects.find((p) => p.id === current.id) ?? null;
      });
    });
  }
  useEffect(loadProjects, []);

  function loadCategories(projectId: number, version: string, selectSlug?: string) {
    // Same reasoning as loadProjects() above: renaming a category moves its
    // directory, so the row it had is gone and the selection has to follow
    // the new slug.
    api.adminListCategories(projectId, version || undefined).then((r) => {
      setCategories(r.categories);
      setSelectedCategory((current) => {
        if (!current) return null;
        const wanted = selectSlug ?? current.slug;
        return r.categories.find((c) => c.slug === wanted) ?? r.categories.find((c) => c.id === current.id) ?? null;
      });
    });
  }

  function loadVersions(projectSlug: string) {
    api.adminListVersions(projectSlug).then((data) => {
      setVersions(data);
      setViewing(data.writable);
    });
  }

  useEffect(() => {
    if (selectedProject) loadVersions(selectedProject.slug);
    else {
      setVersions(null);
      setViewing("");
      setShowVersions(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    // Waits for the versions response: loading categories before `viewing`
    // is known would fetch the wrong version's for one round trip.
    if (selectedProject && versions) loadCategories(selectedProject.id, viewing);
    else {
      setCategories([]);
      setSelectedCategory(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject, versions, viewing]);

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

  const [menuOpen, setMenuOpen] = useState(false);
  const reviewBadge =
    reviewCount > 0 ? (
      <span className="ml-1.5 rounded-full bg-[var(--accent)] px-1.5 text-[10px] font-semibold leading-4 text-[var(--accent-ink)]">
        {reviewCount}
      </span>
    ) : null;
  /** The header's panel toggles, in the order they are shown. Branding,
   *  accounts, tokens and diagnostics are administrator territory -- the
   *  middleware refuses the whole prefix for anyone else, so offering them
   *  would be offering four ways to get a 403. One list for both layouts,
   *  so the row and the menu can never offer different things. */
  const headerItems: { key: string; label: string; onClick: () => void; badge?: ReactNode }[] = [
    ...(isAdmin
      ? [
          { key: "branding", label: t("admin.branding"), onClick: () => setShowBranding((v) => !v) },
          { key: "users", label: t("users.title"), onClick: () => setShowUsers((v) => !v) },
        ]
      : []),
    { key: "reviews", label: t("review.queueButton"), onClick: () => setShowReviews((v) => !v), badge: reviewBadge },
    { key: "activity", label: t("activity.title"), onClick: () => setShowActivity((v) => !v) },
    { key: "insights", label: t("admin.insights"), onClick: () => setShowInsights((v) => !v) },
    ...(isAdmin
      ? [
          { key: "tokens", label: t("admin.tokens"), onClick: () => setShowTokens((v) => !v) },
          { key: "diagnostics", label: t("diag.title"), onClick: () => setShowDiagnostics((v) => !v) },
        ]
      : []),
    // Importing writes a whole project, so only for accounts that may write.
    ...(canWrite ? [{ key: "import", label: t("import.title"), onClick: () => setShowImport((v) => !v) }] : []),
    { key: "account", label: t("admin.account"), onClick: () => setShowAccount((v) => !v) },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="flex items-center gap-3 px-4 py-3">
          {logoForTheme(site, isDark) && (
            <img src={logoForTheme(site, isDark)!} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />
          )}
          <span className="truncate text-lg font-semibold">{site.name}</span>
          <span className="hidden text-sm text-[var(--muted)] sm:inline">{t("nav.admin")}</span>

          {/* Wide screens: everything in one row, as it always was. */}
          <nav className="ml-auto hidden items-center gap-2 xl:flex">
            <Link to="/" className="text-sm text-[var(--accent)]">
              {t("nav.public")}
            </Link>
            {headerItems.map((item) => (
              <Button
                key={item.key}
                variant="ghost"
                size="sm"
                onClick={item.onClick}
                aria-pressed={panel === item.key}
                className={panel === item.key ? "bg-[var(--surface-2)] text-[var(--accent)]" : undefined}
              >
                {item.label}
                {item.badge}
              </Button>
            ))}
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t(isDark ? "nav.toLightMode" : "nav.toDarkMode")}>
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <UiLanguageToggle lang={lang} onChange={setLang} />
            <Button variant="outline" size="sm" onClick={onLogout}>
              {t("nav.logout")}
            </Button>
          </nav>

          {/* Narrower: the approvals stay in reach -- they are the one thing
              in this row that can be waiting for somebody -- and everything
              else folds into a menu below the bar. Eleven controls in one
              row pushed the page sideways on a phone, and still overflowed
              on a laptop. */}
          <div className="ml-auto flex items-center gap-1 xl:hidden">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowReviews((v) => !v)}
              aria-pressed={showReviews}
              className={showReviews ? "bg-[var(--surface-2)] text-[var(--accent)]" : undefined}
            >
              {t("review.queueButton")}
              {reviewBadge}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-expanded={menuOpen}
              aria-controls="admin-menu"
              aria-label={menuOpen ? t("nav.closeMenu") : t("nav.openMenu")}
              onClick={() => setMenuOpen((v) => !v)}
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>
        </div>

        {menuOpen && (
          <nav id="admin-menu" className="border-t border-[var(--border)] px-4 py-3 xl:hidden">
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
              <Link
                to="/"
                className="rounded-md px-3 py-2 text-sm text-[var(--accent)] hover:bg-[var(--surface-2)]"
              >
                {t("nav.public")}
              </Link>
              {headerItems
                .filter((item) => item.key !== "reviews")
                .map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    aria-pressed={panel === item.key}
                    className={`rounded-md px-3 py-2 text-left text-sm hover:bg-[var(--surface-2)] ${
                      panel === item.key ? "bg-[var(--surface-2)] font-medium text-[var(--accent)]" : ""
                    }`}
                    onClick={() => {
                      item.onClick();
                      setMenuOpen(false);
                    }}
                  >
                    {item.label}
                  </button>
                ))}
            </div>
            <div className="mt-3 flex items-center gap-2 border-t border-[var(--border)] pt-3">
              <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t(isDark ? "nav.toLightMode" : "nav.toDarkMode")}>
                {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </Button>
              <UiLanguageToggle lang={lang} onChange={setLang} />
              <Button variant="outline" size="sm" className="ml-auto" onClick={onLogout}>
                {t("nav.logout")}
              </Button>
            </div>
          </nav>
        )}
      </header>

      <div className="mx-auto max-w-6xl px-4 py-6">
        {isAdmin && <UpdateNotice />}
        {showAccount && (
          <>
            <AccountCard onClose={() => setShowAccount(false)} />
            <TwoFactorCard />
            <NotificationsCard />
          </>
        )}
        {showBranding && <BrandingCard isDark={isDark} onClose={() => setShowBranding(false)} />}
        {showTokens && <ApiTokensCard projects={projects} onClose={() => setShowTokens(false)} />}
        {showActivity && <ActivityCard onClose={() => setShowActivity(false)} />}
        {showInsights && (
          <AdminInsightsCard onClose={() => setShowInsights(false)} onCreatePage={startPageFromGap} />
        )}
        {showDiagnostics && <AdminDiagnosticsCard onClose={() => setShowDiagnostics(false)} />}
        {showImport && (
          <ImportCard
            projects={projects}
            onClose={() => setShowImport(false)}
            onImported={(slug) => {
              setShowImport(false);
              setEditing(null);
              setSelectedCategory(null);
              // Straight into the imported project: its drafts are the
              // next thing to look at.
              api.adminListProjects().then((r) => {
                setProjects(r.projects);
                setSelectedProject(r.projects.find((p) => p.slug === slug) ?? null);
              });
            }}
          />
        )}
        {showReviews && (
          <ReviewQueueCard
            refreshKey={reviewsKey}
            onClose={() => setShowReviews(false)}
            onOpen={(entry) => {
              setShowReviews(false);
              openReview(entry);
            }}
          />
        )}
        {showUsers && <AdminUsersCard onClose={() => setShowUsers(false)} onSelfChanged={() => void refresh()} />}

        {/* The projects, categories and editor: hidden -- not unmounted --
            while an area is open, so an open editor and its unsaved text are
            exactly as they were when the area is closed again. */}
        <div hidden={panel !== null}>
        {/* Said once, at the top, rather than as a disabled tooltip on every
            control that isn't there: a reader who cannot find the Save
            button should learn why from the page, not from hunting. */}
        {!canWriteHere && (
          <p className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
            {t(canWriteSomewhere ? "users.readOnlyProject" : "users.readOnlyNotice")}
          </p>
        )}

        <RepoStatusBar status={repoStatus} syncing={syncing} canSync={canWrite} onSync={onSyncNow} />

        {/* No "not connected" gate any more: there is always a content
         *  repository (a local one in the data volume when no remote is
         *  configured), so the editor is always the thing to show. */}
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <ProjectsPanel
            projects={projects}
            readOnly={!canWrite}
            selected={selectedProject}
            onSelect={(p) => {
              setSelectedProject(p);
              setSelectedCategory(null);
              setEditing(null);
            }}
            onChanged={loadProjects}
          />

          <div>
            {!selectedProject && <p className="text-[var(--muted)]">{t("admin.selectProject")}</p>}

            {selectedProject && (
              <>
                <VersionsBar
                  versions={versions}
                  viewing={viewing}
                  onView={(v) => {
                    setViewing(v);
                    setSelectedCategory(null);
                    setEditing(null);
                  }}
                  open={showVersions}
                  onToggle={() => setShowVersions((v) => !v)}
                  onToggleSnippets={() => setShowSnippets((v) => !v)}
                />

                {/* Freezing a release and deleting one are both writes, so
                    the card is not offered to a read-only account. The BAR
                    above it stays: which versions exist, and which one is
                    being looked at, is reading. */}
                {showVersions && versions && canWriteHere && (
                  <VersionsCard
                    project={selectedProject}
                    versions={versions}
                    onChanged={() => {
                      loadVersions(selectedProject.slug);
                      setSelectedCategory(null);
                      setEditing(null);
                    }}
                  />
                )}

                {showSnippets && (
                  <SnippetsCard
                    projectSlug={selectedProject.slug}
                    version={viewing}
                    readOnly={readOnly}
                    onClose={() => setShowSnippets(false)}
                  />
                )}

                {frozen && <FrozenNotice projectSlug={selectedProject.slug} version={viewing} />}
                {selectedProject.source && !frozen && (
                  <SyncBanner projectSlug={selectedProject.slug} source={selectedProject.source} />
                )}

                {/* min-w-0 on the right column: a grid track is sized by its
                    content unless told otherwise, so a wide unified diff in the
                    History tab stretched this column instead of scrolling inside
                    it, and pushed the whole admin page into horizontal scroll.
                    Same failure and same fix as the public shell -- see
                    DocsShell.tsx, which already carried the comment. */}
                <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
                  <CategoriesPanel
                    projectId={selectedProject.id}
                    projectSlug={selectedProject.slug}
                    categories={categories}
                    selected={selectedCategory}
                    readOnly={contentReadOnly}
                    onSelect={(c) => {
                      setSelectedCategory(c);
                      setEditing(null);
                    }}
                    onChanged={(slug) => loadCategories(selectedProject.id, viewing, slug)}
                  />

                  <div>
                    {!selectedCategory && <p className="text-[var(--muted)]">{t("admin.selectCategory")}</p>}

                    {selectedCategory && editing === null && (
                      <PagesPanel
                        pages={pages}
                        readOnly={contentReadOnly}
                        onEdit={setEditing}
                        onChanged={() => loadPages(selectedCategory.id)}
                      />
                    )}

                    {selectedCategory && editing !== null && (
                      <PageEditor
                        target={editing}
                        projectSlug={selectedProject.slug}
                        categoryId={selectedCategory.id}
                        categories={categories}
                        version={viewing}
                        readOnly={contentReadOnly}
                        frozen={frozen || synced}
                        reviewRequired={Boolean(selectedProject.review_required)}
                        onSaved={() => {
                          loadPages(selectedCategory.id);
                          refreshReviews();
                        }}
                        onDone={() => {
                          setEditing(null);
                          loadPages(selectedCategory.id);
                          refreshReviews();
                        }}
                      />
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
        </div>
      </div>
    </div>
  );
}
