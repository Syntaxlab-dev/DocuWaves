/** A per-language mapping of a human-readable field, as the content repo's
 *  YAML may spell it (`name: {de: ..., en: ...}`). Empty for the plain-string
 *  form, which is every field on a single-language instance. The resolved
 *  value for the language being read always arrives in the plain field
 *  (`name`) as well, so nothing but the admin form needs to look in here. */
export type LocalizedText = Record<string, string>;

export interface Project {
  id: number;
  name: string;
  name_i18n: LocalizedText;
  slug: string;
  icon: string;
  color: string;
  description: string;
  description_i18n: LocalizedText;
  sort_order: number;
}

export interface Category {
  id: number;
  project_id: number;
  name: string;
  name_i18n: LocalizedText;
  slug: string;
  icon: string;
  sort_order: number;
  page_count?: number;
  /** Which documentation version this category belongs to -- "" for a
   *  project that has none, "current" or a frozen id once it has. */
  version: string;
}

export interface PageSummary {
  id: number;
  title: string;
  slug: string;
  /** Which language this entry actually IS, and whether that is the one the
   *  reader asked for -- false everywhere on a single-language instance.
   *  A `fallback` entry is a page that exists only in the site's default
   *  language; it is listed (it is readable) and marked, never hidden. */
  language?: string;
  fallback?: boolean;
}

export interface NavPage extends PageSummary {
  sort_order: number;
}

/** One frozen documentation version of a project, as _versions.yml records
 *  it. The working version is not in this list: it always exists, and its
 *  name comes from `current_label`. */
export interface FrozenVersion {
  id: string;
  label: string;
  released: string;
}

/** The version dimension of whatever is being read, or null for a project
 *  that has no `_versions.yml` at all -- which is what tells the UI there is
 *  no switcher, no banner and no version segment in this project's URLs. */
export interface VersionInfo {
  current_id: string;
  current_label: string;
  /** The version an UNPREFIXED URL shows -- so its links never carry a
   *  version segment, and every link shared before this project was
   *  versioned still points at it. */
  default: string;
  selected: string;
  is_frozen: boolean;
  frozen: FrozenVersion[];
  /** Which versions the thing being read (this page's slug, this category's
   *  slug) exists in, or null for "all of them". The switcher stays on the
   *  same page for a version in this list and falls back to that version's
   *  home for one that isn't -- rather than finding out by 404. */
  available: string[] | null;
}

/** A category as the nav endpoint returns it: `pages` holds only published
 *  ones, and is empty for a category nothing has been published in yet --
 *  the endpoint keeps such a category so the sidebar can decide what to do
 *  with it (it hides it). */
export interface NavCategory extends Category {
  pages: NavPage[];
  /** Which documentation versions this category slug exists in. Present
   *  only for a versioned project -- it is what lets the version switcher
   *  stay on this category when the target version has it, and fall back to
   *  that version's home when it doesn't. */
  available_versions?: string[];
}

export interface ProjectNav {
  project: Project;
  categories: NavCategory[];
  versions: VersionInfo | null;
}

export interface Page extends PageSummary {
  project_id: number;
  category_id: number;
  language: string;
  /** The documentation version this page IS -- also the directory name its
   *  file sits in, which is what a `../assets/x.png` in its Markdown has to
   *  be resolved against. */
  version: string;
  markdown_content: string;
  sort_order: number;
  published: boolean;
  created_at: string;
  updated_at: string;
}

/** What the admin editor loads: one language's page, plus every language
 *  this page exists in at all -- the tab strip needs the missing ones as
 *  much as the present ones. */
export interface AdminPage extends Page {
  languages: string[];
}

/** A project's versions as the admin panel needs them. `versioned` false is
 *  a project that has never frozen one: its content sits directly in the
 *  project directory, it has no version in its URLs, and `would_move` is
 *  what a first freeze would move into current/. */
