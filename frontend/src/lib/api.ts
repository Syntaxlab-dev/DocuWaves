export interface Project {
  id: number;
  name: string;
  slug: string;
  icon: string;
  color: string;
  description: string;
  sort_order: number;
}

export interface Category {
  id: number;
  project_id: number;
  name: string;
  slug: string;
  icon: string;
  sort_order: number;
  page_count?: number;
}

export interface PageSummary {
  id: number;
  title: string;
  slug: string;
}

export interface Page extends PageSummary {
  project_id: number;
  category_id: number;
  markdown_content: string;
  sort_order: number;
  published: boolean;
  created_at: string;
  updated_at: string;
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

  // Admin: projects
  adminListProjects: () => request<{ projects: Project[] }>("/api/admin/projects"),
  adminCreateProject: (data: { name: string; icon: string; color: string; description: string }) =>
    request<{ id: number; slug: string }>("/api/admin/projects", { method: "POST", body: JSON.stringify(data) }),
  adminUpdateProject: (id: number, data: { name: string; icon: string; color: string; description: string }) =>
    request(`/api/admin/projects/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminMoveProject: (id: number, direction: -1 | 1) =>
    request(`/api/admin/projects/${id}/move?direction=${direction}`, { method: "POST" }),
  adminDeleteProject: (id: number) => request(`/api/admin/projects/${id}`, { method: "DELETE" }),

  // Admin: categories
  adminListCategories: (projectId: number) =>
    request<{ categories: Category[] }>(`/api/admin/projects/${projectId}/categories`),
  adminCreateCategory: (projectId: number, data: { name: string; icon: string }) =>
    request<{ id: number; slug: string }>(`/api/admin/projects/${projectId}/categories`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  adminUpdateCategory: (id: number, data: { name: string; icon: string }) =>
    request(`/api/admin/categories/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminMoveCategory: (id: number, direction: -1 | 1) =>
    request(`/api/admin/categories/${id}/move?direction=${direction}`, { method: "POST" }),
  adminDeleteCategory: (id: number) => request(`/api/admin/categories/${id}`, { method: "DELETE" }),

  // Admin: pages
  adminListPages: (categoryId: number) => request<{ pages: Page[] }>(`/api/admin/categories/${categoryId}/pages`),
  adminGetPage: (id: number) => request<Page>(`/api/admin/pages/${id}`),
  adminCreatePage: (data: { title: string; markdown_content: string; category_id: number }) =>
    request<{ id: number; slug: string }>("/api/admin/pages", { method: "POST", body: JSON.stringify(data) }),
  adminUpdatePage: (id: number, data: { title: string; markdown_content: string; category_id: number }) =>
    request(`/api/admin/pages/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminPublishPage: (id: number, published: boolean) =>
    request(`/api/admin/pages/${id}/publish?published=${published}`, { method: "POST" }),
  adminMovePage: (id: number, direction: -1 | 1) =>
    request(`/api/admin/pages/${id}/move?direction=${direction}`, { method: "POST" }),
  adminDeletePage: (id: number) => request(`/api/admin/pages/${id}`, { method: "DELETE" }),

  // Public
  publicListProjects: () => request<{ projects: Project[] }>("/api/public/projects"),
  publicGetProject: (slug: string) =>
    request<{ project: Project; categories: Category[] }>(`/api/public/projects/${slug}`),
  publicGetCategory: (projectSlug: string, categorySlug: string) =>
    request<{ project: Project; category: Category; pages: PageSummary[] }>(
      `/api/public/projects/${projectSlug}/categories/${categorySlug}`,
    ),
  publicGetPage: (projectSlug: string, pageSlug: string) =>
    request<{ project: Project; category: Category; page: Page }>(
      `/api/public/projects/${projectSlug}/pages/${pageSlug}`,
    ),
  search: (q: string) => request<{ results: SearchResult[] }>(`/api/public/search?q=${encodeURIComponent(q)}`),
};

export { ApiError };
