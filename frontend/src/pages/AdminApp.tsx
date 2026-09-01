import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Copy,
  Eye,
  EyeOff,
  GitBranch,
  ImagePlus,
  KeyRound,
  Moon,
  Plus,
  RefreshCw,
  Sun,
  History,
  Lock,
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
  type AdminVersions,
  type ApiToken,
  type Asset,
  type Category,
  type ContentRepoStatus,
  type FooterLink,
  type LocalizedText,
  type Page,
  type Project,
  type SiteAsset,
  type SiteBranding,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { languageName } from "@/lib/lang";
import { normalizeVersionId } from "@/lib/version";
import { logoForTheme, useDocumentTitle, useSite } from "@/lib/site";
import { accentVariables, applyTheme, getPreferredTheme } from "@/lib/theme";

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
type FieldValues = Record<string, string>;

const SINGLE = [""];

function fieldLanguages(languages: string[]): string[] {
  return languages.length > 1 ? languages : SINGLE;
}

/** Stored value (default-language text + mapping) -> what the inputs edit. */
function toFieldValues(text: string, i18n: LocalizedText, languages: string[], defaultLanguage: string): FieldValues {
  if (languages.length < 2) return { "": text };
  return Object.fromEntries(
    languages.map((code) => [code, i18n[code] ?? (code === defaultLanguage ? text : "")]),
  );
}

/** ...and back: `text` is always the DEFAULT language's, because that is
 *  what slugs are derived from and what a reader of an untranslated
 *  language falls back to. */
function fromFieldValues(
  values: FieldValues,
  languages: string[],
  defaultLanguage: string,
): { text: string; i18n: LocalizedText } {
  if (languages.length < 2) return { text: values[""] ?? "", i18n: {} };
  return { text: values[defaultLanguage] ?? "", i18n: values };
}

