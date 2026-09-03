import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type SearchResult } from "@/lib/api";
import { FallbackBadge } from "@/components/FallbackBadge";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocumentTitle } from "@/lib/site";

/** The words to mark in a snippet. Mirrors prose.terms_of() on the server,
 *  which is what chose the snippet's window -- if the two disagreed, the
 *  window would be built around one set of words and highlight another. */
function termsOf(query: string): string[] {
  const found = query.toLowerCase().match(/[\w./-]{2,}/g) || [];
  return [...new Set(found)].sort((a, b) => b.length - a.length);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&");
}

/** The snippet with the searched words marked. Rendered as elements, never
 *  as HTML: the text is author-controlled content from the repo, and the
 *  terms come straight out of the query string. */
function Highlighted({ text, terms }: { text: string; terms: string[] }) {
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

export function SearchResults() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  // Set when the search was started from inside a documentation version
  // (see PublicLayout) -- the reader was standing in one release's docs, so
  // that is the set of pages these results come from. Absent, and the
  // search covers every project's default version, which is what a search
  // from the home page means and what an instance with no versions at all
  // always did.
  const project = params.get("project") || "";
  const version = params.get("version") || "";
  const { t } = useI18n();
  const { lang, path } = useContentLang();
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const terms = useMemo(() => termsOf(q), [q]);

  useDocumentTitle(t("search.title"));

  useEffect(() => {
    if (!q) {
      setResults([]);
      return;
    }
    setResults(null);
    // Searching in one language is searching one set of pages: the reader's
    // own, plus the pages that exist only in the site's default language.
    // Switching language re-runs the same query against the other set.
    api.search(q, lang, project || undefined, version || undefined).then((r) => setResults(r.results));
  }, [q, lang, project, version]);

  /** A hit's address. The version segment is only ever added for a SCOPED
   *  search, where every hit is in the project and version being read --
   *  an unscoped search returns each project's default version, whose
   *  addresses carry no segment by definition. */
  function resultPath(r: SearchResult): string {
    const segment = project && r.project_slug === project && r.version ? `/${r.version}` : "";
    return path(`/p/${r.project_slug}${segment}/pages/${r.page_slug}`);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">{t("search.title")}</h1>
      <p className="mt-1 text-[var(--muted)]">
        {t("search.resultsFor")} "{q}"
      </p>
      {/* Said out loud, because a scoped search finding nothing and a global
          one finding nothing look identical otherwise -- and the reader is
          the only one who can widen it. */}
      {project && (
        <p className="mt-1 text-sm text-[var(--muted)]">
          {t("search.scopePrefix")}
          {project}
          {version ? ` · ${version}` : ""}
        </p>
      )}

      {results === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {results !== null && results.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("search.empty")}</p>}

      <div className="mt-6 flex flex-col gap-3">
        {results?.map((r) => (
          <Link
            key={r.page_id}
            to={resultPath(r)}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 hover:bg-[var(--surface-2)]"
          >
            <div className="text-xs text-[var(--muted)]">
              {r.project_name} / {r.category_name}
            </div>
            <div className="flex items-center font-medium">
              {r.title}
              {r.fallback && <FallbackBadge language={r.language} />}
            </div>
            <div className="mt-1 text-sm text-[var(--muted)]">
              <Highlighted text={r.snippet} terms={terms} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
