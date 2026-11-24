import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Project, type SearchResult, type VersionInfo } from "@/lib/api";
import { FallbackBadge } from "@/components/FallbackBadge";
import { useI18n } from "@/lib/i18n";
import { languageName, useContentLang } from "@/lib/lang";
import { useDocumentTitle } from "@/lib/site";
import { Highlighted, searchResultPath, termsOf } from "@/lib/search";

export function SearchResults() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const q = params.get("q") || "";
  // Set when the search was started from inside a documentation version
  // (see PublicLayout) -- the reader was standing in one release's docs, so
  // that is the set of pages these results come from. Absent, and the
  // search covers every project's default version, which is what a search
  // from the home page means and what an instance with no versions at all
  // always did.
  const project = params.get("project") || "";
  const version = params.get("version") || "";
  const { t, lang: uiLang } = useI18n();
  const { lang, path, languages, multilingual } = useContentLang();
  const [results, setResults] = useState<SearchResult[] | null>(null);
  // The filters' choices: every project the reader can see, and the chosen
  // project's versions (null: none chosen, or it has no versions).
  const [projects, setProjects] = useState<Project[]>([]);
  const [versions, setVersions] = useState<VersionInfo | null>(null);
  const [corrected, setCorrected] = useState<string | null>(null);
  // Highlight what was actually found, which is the corrected words when
  // there was a typo -- the typo itself appears nowhere in the results.
  const terms = useMemo(() => termsOf(corrected ?? q), [corrected, q]);

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
    setCorrected(null);
    // record: this page is a finished search, so one that finds nothing is
    // worth counting for the gaps radar (unlike search-as-you-type).
    api.search(q, lang, project || undefined, version || undefined, true).then((r) => {
      setResults(r.results);
      setCorrected(r.corrected ?? null);
    });
  }, [q, lang, project, version]);

  useEffect(() => {
    api.publicListProjects(lang).then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  }, [lang]);

  useEffect(() => {
    if (!project) {
      setVersions(null);
      return;
    }
    api
      .publicGetProject(project, lang)
      .then((r) => setVersions(r.versions))
      .catch(() => setVersions(null));
  }, [project, lang]);

  /** Changes one filter in the address, so a filtered search is a link. */
  function setFilter(changes: { project?: string; version?: string }) {
    const next = new URLSearchParams(params);
    for (const [name, value] of Object.entries(changes)) {
      if (value) next.set(name, value);
      else next.delete(name);
    }
    setParams(next);
  }

  /** Another language is another set of pages, and on a multilingual site
   *  the language is the address's prefix: the same search, under it. */
  function setLanguage(next: string) {
    const query = params.toString();
    navigate(`/${next}/search${query ? `?${query}` : ""}`);
  }

  const resultPath = (r: SearchResult) => searchResultPath(r, project, path);
  const versionChoices = versions
    ? [{ id: versions.current_id, label: versions.current_label }, ...versions.frozen.map((v) => ({ id: v.id, label: v.label }))]
    : [];
  const selectClass =
    "h-8 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm text-[var(--ink)]";


  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">{t("search.title")}</h1>
      <p className="mt-1 text-[var(--muted)]">
        {t("search.resultsFor")} "{corrected ?? q}"
      </p>
      {corrected && (
        <p className="mt-1 text-sm text-[var(--muted)]">{t("search.correctedFrom").replace("{query}", q)}</p>
      )}
      {/* The filters. Always shown when there is something to choose, so a
          scoped search finding nothing can be widened in one click -- the
          reader is the only one who can. */}
      {(projects.length > 1 || project || versionChoices.length > 1 || (multilingual && languages.length > 1)) && (
        <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label={t("search.filters")}>
          {(projects.length > 1 || project) && (
            <label className="flex items-center gap-1.5 text-sm text-[var(--muted)]">
              {t("search.project")}
              <select
                className={selectClass}
                value={project}
                onChange={(event) => setFilter({ project: event.target.value, version: "" })}
              >
                <option value="">{t("search.allProjects")}</option>
                {projects.map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name}
                  </option>
                ))}
                {project && !projects.some((p) => p.slug === project) && <option value={project}>{project}</option>}
              </select>
            </label>
          )}
          {versionChoices.length > 1 && versions && (
            <label className="flex items-center gap-1.5 text-sm text-[var(--muted)]">
              {t("search.version")}
              <select
                className={selectClass}
                value={version || versions.default}
                onChange={(event) =>
                  setFilter({ version: event.target.value === versions.default ? "" : event.target.value })
                }
              >
                {versionChoices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {multilingual && languages.length > 1 && (
            <label className="flex items-center gap-1.5 text-sm text-[var(--muted)]">
              {t("search.language")}
              <select className={selectClass} value={lang} onChange={(event) => setLanguage(event.target.value)}>
                {languages.map((code) => (
                  <option key={code} value={code}>
                    {languageName(code, uiLang)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(project || version) && (
            <button
              type="button"
              onClick={() => setFilter({ project: "", version: "" })}
              className="text-sm text-[var(--accent)] hover:underline"
            >
              {t("search.clearFilters")}
            </button>
          )}
        </div>
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
              {/* Found by what it is about rather than by the reader's
                  words: say so, or the result looks like a mistake. */}
              {r.match === "meaning" && (
                <span
                  className="ml-2 rounded-full border border-[var(--border)] px-2 py-0.5 text-xs font-normal text-[var(--muted)]"
                  title={t("search.byMeaningHint")}
                >
                  {t("search.byMeaning")}
                </span>
              )}
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
