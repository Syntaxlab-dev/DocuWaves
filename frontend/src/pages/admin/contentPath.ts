// The content view's selection as an address, and back:
//   /admin/content/<project>/<category>?page=<slug>&lang=<code>
// Slugs are URL-safe already; encoded anyway for hand-written ones.

export interface ContentLocation {
  project: string;
  category: string;
  page: string;
  lang: string;
}

export function contentPath(
  project?: string,
  category?: string,
  editing?: { kind: string; slug?: string; language?: string } | null,
): string {
  let path = "/admin/content";
  if (!project) return path;
  path += `/${encodeURIComponent(project)}`;
  if (!category) return path;
  path += `/${encodeURIComponent(category)}`;
  if (editing && editing.kind === "page" && editing.slug) {
    const query = new URLSearchParams({ page: editing.slug });
    if (editing.language) query.set("lang", editing.language);
    path += `?${query.toString()}`;
  }
  return path;
}

export function parseContentPath(pathname: string, search: string): ContentLocation | null {
  const rest = pathname.replace(/\/+$/, "").replace(/^\/admin\/content/, "");
  const [project = "", category = ""] = rest.split("/").filter(Boolean).map(decodeURIComponent);
  if (!project) return null;
  const query = new URLSearchParams(search);
  return { project, category, page: category ? (query.get("page") ?? "") : "", lang: query.get("lang") ?? "" };
}
