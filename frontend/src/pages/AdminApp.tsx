import { useEffect, useRef, useState } from "react";
import { contentPath, parseContentPath } from "@/pages/admin/contentPath";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ChevronRight, Moon, Sun, Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AdminInsightsCard } from "@/components/AdminInsightsCard";
import { AdminDiagnosticsCard } from "@/components/AdminDiagnosticsCard";
import { UpdateNotice } from "@/components/UpdateNotice";
import { AdminUsersCard } from "@/components/AdminUsersCard";
import { ActivityCard } from "@/components/ActivityCard";
import { AdminLogCard } from "@/components/AdminLogCard";
import { TwoFactorCard } from "@/components/TwoFactorCard";
import { NotificationsCard } from "@/components/NotificationsCard";
import { SnippetsCard } from "@/components/SnippetsCard";
import { ReplaceCard } from "@/components/ReplaceCard";
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
import { AdminNav, panelFromPath } from "./admin/AdminNav";
import { Dashboard, type OpenTarget } from "./admin/Dashboard";

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
  /** Which category `pages` belongs to: until it matches the selected one,
   *  the list shows placeholders instead of the previous category's pages. */
  const [pagesFor, setPagesFor] = useState<number | null>(null);
  const [editing, setEditing] = useState<EditorTarget | null>(null);
  // The admin's areas (Branding, Accounts, Insights, ...): ONE at a time,
  // shown in place of the content, each at its own address under /admin/
  // (AdminNav). Closing one -- its ×, Escape -- goes back to /admin.
  const location = useLocation();
  const navigate = useNavigate();
  const panel = panelFromPath(location.pathname);
  // /admin is the dashboard, /admin/content the projects and the editor.
  // The content stays mounted (hidden) everywhere else, so an open editor
  // and its unsaved text survive a look at any other area.
  const isContent = location.pathname.replace(/\/+$/, "").startsWith("/admin/content");
  const showDashboard = panel === null && !isContent;
  const closePanel = () => navigate("/admin");
  const toContent = () => {
    if (!isContent) navigate("/admin/content");
  };
  const showAccount = panel === "account";
  const showBranding = panel === "branding";
  const showActivity = panel === "activity";
  const showLog = panel === "log";
  const showInsights = panel === "insights";
  const showTokens = panel === "tokens";
  const showDiagnostics = panel === "diagnostics";
  const showUsers = panel === "users";
  // The approval queue (services/page_review.py): its count in the nav,
  // re-read after every save so it never claims work that was just done.
  const showReviews = panel === "reviews";
  const showImport = panel === "import";
  useEffect(() => {
    if (!panel) return;
    window.scrollTo({ top: 0 });
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") navigate("/admin");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, navigate]);
  // The selection lives in the address too, so a reload, a bookmark or a
  // link sent to a colleague opens the same place:
  //   /admin/content/<project>/<category>?page=<slug>&lang=<code>
  // Read once on arrival (`restore`, consumed as the lists load), and
  // written back, replacing the history entry, whenever the selection moves.
  const restore = useRef(isContent ? parseContentPath(location.pathname, location.search) : null);
  // The selected project's documentation versions, and which one is shown
  // (explained where they are loaded, below).
  const [versions, setVersions] = useState<AdminVersions | null>(null);
  const [viewing, setViewing] = useState("");
  /** The address this component itself last wrote, so the listener below
   *  can tell its own moves from Back, Forward or a typed URL. */
  const written = useRef("");
  useEffect(() => {
    if (!isContent) return;
    if (restore.current && restore.current.project) return; // still arriving
    const target = contentPath(selectedProject?.slug, selectedCategory?.slug, editing);
    const here = location.pathname.replace(/\/+$/, "") + location.search;
    console.info("DBG write", here, "->", target, "restore", JSON.stringify(restore.current));
    if (target === here) return;
    written.current = target;
    navigate(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isContent, selectedProject, selectedCategory, editing]);

  // The address moved without the selection (Back, Forward, the nav link):
  // the selection follows it. The bare /admin/content of the nav link is the
  // exception -- it means "the content", so the current selection is kept and
  // the address completed in place.
  useEffect(() => {
    if (!isContent) return;
    const here = location.pathname.replace(/\/+$/, "") + location.search;
    const target = contentPath(selectedProject?.slug, selectedCategory?.slug, editing);
    console.info("DBG follow", here, "written", written.current, "target", target, "projects", projects.map((p) => `${p.id}:${p.slug}`).join(","), "sel", selectedProject?.id, "cats", categories.map((c) => c.slug).join(","));
    if (here === written.current || here === target || projects.length === 0) return;
    if (here === "/admin/content") {
      written.current = target;
      navigate(target, { replace: true });
      return;
    }
    const want = parseContentPath(location.pathname, location.search);
    const project = want && projects.find((p) => p.slug === want.project);
    if (!want || !project) return;
    if (project.id !== selectedProject?.id) {
      restore.current = want;
      setEditing(null);
      setSelectedCategory(null);
      setSelectedProject(project);
      return;
    }
    const category = categories.find((c) => c.slug === want.category) ?? null;
    if (want.category && !category && selectedProject && versions) {
      // Not in the list this render holds (it may be reloading): ask for it
      // again and let the answer pick the category up, as on arrival.
      restore.current = want;
      loadCategories(selectedProject.id, viewing);
      return;
    }
    setSelectedCategory(category);
    setEditing(
      category && want.page ? { kind: "page", slug: want.page, language: want.lang || site.default_language } : null,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search]);
  const [reviewCount, setReviewCount] = useState(0);
  const [reviewsKey, setReviewsKey] = useState(0);
  /** A queue entry being opened: the project, then the category, then the
   *  editor -- each waits for the list it needs to have loaded. */
  const [opening, setOpening] = useState<OpenTarget | null>(null);
  const [repoStatus, setRepoStatus] = useState<ContentRepoStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  // The selected project's documentation versions, and which one the panels
  // below are showing. `viewing` is the WRITABLE version by default -- the
  // one the editor writes to, and the project directory itself while the
  // project has no versions at all, where every panel behaves exactly as it
  // did before versions existed.
  const [showVersions, setShowVersions] = useState(false);
  const [showSnippets, setShowSnippets] = useState(false);
  const [showReplace, setShowReplace] = useState(false);
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

  /** A page opened from elsewhere (the approvals, the dashboard): its
   *  project, then its category, then the editor. */
  function openReview(entry: OpenTarget) {
    const project = projects.find((p) => p.slug === entry.project_slug);
    if (!project) return;
    toContent();
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
    toContent();
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
      const wanted = restore.current?.project;
      if (wanted) {
        const project = r.projects.find((p) => p.slug === wanted);
        if (project) {
          setSelectedProject(project);
          if (!restore.current?.category) restore.current = null;
          return;
        }
        restore.current = null;
      }
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
      const arriving = restore.current;
      if (arriving?.category) {
        restore.current = null;
        const category = r.categories.find((c) => c.slug === arriving.category);
        setSelectedCategory(category ?? null);
        if (category && arriving.page) {
          setEditing({ kind: "page", slug: arriving.page, language: arriving.lang || site.default_language });
        }
        return;
      }
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
    api.adminListPages(categoryId).then((r) => {
      setPages(r.pages);
      setPagesFor(categoryId);
    });
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
  // A new address closes the phone menu: whatever was picked is now showing.
  useEffect(() => setMenuOpen(false), [location.pathname]);
  const nav = <AdminNav isAdmin={isAdmin} canWrite={canWrite} reviewCount={reviewCount} />;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="flex items-center gap-3 px-4 py-3">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-expanded={menuOpen}
            aria-controls="admin-menu"
            aria-label={menuOpen ? t("nav.closeMenu") : t("nav.openMenu")}
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
          <Link to="/admin" className="flex min-w-0 items-center gap-3">
            {logoForTheme(site, isDark) && (
              <img src={logoForTheme(site, isDark)!} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />
            )}
            <span className="truncate text-lg font-semibold">{site.name}</span>
            <span className="hidden text-sm text-[var(--muted)] sm:inline">{t("nav.admin")}</span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <Link to="/" className="hidden text-sm text-[var(--accent)] sm:inline">
              {t("nav.public")}
            </Link>
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t(isDark ? "nav.toLightMode" : "nav.toDarkMode")}>
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <UiLanguageToggle lang={lang} onChange={setLang} />
            <Button variant="outline" size="sm" onClick={onLogout}>
              {t("nav.logout")}
            </Button>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Wide screens: the areas as a sidebar, always there. */}
        <aside className="sticky top-[57px] hidden h-[calc(100vh-57px)] w-56 shrink-0 overflow-y-auto border-r border-[var(--border)] bg-[var(--surface)] lg:block">
          {nav}
        </aside>
        {/* Narrower: the same list as a drawer over the page. */}
        {menuOpen && (
          <div className="fixed inset-0 top-[57px] z-20 lg:hidden">
            <button
              type="button"
              aria-label={t("nav.closeMenu")}
              className="absolute inset-0 bg-black/30"
              onClick={() => setMenuOpen(false)}
            />
            <div id="admin-menu" className="relative h-full w-64 overflow-y-auto border-r border-[var(--border)] bg-[var(--surface)]">
              <Link to="/" className="mx-3 mt-4 block rounded-md px-2 py-1.5 text-sm text-[var(--accent)] hover:bg-[var(--surface-2)]">
                {t("nav.public")}
              </Link>
              {nav}
            </div>
          </div>
        )}

        <main className="min-w-0 flex-1">
      <div className="mx-auto max-w-6xl px-4 py-6">
        {isAdmin && <UpdateNotice />}
        {showAccount && (
          <>
            <AccountCard onClose={closePanel} />
            <TwoFactorCard />
            <NotificationsCard />
          </>
        )}
        {showBranding && <BrandingCard isDark={isDark} onClose={closePanel} />}
        {showTokens && <ApiTokensCard projects={projects} onClose={closePanel} />}
        {showActivity && <ActivityCard onClose={closePanel} />}
        {showLog && <AdminLogCard onClose={closePanel} />}
        {showInsights && (
          <AdminInsightsCard onClose={closePanel} onCreatePage={startPageFromGap} />
        )}
        {showDiagnostics && <AdminDiagnosticsCard onClose={closePanel} />}
        {showImport && (
          <ImportCard
            projects={projects}
            onClose={closePanel}
            onImported={(slug) => {
              toContent();
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
            onClose={closePanel}
            onOpen={(entry) => {
              openReview(entry);
            }}
          />
        )}
        {showUsers && <AdminUsersCard onClose={closePanel} onSelfChanged={() => void refresh()} />}

        {/* The projects, categories and editor: hidden -- not unmounted --
            while an area is open, so an open editor and its unsaved text are
            exactly as they were when the area is closed again. */}
        {showDashboard && (
          <Dashboard projects={projects} canWrite={canWrite} reviewsKey={reviewsKey} onOpen={openReview} />
        )}

        <div hidden={!isContent}>
        {/* Said once, at the top, rather than as a disabled tooltip on every
            control that isn't there: a reader who cannot find the Save
            button should learn why from the page, not from hunting. */}
        {!canWriteHere && (
          <p className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
            {t(canWriteSomewhere ? "users.readOnlyProject" : "users.readOnlyNotice")}
          </p>
        )}

        <RepoStatusBar status={repoStatus} syncing={syncing} canSync={canWrite} onSync={onSyncNow} />

        {selectedProject && (
          <nav aria-label={t("adminNav.breadcrumb")} className="mb-4 flex flex-wrap items-center gap-1 text-sm text-[var(--muted)]">
            <button
              type="button"
              className="hover:text-[var(--ink)]"
              onClick={() => {
                setEditing(null);
                setSelectedCategory(null);
                setSelectedProject(null);
              }}
            >
              {t("adminNav.pages")}
            </button>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            {selectedCategory ? (
              <button
                type="button"
                className="hover:text-[var(--ink)]"
                onClick={() => {
                  setEditing(null);
                  setSelectedCategory(null);
                }}
              >
                {selectedProject.name}
              </button>
            ) : (
              <span aria-current="page" className="font-medium text-[var(--ink)]">{selectedProject.name}</span>
            )}
            {selectedCategory && (
              <>
                <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                {editing ? (
                  <button type="button" className="hover:text-[var(--ink)]" onClick={() => setEditing(null)}>
                    {selectedCategory.name}
                  </button>
                ) : (
                  <span aria-current="page" className="font-medium text-[var(--ink)]">{selectedCategory.name}</span>
                )}
              </>
            )}
            {selectedCategory && editing && (
              <>
                <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                <span aria-current="page" className="max-w-[20rem] truncate font-medium text-[var(--ink)]">
                  {editing.kind === "new"
                    ? t("admin.newPage")
                    : (pages.find((pg) => pg.slug === editing.slug && pg.language === editing.language) ??
                        pages.find((pg) => pg.slug === editing.slug))?.title ?? editing.slug}
                </span>
              </>
            )}
          </nav>
        )}

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
                  onToggleReplace={contentReadOnly ? undefined : () => setShowReplace((v) => !v)}
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

                {showReplace && !contentReadOnly && (
                  <ReplaceCard
                    projectId={selectedProject.id}
                    version={viewing}
                    onClose={() => setShowReplace(false)}
                    onChanged={() => {
                      if (selectedCategory) loadPages(selectedCategory.id);
                      refreshReviews();
                    }}
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
                        loading={pagesFor !== selectedCategory.id}
                        readOnly={contentReadOnly}
                        categories={categories}
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
        </main>
      </div>
    </div>
  );
}