export interface AdminVersions {
  versioned: boolean;
  current_id: string;
  current_label: string;
  default: string;
  /** The version the editor writes to: "" while unversioned, else "current". */
  writable: string;
  versions: FrozenVersion[];
  would_move: string[];
}

export interface SearchResult {
  page_id: number;
  title: string;
  page_slug: string;
  snippet: string;
  project_name: string;
  project_slug: string;
  category_name: string;
  category_slug: string;
  language: string;
  /** The hit is in the site's default language because this page has no
   *  translation into the language searched in. */
  fallback: boolean;
  /** Which documentation version the hit is in -- always the one being read
   *  when the search was scoped to a version, each project's default
   *  otherwise. */
  version: string;
}

export interface AuthStatus {
  setup_required: boolean;
  authenticated: boolean;
  username: string | null;
}

export interface OidcStatus {
  enabled: boolean;
  provider_name: string;
}

export interface Asset {
  filename: string;
  size: number;
  /** The relative path to paste into a page, e.g. `../assets/shot.png`. */
  markdown_path: string;
  /** The same file as the public endpoint serves it -- for previewing. */
  url: string;
}

export interface FooterLink {
  label: string;
  url: string;
}

/** This instance's branding, resolved from content/_site.yml in the content
 *  repo (not from the database -- see the backend's site_branding.py). Every
 *  field always arrives filled in: `accent` is "" when none is configured
 *  (meaning "keep the built-in one, which differs per colour scheme"), and a
 *  `*_url` is null whenever the configured file doesn't resolve to a real
 *  allowed image, so the UI falls back instead of showing a broken one. */
export interface SiteBranding {
  /** The CONTENT languages this instance is configured for, in order, the
   *  first being the default. Empty = single-language: no URL prefix, no
   *  switcher, no per-language fields anywhere in the admin UI. This is not
   *  the interface language (see lib/i18n.tsx), which is a separate thing a
   *  reader picks for themselves. */
  languages: string[];
  default_language: string;
  name: string;
  name_i18n: LocalizedText;
  tagline: string;
  tagline_i18n: LocalizedText;
  footer_text_i18n: LocalizedText;
  logo: string;
  logo_url: string | null;
  logo_dark: string;
  logo_dark_url: string | null;
  favicon: string;
  favicon_url: string | null;
  accent: string;
  footer_text: string;
  footer_links: FooterLink[];
}

export interface SiteAsset {
  filename: string;
  size: number;
  url: string;
}

export interface ContentRepoStatus {
  configured: boolean;
  connected: boolean;
  branch: string | null;
  last_commit: { sha: string; message: string; date: string } | null;
  error: string | null;
}

/** The admin forms' write shapes. `*_i18n` is sent only by a multilingual
 *  instance (the backend drops anything else), so a single-language install
 *  posts exactly the body it always posted. */
export interface ProjectInput {
  name: string;
  icon: string;
  color: string;
  description: string;
  name_i18n?: LocalizedText;
  description_i18n?: LocalizedText;
}

export interface CategoryInput {
  name: string;
  icon: string;
  name_i18n?: LocalizedText;
}