function LocalizedInput({
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
  const [showAccount, setShowAccount] = useState(false);
  const [showBranding, setShowBranding] = useState(false);
  const [showTokens, setShowTokens] = useState(false);
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
  // Read-only: a frozen version is a snapshot of a release. Every control
  // that writes is hidden while one is being viewed, and the API refuses
  // the write anyway (see the backend's content_versions.ensure_writable) --
  // this is the half that stops someone reaching for a button that would
  // then fail.
  const frozen = Boolean(versions && viewing && viewing !== versions.writable);

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

  function loadCategories(projectId: number, version: string) {
    api.adminListCategories(projectId, version || undefined).then((r) => setCategories(r.categories));
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
          <Button variant="ghost" size="sm" onClick={() => setShowTokens((v) => !v)}>
            {t("admin.tokens")}
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
        {showTokens && <ApiTokensCard onClose={() => setShowTokens(false)} />}

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
                />

                {showVersions && versions && (
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

                {frozen && <FrozenNotice projectSlug={selectedProject.slug} version={viewing} />}

                <div className="grid gap-4 md:grid-cols-[220px_1fr]">
                  <CategoriesPanel
                    projectId={selectedProject.id}
                    categories={categories}
                    selected={selectedCategory}
                    readOnly={frozen}
                    onSelect={(c) => {
                      setSelectedCategory(c);
                      setEditing(null);
                    }}
                    onChanged={() => loadCategories(selectedProject.id, viewing)}
                  />

                  <div>
                    {!selectedCategory && <p className="text-[var(--muted)]">{t("admin.selectCategory")}</p>}

                    {selectedCategory && editing === null && (
                      <PagesPanel
                        pages={pages}
                        readOnly={frozen}
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
                        readOnly={frozen}
                        onSaved={() => loadPages(selectedCategory.id)}
                        onDone={() => {
                          setEditing(null);
                          loadPages(selectedCategory.id);
                        }}
                      />
                    )}
                  </div>
                </div>
              </>
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

/**
 * API tokens -- the credentials an operator hands to an AI assistant so it
 * can read (and, with a write token, edit) these docs through the MCP
 * endpoint at /api/mcp.
 *
 * Two things this panel has to get across, because getting them wrong is
 * expensive in a way nothing else in the admin area is:
 *
 * 1. THE VALUE IS SHOWN ONCE. Only a SHA-256 hash is stored, so there is no
 *    "show token" button anywhere and there never will be. The reveal box
 *    below therefore states that outright, sits there until it is dismissed
 *    (rather than auto-hiding on the next render), and is the only place a
 *    token value ever appears in this UI.
 * 2. A WRITE TOKEN CHANGES THE DOCUMENTATION. Not "has elevated
 *    permissions" -- it means whoever holds it can rewrite a published
 *    page. The warning next to the scope selector says exactly that, in
 *    those words, and appears the moment "read and write" is picked rather
 *    than being a paragraph above the form nobody reads.
 */
function ApiTokensCard({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [tokens, setTokens] = useState<ApiToken[] | null>(null);
  const [name, setName] = useState("");
  const [scope, setScope] = useState("read");
  const [expiresAt, setExpiresAt] = useState("");
  const [creating, setCreating] = useState(false);
  /** The plaintext of the token just created. Held in component state and
   *  nowhere else -- closing this panel or reloading the page loses it, as
   *  it must, because the server cannot produce it again. */
  const [revealed, setRevealed] = useState<{ name: string; token: string } | null>(null);

  function load() {
    api
      .adminListTokens()
      .then((r) => setTokens(r.tokens))
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t("common.error")));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const created = await api.adminCreateToken(name.trim(), scope, expiresAt);
      setRevealed({ name: created.name, token: created.token });
      setName("");
      setExpiresAt("");
      toast.success(t("admin.tokenCreated"));
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(token: ApiToken) {
    if (!confirm(t("admin.tokenRevokeConfirm").replace("{name}", token.name))) return;
    try {
      await api.adminRevokeToken(token.id);
      toast.success(t("admin.tokenRevoked"));
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  async function onCopy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("admin.tokenCopied"));
    } catch {
      // Clipboard access needs a secure context; a LAN install served over
      // plain http has none. Say so rather than failing silently -- the
      // value is right there to select by hand.
      toast.error(t("admin.tokenCopyFailed"));
    }
  }

  const endpointUrl = `${window.location.origin}/api/mcp`;

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-[var(--ink)]">
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          {t("admin.tokens")}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-[var(--muted)]">{t("admin.tokensIntro")}</p>

        {revealed && (
          <div className="flex flex-col gap-2 rounded-lg border border-[var(--accent)] bg-[var(--accent-soft)] p-3">
            <span className="text-sm font-medium">{t("admin.tokenRevealTitle")}</span>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 font-mono text-xs">
                {revealed.token}
              </code>
              <Button variant="outline" size="sm" onClick={() => onCopy(revealed.token)}>
                <Copy className="h-3.5 w-3.5" />
                {t("admin.tokenCopy")}
              </Button>
            </div>
            <span className="text-xs text-[var(--muted)]">{t("admin.tokenRevealBody")}</span>

            <span className="mt-1 text-sm font-medium">{t("admin.tokenEndpointTitle")}</span>
            <span className="text-xs text-[var(--muted)]">{t("admin.tokenEndpointBody")}</span>
            <code className="break-all rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 font-mono text-xs">
              {endpointUrl}
              <br />
              Authorization: Bearer {revealed.token}
            </code>

            <Button variant="outline" size="sm" className="self-start" onClick={() => setRevealed(null)}>
              {t("admin.tokenRevealDone")}
            </Button>
          </div>
        )}

        {tokens === null ? (
          <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>
        ) : tokens.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">{t("admin.tokensEmpty")}</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {tokens.map((token) => (
              <TokenRow key={token.id} token={token} onRevoke={() => onRevoke(token)} />
            ))}
          </div>
        )}

        <form onSubmit={onCreate} className="flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-1 flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="token-name">
                {t("admin.tokenName")}
              </label>
              <Input id="token-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="token-scope">
                {t("admin.tokenScope")}
              </label>
              <select
                id="token-scope"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
              >
                <option value="read">{t("admin.tokenScopeRead")}</option>
                <option value="write">{t("admin.tokenScopeWrite")}</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="token-expires">
                {t("admin.tokenExpires")}
              </label>
              <Input
                id="token-expires"
                type="date"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="max-w-[11rem]"
              />
            </div>
            <Button type="submit" disabled={creating || !name.trim()}>
              {t("admin.tokenCreate")}
            </Button>
          </div>

          {/* The consequence of the choice, next to the choice. A write
              token is the one thing in this panel that can change what
              readers see, so it says so in plain words rather than leaving
              "write" to speak for itself. */}
          {scope === "write" ? (
            <p className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
              <span>{t("admin.tokenScopeWriteHint")}</span>
            </p>
          ) : (
            <p className="text-xs text-[var(--muted)]">{t("admin.tokenScopeReadHint")}</p>
          )}
          <p className="text-xs text-[var(--muted)]">{t("admin.tokenExpiresHint")}</p>
        </form>

        <Button variant="outline" className="self-start" onClick={onClose}>
          {t("admin.cancel")}
        </Button>
      </CardContent>
    </Card>
  );
}

