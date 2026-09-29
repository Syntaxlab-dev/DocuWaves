/**
 * What the search results page and the quick search (Ctrl/⌘+K) share, so the
 * two can never disagree about which words are marked or where a hit leads.
 */
import type { SearchResult } from "@/lib/api";

/** The words to mark in a snippet. Mirrors prose.terms_of() on the server,
 *  which is what chose the snippet's window -- if the two disagreed, the
 *  window would be built around one set of words and highlight another. */
export function termsOf(query: string): string[] {
  const found = query.toLowerCase().match(/[\w./-]{2,}/g) || [];
  return [...new Set(found)].sort((a, b) => b.length - a.length);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&");
}

/** The snippet with the searched words marked. Rendered as elements, never
 *  as HTML: the text is author-controlled content from the repo, and the
 *  terms come straight out of the query string. */
export function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length || !text) return <>{text}</>;
  // One capturing group, so split() hands back the matches at the odd
  // indices and the text between them at the even ones.
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  return (
    <>
      {text.split(pattern).map((part, index) =>
        index % 2 === 1 ? (
          <mark key={index} className="rounded bg-[var(--accent-soft)] px-0.5 text-[var(--ink)]">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

/** A hit's address. The version segment is only ever added for a SCOPED
 *  search, where every hit is in the project and version being read -- an
 *  unscoped search returns each project's default version, whose addresses
 *  carry no segment by definition. */
export function searchResultPath(r: SearchResult, scopedProject: string, path: (p: string) => string): string {
  const segment = scopedProject && r.project_slug === scopedProject && r.version ? `/${r.version}` : "";
  return path(`/p/${r.project_slug}${segment}/pages/${r.page_slug}`);
}
