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

/** A category as the nav endpoint returns it: `pages` holds only published
 *  ones, and is empty for a category nothing has been published in yet --
 *  the endpoint keeps such a category so the sidebar can decide what to do
 *  with it (it hides it). */
export interface NavCategory extends Category {
  pages: NavPage[];
}

export interface ProjectNav {
  project: Project;
  categories: NavCategory[];
}

export interface Page extends PageSummary {
  project_id: number;
  category_id: number;
  language: string;
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

/** `?lang=<code>` for the public endpoints, or nothing at all when the
 *  instance is single-language (lang is "" then) -- so an unprefixed
 *  install's requests stay byte-for-byte the ones it made before. */
function langQuery(lang: string | undefined, separator: "?" | "&" = "?"): string {
  return lang ? `${separator}lang=${encodeURIComponent(lang)}` : "";
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
  adminListCategories: (projectId: number) =>
    request<{ categories: Category[] }>(`/api/admin/projects/${projectId}/categories`),
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
  adminFindPage: (projectSlug: string, pageSlug: string, language: string) =>
    request<{ page: Page | null; languages: string[] }>(
      `/api/admin/projects/${encodeURIComponent(projectSlug)}/pages/by-slug/${encodeURIComponent(pageSlug)}` +
        `?language=${encodeURIComponent(language)}`,
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

  // Public
  publicGetSite: () => request<SiteBranding>("/api/public/site"),
  publicListProjects: (lang?: string) => request<{ projects: Project[] }>(`/api/public/projects${langQuery(lang)}`),
  publicGetProject: (slug: string, lang?: string) =>
    request<{ project: Project; categories: Category[] }>(`/api/public/projects/${slug}${langQuery(lang)}`),
  publicGetProjectNav: (slug: string, lang?: string) =>
    request<ProjectNav>(`/api/public/projects/${encodeURIComponent(slug)}/nav${langQuery(lang)}`),
  publicGetCategory: (projectSlug: string, categorySlug: string, lang?: string) =>
    request<{ project: Project; category: Category; pages: PageSummary[] }>(
      `/api/public/projects/${projectSlug}/categories/${categorySlug}${langQuery(lang)}`,
    ),
  publicGetPage: (projectSlug: string, pageSlug: string, lang?: string) =>
    request<{ project: Project; category: Category; page: Page & { fallback: boolean } }>(
      `/api/public/projects/${projectSlug}/pages/${pageSlug}${langQuery(lang)}`,
    ),
  search: (q: string, lang?: string) =>
    request<{ results: SearchResult[] }>(`/api/public/search?q=${encodeURIComponent(q)}${langQuery(lang, "&")}`),
};

export { ApiError };