/** One token in the list: everything a decision to revoke needs (what it is
 *  called, what it may do, whether it still works, whether anything has ever
 *  used it) and, deliberately, nothing that identifies the value. */
function TokenRow({ token, onRevoke }: { token: ApiToken; onRevoke: () => void }) {
  const { t } = useI18n();
  const write = token.scope === "write";
  // Compared as dates, matching the backend: a token expires at the END of
  // its expiry day, so today's date is still valid.
  const expired = Boolean(token.expires_at) && token.expires_at < new Date().toISOString().slice(0, 10);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
      <KeyRound className="h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
      <span className="font-medium">{token.name}</span>
      <span
        className={`rounded border px-1.5 text-xs uppercase leading-5 ${
          write ? "border-amber-500/60 text-amber-600" : "border-[var(--border)] text-[var(--muted)]"
        }`}
      >
        {write ? t("admin.tokenScopeWrite") : t("admin.tokenScopeRead")}
      </span>
      <span className={`text-xs ${expired ? "text-red-500" : "text-[var(--muted)]"}`}>
        {!token.expires_at
          ? t("admin.tokenNoExpiry")
          : expired
            ? t("admin.tokenExpired")
            : `${t("admin.tokenExpiresOn")} ${token.expires_at}`}
      </span>
      <span className="text-xs text-[var(--muted)]">
        {t("admin.tokenLastUsed")}:{" "}
        {token.last_used_at ? token.last_used_at.slice(0, 16).replace("T", " ") : t("admin.tokenNeverUsed")}
      </span>
      <span className="text-xs text-[var(--muted)]">
        {t("admin.tokenCreatedOn")} {token.created_at.slice(0, 10)}
      </span>
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onRevoke}>
        <Trash2 className="h-3.5 w-3.5" />
        {t("admin.tokenRevoke")}
      </Button>
    </div>
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
  const { t, lang: uiLang } = useI18n();
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
        name_i18n: draft.name_i18n,
        tagline: draft.tagline,
        tagline_i18n: draft.tagline_i18n,
        logo: draft.logo,
        logo_dark: draft.logo_dark,
        favicon: draft.favicon,
        accent: draft.accent,
        footer_text: draft.footer_text,
        footer_text_i18n: draft.footer_text_i18n,
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
              <BrandingTextField
                label={t("admin.brandingName")}
                draft={draft}
                field="name"
                mappingField="name_i18n"
                patch={patch}
              />
              <BrandingTextField
                label={t("admin.brandingTagline")}
                draft={draft}
                field="tagline"
                mappingField="tagline_i18n"
                patch={patch}
              />
            </div>

            {/* Read-only: `languages:` decides how every page file in the
                content repo is named and how every URL is shaped, so it is
                changed in _site.yml (by hand or by pull request) rather
                than by a button that would silently re-language a whole
                repo -- see the backend's write_branding(). */}
            <div className="flex flex-col gap-1">
              <span className="text-sm font-medium">{t("admin.brandingLanguages")}</span>
              <span className="text-sm text-[var(--muted)]">
                {draft.languages.length > 0
                  ? draft.languages.map((code) => `${code} (${languageName(code, uiLang)})`).join(" · ")
                  : t("admin.brandingLanguagesNone")}
              </span>
              <span className="text-xs text-[var(--muted)]">{t("admin.brandingLanguagesHint")}</span>
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

            <BrandingTextField
              label={t("admin.brandingFooterText")}
              draft={draft}
              field="footer_text"
              mappingField="footer_text_i18n"
              patch={patch}
            />

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

/** One of the three translatable branding texts. Exactly the plain input it
 *  has always been on a single-language instance; one input per language
 *  once `languages:` names more than one, with the default language's value
 *  kept in the plain field (which is what an unbranded/untranslated read
 *  falls back to). */