export interface PageInput {
  title: string;
  markdown_content: string;
  category_id: number;
  /** Which language is being written. Omitted = the site's default. */
  language?: string;
  /** Set only when creating a TRANSLATION: the existing page's slug, which
   *  its translations share. Omitted = a new page, slug from the title. */
  slug?: string;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Same error handling as request(), but sends the File's raw bytes as the
 *  body -- the upload endpoint takes the image that way (and the filename as
 *  a query parameter) rather than as a multipart form, so no Content-Type
 *  header of our own here: whatever the browser puts on it is ignored
 *  server-side and the bytes are validated instead. */
async function upload<T>(path: string, file: File): Promise<T> {
  const res = await fetch(path, { method: "POST", body: file });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

/** `?lang=<code>&version=<id>` for the public endpoints, or nothing at all
 *  when the instance is single-language and the project unversioned (both
 *  are "" then) -- so an unprefixed, unversioned install's requests stay
 *  byte-for-byte the ones it made before. */
function contentQuery(lang?: string, version?: string): string {
  const parts: string[] = [];
  if (lang) parts.push(`lang=${encodeURIComponent(lang)}`);
  if (version) parts.push(`version=${encodeURIComponent(version)}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const api = {
  // Auth
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  setup: (username: string, password: string) =>
    request("/api/auth/setup", { method: "POST", body: JSON.stringify({ username, password }) }),
  login: (username: string, password: string) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  oidcStatus: () => request<OidcStatus>("/api/auth/oidc/status"),

  // Admin: content repo
  contentRepoStatus: () => request<ContentRepoStatus>("/api/admin/content-repo/status"),
  contentRepoSync: () => request("/api/admin/content-repo/sync", { method: "POST" }),

  // Admin: projects
  adminListProjects: () => request<{ projects: Project[] }>("/api/admin/projects"),
  adminCreateProject: (data: ProjectInput) =>
    request<{ id: number; slug: string }>("/api/admin/projects", { method: "POST", body: JSON.stringify(data) }),
  adminUpdateProject: (id: number, data: ProjectInput) =>
    request(`/api/admin/projects/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminMoveProject: (id: number, direction: -1 | 1) =>
    request(`/api/admin/projects/${id}/move?direction=${direction}`, { method: "POST" }),
  adminDeleteProject: (id: number) => request(`/api/admin/projects/${id}`, { method: "DELETE" }),

  // Admin: categories
  adminListCategories: (projectId: number, version?: string) =>
    request<{ categories: Category[] }>(
      `/api/admin/projects/${projectId}/categories${version ? `?version=${encodeURIComponent(version)}` : ""}`,
    ),
  adminCreateCategory: (projectId: number, data: CategoryInput) =>
    request<{ id: number; slug: string }>(`/api/admin/projects/${projectId}/categories`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  adminUpdateCategory: (id: number, data: CategoryInput) =>
    request(`/api/admin/categories/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminMoveCategory: (id: number, direction: -1 | 1) =>
    request(`/api/admin/categories/${id}/move?direction=${direction}`, { method: "POST" }),
  adminDeleteCategory: (id: number) => request(`/api/admin/categories/${id}`, { method: "DELETE" }),

  // Admin: pages
  adminListPages: (categoryId: number) => request<{ pages: Page[] }>(`/api/admin/categories/${categoryId}/pages`),
  adminGetPage: (id: number) => request<AdminPage>(`/api/admin/pages/${id}`),
  /** By slug + language, for the editor's language tabs: `page` is null for
   *  a language this page has no version in yet (a tab to create, not an
   *  error), and `languages` is every language it does exist in. */
  adminFindPage: (projectSlug: string, pageSlug: string, language: string, version?: string) =>
    request<{ page: Page | null; languages: string[]; frozen: boolean }>(
      `/api/admin/projects/${encodeURIComponent(projectSlug)}/pages/by-slug/${encodeURIComponent(pageSlug)}` +
        `?language=${encodeURIComponent(language)}${version ? `&version=${encodeURIComponent(version)}` : ""}`,
    ),
  adminCreatePage: (data: PageInput) =>
    request<{ id: number; slug: string; language: string }>("/api/admin/pages", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  adminUpdatePage: (id: number, data: PageInput) =>
    request(`/api/admin/pages/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminPublishPage: (id: number, published: boolean) =>
    request(`/api/admin/pages/${id}/publish?published=${published}`, { method: "POST" }),
  adminMovePage: (id: number, direction: -1 | 1) =>
    request(`/api/admin/pages/${id}/move?direction=${direction}`, { method: "POST" }),
  adminDeletePage: (id: number) => request(`/api/admin/pages/${id}`, { method: "DELETE" }),

  // Admin: image assets -- keyed by project slug, not id (an asset is a
  // plain file in the project's directory, it has no database row)
  adminListAssets: (projectSlug: string) =>
    request<{ assets: Asset[] }>(`/api/admin/projects/${encodeURIComponent(projectSlug)}/assets`),
  adminUploadAsset: (projectSlug: string, file: File) =>
    upload<Asset>(
      `/api/admin/projects/${encodeURIComponent(projectSlug)}/assets?filename=${encodeURIComponent(file.name)}`,
      file,
    ),
  adminDeleteAsset: (projectSlug: string, filename: string) =>
    request(`/api/admin/projects/${encodeURIComponent(projectSlug)}/assets/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),

  // Admin: site branding -- instance-level, not keyed by anything
  adminGetSite: () => request<SiteBranding>("/api/admin/site"),
  adminUpdateSite: (data: {
    name: string;
    name_i18n: LocalizedText;
    tagline: string;
    tagline_i18n: LocalizedText;
    logo: string;
    logo_dark: string;
    favicon: string;
    accent: string;
    footer_text: string;
    footer_text_i18n: LocalizedText;
    footer_links: FooterLink[];
  }) => request<SiteBranding>("/api/admin/site", { method: "PUT", body: JSON.stringify(data) }),
  adminUploadSiteAsset: (file: File) =>
    upload<SiteAsset>(`/api/admin/site/assets?filename=${encodeURIComponent(file.name)}`, file),

  // Admin: documentation versions -- keyed by project slug, like assets: a
  // version is a directory in the content repo, it has no database row.
  adminListVersions: (projectSlug: string) =>
    request<AdminVersions>(`/api/admin/projects/${encodeURIComponent(projectSlug)}/versions`),
  adminFreezeVersion: (projectSlug: string, id: string, label: string) =>
    request<AdminVersions & { id: string; label: string; first_freeze: boolean }>(
      `/api/admin/projects/${encodeURIComponent(projectSlug)}/versions`,
      { method: "POST", body: JSON.stringify({ id, label }) },
    ),
  adminDeleteVersion: (projectSlug: string, versionId: string) =>
    request<AdminVersions>(
      `/api/admin/projects/${encodeURIComponent(projectSlug)}/versions/${encodeURIComponent(versionId)}`,
      { method: "DELETE" },
    ),

  // Public
  publicGetSite: () => request<SiteBranding>("/api/public/site"),
  publicListProjects: (lang?: string) => request<{ projects: Project[] }>(`/api/public/projects${contentQuery(lang)}`),
  publicGetProject: (slug: string, lang?: string, version?: string) =>
    request<{ project: Project; categories: Category[]; versions: VersionInfo | null }>(
      `/api/public/projects/${slug}${contentQuery(lang, version)}`,
    ),
  publicGetProjectNav: (slug: string, lang?: string, version?: string) =>
    request<ProjectNav>(`/api/public/projects/${encodeURIComponent(slug)}/nav${contentQuery(lang, version)}`),
  publicGetCategory: (projectSlug: string, categorySlug: string, lang?: string, version?: string) =>
    request<{ project: Project; category: Category; pages: PageSummary[]; versions: VersionInfo | null }>(
      `/api/public/projects/${projectSlug}/categories/${categorySlug}${contentQuery(lang, version)}`,
    ),
  publicGetPage: (projectSlug: string, pageSlug: string, lang?: string, version?: string) =>
    request<{
      project: Project;
      category: Category;
      page: Page & { fallback: boolean };
      versions: VersionInfo | null;
    }>(`/api/public/projects/${projectSlug}/pages/${pageSlug}${contentQuery(lang, version)}`),
  /** `project`+`version` scope the search to the docs the reader is standing
   *  in; without them it covers each project's default version. */
  search: (q: string, lang?: string, project?: string, version?: string) => {
    const scope = project ? `&project=${encodeURIComponent(project)}` : "";
    return request<{ results: SearchResult[] }>(
      `/api/public/search?q=${encodeURIComponent(q)}${contentQuery(lang, version).replace("?", "&")}${scope}`,
    );
  },
};

export { ApiError };
