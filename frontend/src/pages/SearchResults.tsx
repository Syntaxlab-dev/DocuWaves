import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type SearchResult } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function SearchResults() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  const { t } = useI18n();
  const [results, setResults] = useState<SearchResult[] | null>(null);

  useEffect(() => {
    if (!q) {
      setResults([]);
      return;
    }
    setResults(null);
    api.search(q).then((r) => setResults(r.results));
  }, [q]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">{t("search.title")}</h1>
      <p className="mt-1 text-[var(--muted)]">
        {t("search.resultsFor")} "{q}"
      </p>

      {results === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {results !== null && results.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("search.empty")}</p>}

      <div className="mt-6 flex flex-col gap-3">
        {results?.map((r) => (
          <Link
            key={r.page_id}
            to={`/p/${r.project_slug}/pages/${r.page_slug}`}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 hover:bg-[var(--surface-2)]"
          >
            <div className="text-xs text-[var(--muted)]">
              {r.project_name} / {r.category_name}
            </div>
            <div className="font-medium">{r.title}</div>
            <div className="mt-1 text-sm text-[var(--muted)]">{r.snippet}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