function BrandingTextField({
  label,
  draft,
  field,
  mappingField,
  patch,
}: {
  label: string;
  draft: SiteBranding;
  field: "name" | "tagline" | "footer_text";
  mappingField: "name_i18n" | "tagline_i18n" | "footer_text_i18n";
  patch: (changes: Partial<SiteBranding>) => void;
}) {
  const values = toFieldValues(draft[field], draft[mappingField], draft.languages, draft.default_language);
  return (
    <LocalizedInput
      label={label}
      values={values}
      languages={draft.languages}
      onChange={(next) => {
        const resolved = fromFieldValues(next, draft.languages, draft.default_language);
        patch({ [field]: resolved.text, [mappingField]: resolved.i18n } as Partial<SiteBranding>);
      }}
    />
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

/**
 * Documentation versions for the selected project.
 *
 * The bar is always there (an unversioned project needs a way to reach
 * "Freeze a version" too), but it only grows a version picker once the
 * project HAS frozen versions -- a picker with one option would be a
 * control that does nothing on every project that never versions anything.
 */
function VersionsBar({
  versions,
  viewing,
  onView,
  open,
  onToggle,
}: {
  versions: AdminVersions | null;
  viewing: string;
  onView: (version: string) => void;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const hasFrozen = Boolean(versions && versions.versions.length > 0);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {hasFrozen && versions && (
        <>
          <span className="text-sm text-[var(--muted)]">{t("admin.versionViewing")}</span>
          <select
            aria-label={t("admin.versionViewing")}
            value={viewing}
            onChange={(e) => onView(e.target.value)}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
          >
            <option value={versions.writable}>{t("admin.versionCurrent")}</option>
            {versions.versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </>
      )}
      <Button variant="ghost" size="sm" className={hasFrozen ? "" : "ml-auto"} onClick={onToggle}>
        <History className="h-3.5 w-3.5" />
        {t("admin.versions")}
      </Button>
      {open && <span className="sr-only">{t("admin.versionsIntro")}</span>}
    </div>
  );
}

/** Shown above every panel while a frozen version is selected, so the
 *  missing buttons below are explained rather than merely absent. */
function FrozenNotice({ projectSlug, version }: { projectSlug: string; version: string }) {
  const { t } = useI18n();
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>
        {t("admin.versionReadOnly").replace("{project}", projectSlug).replace("{version}", version)}
      </span>
    </div>
  );
}

/**
 * The version list plus the freeze form.
 *
 * Freezing spells out what it is about to do BEFORE it does it, and the
 * first freeze of a project spells out more, because that is the one that
 * moves the project's existing directories down a level. `would_move`
 * comes from the server (it lists what is actually on disk right now), so
 * the confirmation names the real folders rather than a generic promise.
 */
function VersionsCard({
  project,
  versions,
  onChanged,
}: {
  project: Project;
  versions: AdminVersions;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  // What the id will actually be on disk. Shown in the confirmation rather
  // than the raw text, so nobody agrees to "copy to V 3.0/" and gets
  // "v-3.0/" -- the backend normalizes identically and is the authority.
  const normalizedId = normalizeVersionId(id);

  async function onFreeze() {
    setBusy(true);
    try {
      await api.adminFreezeVersion(project.slug, id.trim(), label.trim());
      toast.success(t("admin.versionFrozen"));
      setId("");
      setLabel("");
      setConfirming(false);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(versionId: string, versionLabel: string) {
    const message = t("admin.versionDeleteConfirm")
      .replace("{label}", versionLabel)
      .replace("{project}", project.slug)
      .replace("{id}", versionId);
    if (!confirm(message)) return;
    try {
      await api.adminDeleteVersion(project.slug, versionId);
      toast.success(t("admin.versionDeleted"));
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("admin.versions")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-[var(--muted)]">{t("admin.versionsIntro")}</p>

        {versions.versions.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">{t("admin.versionNone")}</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {versions.versions.map((v) => (
              <div key={v.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                <Lock className="h-3.5 w-3.5 text-[var(--muted)]" aria-hidden="true" />
                <span className="font-medium">{v.label}</span>
                <span className="font-mono text-xs text-[var(--muted)]">{v.id}</span>
                {v.released && (
                  <span className="text-xs text-[var(--muted)]">
                    {t("admin.versionReleased")} {v.released}
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="ml-auto h-6 w-6"
                  aria-label={t("admin.delete")}
                  onClick={() => onDelete(v.id, v.label)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <span className="text-sm font-medium">{t("admin.versionFreeze")}</span>
          <div className="flex flex-wrap gap-2">
            <Input
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                setConfirming(false);
              }}
              placeholder={t("admin.versionId")}
              className="max-w-[16rem] font-mono"
            />
            <Input
              value={label}
              onChange={(e) => {
                setLabel(e.target.value);
                setConfirming(false);
              }}
              placeholder={t("admin.versionLabel")}
              className="max-w-[12rem]"
            />
            <Button
              variant="outline"
              disabled={!normalizedId || !label.trim() || busy}
              onClick={() => setConfirming(true)}
            >
              {t("admin.versionFreeze")}
            </Button>
          </div>

          {confirming && (
            <div className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm">
              <p className="font-medium">{t("admin.versionFreezeConfirmTitle")}</p>
              <ul className="mt-2 list-disc pl-5 text-[var(--muted)]">
                {!versions.versioned && versions.would_move.length > 0 && (
                  <li>
                    {t("admin.versionFreezeStepMove")}{" "}
                    <span className="font-mono text-[var(--ink)]">{versions.would_move.join("  ")}</span>
                  </li>
                )}
                <li>{t("admin.versionFreezeStepCopy").replace("{id}", normalizedId)}</li>
                {!versions.versioned && <li>{t("admin.versionFreezeStepAssets")}</li>}
                <li>{t("admin.versionFreezeStepCommit")}</li>
              </ul>
              <div className="mt-3 flex gap-2">
                <Button size="sm" disabled={busy} onClick={onFreeze}>
                  {t("admin.versionFreezeGo")}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
                  {t("admin.cancel")}
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
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
  const { site } = useSite();
  const languages = site.languages;
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState<FieldValues>({});
  const [icon, setIcon] = useState("");
  const [color, setColor] = useState("");
  const [description, setDescription] = useState<FieldValues>({});

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    const resolvedName = fromFieldValues(name, languages, site.default_language);
    const resolvedDescription = fromFieldValues(description, languages, site.default_language);
    await api.adminCreateProject({
      name: resolvedName.text,
      name_i18n: resolvedName.i18n,
      icon,
      color,
      description: resolvedDescription.text,
      description_i18n: resolvedDescription.i18n,
    });
    setName({});
    setIcon("");
    setColor("");
    setDescription({});
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
          <LocalizedInput label={t("admin.projectName")} values={name} onChange={setName} languages={languages} required />
          <Input placeholder={t("admin.projectIcon")} value={icon} onChange={(e) => setIcon(e.target.value)} />
          <Input placeholder={t("admin.projectColor")} value={color} onChange={(e) => setColor(e.target.value)} />
          <LocalizedInput
            label={t("admin.projectDescription")}
            values={description}
            onChange={setDescription}
            languages={languages}
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
  readOnly,
  onSelect,
  onChanged,
}: {
  projectId: number;
  categories: Category[];
  selected: Category | null;
  /** A frozen version is being viewed: browse it, don't change it. */
  readOnly: boolean;
  onSelect: (c: Category) => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const { site } = useSite();
  const languages = site.languages;
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState<FieldValues>({});
  const [icon, setIcon] = useState("");

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    const resolved = fromFieldValues(name, languages, site.default_language);
    await api.adminCreateCategory(projectId, { name: resolved.text, name_i18n: resolved.i18n, icon });
    setName({});
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
        {!readOnly && (
          <Button variant="ghost" size="icon" onClick={() => setShowForm((v) => !v)} aria-label="add">
            <Plus className="h-4 w-4" />
          </Button>
        )}
      </div>

      {showForm && !readOnly && (
        <form onSubmit={onCreate} className="mt-2 flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <LocalizedInput label={t("admin.categoryName")} values={name} onChange={setName} languages={languages} required />
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
            {!readOnly && (
              <>
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
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * What the editor was opened on. A page and one of its translations are the
 * same page, so the editor is addressed by SLUG plus language rather than
 * by the numeric id of one language's row -- "translate this page" has to
 * mean "the English version of this same slug", never "a new page called
 * whatever the English title turned out to be".
 */
type EditorTarget =
  /** A page that doesn't exist yet: no slug until it is first saved. */
  | { kind: "new" }
  /** An existing page, opened in one of the languages it exists in. */
  | { kind: "page"; slug: string; language: string }
  /** A translation that does not exist yet, of a page that does. */
  | { kind: "translation"; slug: string; language: string };

/** The language variants of one page, keyed by language code. */
interface PageGroup {
  slug: string;
  title: string;
  variants: Map<string, Page>;
}

/** One entry per page, however many languages it exists in -- the admin
 *  list endpoint returns a row per translation, and a list showing
 *  "Installation" three times would be a list of files, not of pages. */
function groupPages(pages: Page[], defaultLanguage: string): PageGroup[] {
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

function PagesPanel({
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

              {/* Which languages this page exists in, and which are still
                  missing -- one row of codes, each a link into the editor
                  on that language. A missing one is dimmed and dashed,
                  clicking it starts the translation. Nothing of this shows
                  on a single-language instance. */}
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

/**
 * One page, in one language at a time, with a tab per configured language.
 *
 * The tabs are the whole multi-language story here: a language the page
 * already exists in loads that translation, a language it doesn't exist in
 * yet opens an empty editor that will be SAVED UNDER THE SAME SLUG (see
 * PageInput.slug) -- which is what makes it a translation rather than a
 * second page that happens to say something similar. The slug itself is
 * never editable and never derived from a translated title; only the
 * default language's title steers it, on the backend.
 *
 * A single-language instance sees no tab strip at all: `languages` is empty
 * there, so the editor is exactly the one-language editor it always was.
 */
function PageEditor({
  target,
  projectSlug,
  categoryId,
  categories,
  version,
  readOnly,
  onSaved,
  onDone,
}: {
  target: EditorTarget;
  projectSlug: string;
  categoryId: number;
  categories: Category[];
  /** Which documentation version this page belongs to: "" for a project
   *  with none, "current" or a frozen id otherwise. Also the directory the
   *  preview resolves `../assets/…` against. */
  version: string;
  /** The version is frozen: the editor reads it and offers no way to save.
   *  The API refuses the write too -- this is what stops anyone reaching
   *  for a button that would only fail. */
  readOnly: boolean;
  onSaved: () => void;
  onDone: () => void;
}) {
  const { t, lang: uiLang } = useI18n();
  const { site } = useSite();
  const multilingual = site.languages.length > 1;

  const [slug, setSlug] = useState(target.kind === "new" ? "" : target.slug);
  const [language, setLanguage] = useState(target.kind === "new" ? site.default_language : target.language);
  /** Which languages this page exists in, as the backend last told us --
   *  refreshed on every load and after every save, so a translation created
   *  here immediately becomes a normal tab. */
  const [existing, setExisting] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [targetCategoryId, setTargetCategoryId] = useState(categoryId);
  const [published, setPublished] = useState(false);
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [saving, setSaving] = useState(false);
  const [loadedId, setLoadedId] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  // The page's own category, not the one it was opened from: the dropdown
  // above can move it, and a `../assets/x.png` in the body has to resolve
  // against wherever the page will actually be saved.
  const targetCategorySlug = categories.find((c) => c.id === targetCategoryId)?.slug;

  useEffect(() => {
    let current = true;
    setTab("edit");
    setDirty(false);
    if (!slug) {
      // Brand-new page: nothing to load, and no other language to offer
      // until it has been saved once and has a slug of its own.
      setTitle("");
      setContent("");
      setTargetCategoryId(categoryId);
      setPublished(false);
      setLoadedId(null);
      setExisting([]);
      return;
    }
    api.adminFindPage(projectSlug, slug, language, version || undefined).then((page) => {
      if (!current) return;
      setExisting(page.languages);
      if (page.page) {
        setTitle(page.page.title);
        setContent(page.page.markdown_content);
        setTargetCategoryId(page.page.category_id);
        setPublished(page.page.published);
        setLoadedId(page.page.id);
      } else {
        // This language has no version yet: an empty editor, but on the
        // page's own slug and in its own category.
        setTitle("");
        setContent("");
        setPublished(false);
        setLoadedId(null);
      }
    });
    return () => {
      current = false;
    };
  }, [projectSlug, slug, language, categoryId, version]);

  function switchLanguage(code: string) {
    if (code === language) return;
    // Switching tabs reloads from the server, so unsaved text would be
    // gone without a word.
    if (dirty && !confirm(t("admin.deleteConfirm"))) return;
    setLanguage(code);
  }

  async function onSave() {
    setSaving(true);
    try {
      if (loadedId === null) {
        const created = await api.adminCreatePage({
          title,
          markdown_content: content,
          category_id: targetCategoryId,
          // Both only matter on a multilingual instance; the backend reads
          // an empty language as "the default" and an empty slug as "a new
          // page, derive it from the title".
          language,
          slug: slug || undefined,
        });
        await api.adminPublishPage(created.id, published);
        setLoadedId(created.id);
        setSlug(created.slug);
        setExisting((codes) => (codes.includes(created.language) ? codes : [...codes, created.language]));
      } else {
        const saved = await api.adminUpdatePage(loadedId, {
          title,
          markdown_content: content,
          category_id: targetCategoryId,
          language,
        });
        // saved.id, not loadedId: renaming the page moved its file, and the
        // row it had is gone. Publishing under the old id 404s on a save
        // that actually worked, and silently drops the published state the
        // author just toggled.
        await api.adminPublishPage(saved.id, published);
        setLoadedId(saved.id);
      }
      setDirty(false);
      toast.success(t("admin.save"));
      // The list behind the editor is refreshed, but the editor stays open
      // on this page -- writing the other language is the very next thing
      // an author does after saving a translation.
      onSaved();
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
    setDirty(true);
    // After React has re-rendered with the new value, or setting the
    // caret would immediately be overwritten by the controlled update.
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + snippet.length, start + snippet.length);
    });
  }

  return (
    <div>
      {multilingual && (
        <div className="mb-3 flex flex-wrap items-center gap-1" aria-label={t("admin.pageLanguages")}>
          {site.languages.map((code) => {
            const exists = existing.includes(code);
            const active = code === language;
            return (
              <button
                key={code}
                type="button"
                onClick={() => switchLanguage(code)}
                disabled={!slug && !active}
                aria-current={active ? "true" : undefined}
                title={
                  !slug && !active
                    ? t("admin.saveFirstForTranslations")
                    : exists
                      ? languageName(code, uiLang)
                      : `${languageName(code, uiLang)} — ${t("admin.createTranslation")}`
                }
                className={[
                  "rounded-t border-b-2 px-3 py-1.5 text-sm",
                  active ? "border-[var(--accent)] font-medium" : "border-transparent text-[var(--muted)]",
                  // Dashed and dimmed = this translation doesn't exist yet.
                  // The same treatment the page list uses, so the two read
                  // as the same fact stated twice.
                  !exists && !active ? "opacity-60" : "",
                  !slug && !active ? "cursor-not-allowed" : "",
                ].join(" ")}
              >
                {languageName(code, uiLang)}
                {!exists && <span className="ml-1.5 text-xs">·</span>}
              </button>
            );
          })}
          <span className="ml-2 text-xs text-[var(--muted)]">
            {existing.includes(language) ? "" : t("admin.translationMissing")}
          </span>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Input
          value={title}
          disabled={readOnly}
          onChange={(e) => {
            setTitle(e.target.value);
            setDirty(true);
          }}
          placeholder={t("admin.pageTitle")}
          className="flex-1 text-base font-medium"
        />
        <select
          value={targetCategoryId}
          disabled={readOnly}
          onChange={(e) => setTargetCategoryId(Number(e.target.value))}
          className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
        >
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <Button variant="outline" size="icon" disabled={readOnly} onClick={() => setPublished((v) => !v)} title={published ? t("admin.published") : t("admin.draft")}>
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

      {/* The uploader writes into the version being EDITED, so it has no
          place on a frozen one -- and its "insert" would paste a snippet
          into a textarea that can't be saved anyway. */}
      {!readOnly && (
        <ImagesPanel
          projectSlug={projectSlug}
          onInsert={(asset) => insertSnippet(`![](${asset.markdown_path})`)}
        />
      )}

      <div className="mt-3">
        {tab === "edit" ? (
          <Textarea
            ref={editorRef}
            value={content}
            readOnly={readOnly}
            onChange={(e) => {
              setContent(e.target.value);
              setDirty(true);
            }}
            className="min-h-[420px] font-mono"
          />
        ) : (
          <div className="min-h-[420px] rounded-lg border border-[var(--border)] p-4">
            <MarkdownView
              content={content}
              title={title}
              projectSlug={projectSlug}
              categorySlug={targetCategorySlug}
              versionDir={version}
            />
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        {/* No Save at all on a frozen version, rather than one that errors:
            the notice above the panels already says why, and the way to
            correct an old page is a file edit in the content repo. */}
        {!readOnly && (
          <Button onClick={onSave} disabled={saving || !title.trim()}>
            {t("admin.save")}
          </Button>
        )}
        <Button variant="outline" onClick={onDone}>
          {readOnly ? t("common.back") : t("admin.cancel")}
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
