import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, FileText, Search } from "lucide-react";
import { api, type SearchResult } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { Highlighted, searchResultPath, termsOf } from "@/lib/search";

const MAX_HITS = 8;
const DEBOUNCE_MS = 180;

/**
 * Search from anywhere on the public site without leaving the page:
 * Ctrl/⌘+K (or "/" when not typing) opens a dialog that searches as you type.
 *
 * Only mounted in the PUBLIC layout. In the admin editor Ctrl/⌘+K inserts a
 * link (see MarkdownCheatSheet), and taking the shortcut there would break a
 * habit authors already have.
 *
 * Same endpoint, same scope and same highlighting as the results page -- the
 * helpers are shared (lib/search.tsx) -- so a query means the same thing in
 * both places, and "all results" just opens the page for it.
 */
export function QuickSearch({
  open,
  onOpenChange,
  scope,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The project and version being read, when that is a versioned project --
   *  exactly what the header search passes along. */
  scope: { project: string; version: string } | null;
}) {
  const { t } = useI18n();
  const { lang, path } = useContentLang();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [corrected, setCorrected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestId = useRef(0);
  const listId = useId();
  const terms = useMemo(() => termsOf(corrected ?? query), [corrected, query]);

  // Fresh every time it opens: yesterday's query in an input you just
  // summoned to ask something new is one more thing to delete first.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setResults([]);
    setActive(0);
  }, [open]);

  useEffect(() => {
    const q = query.trim();
    if (!open || q.length < 2) {
      setResults([]);
      setCorrected(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    const id = ++requestId.current;
    const timer = window.setTimeout(() => {
      api
        .search(q, lang, scope?.project, scope?.version)
        .then((r) => {
          // Only the newest answer counts: a slow reply to "inst" must not
          // land on top of the one for "installation".
          if (id !== requestId.current) return;
          setResults(r.results.slice(0, MAX_HITS));
          setCorrected(r.corrected ?? null);
          setActive(0);
        })
        .catch(() => id === requestId.current && setResults([]))
        .finally(() => id === requestId.current && setLoading(false));
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query, open, lang, scope?.project, scope?.version]);

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  const allResultsPath = useCallback(() => {
    const extra = scope
      ? `&project=${encodeURIComponent(scope.project)}&version=${encodeURIComponent(scope.version)}`
      : "";
    return path(`/search?q=${encodeURIComponent(query.trim())}${extra}`);
  }, [path, query, scope]);

  function go(to: string) {
    close();
    navigate(to);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (results.length ? (i + 1) % results.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (results.length ? (i - 1 + results.length) % results.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[active]) go(searchResultPath(results[active], scope?.project ?? "", path));
      else if (query.trim()) go(allResultsPath());
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  if (!open) return null;

  const q = query.trim();
  const activeId = results[active] ? `${listId}-${active}` : undefined;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[12vh] backdrop-blur-[2px]"
      // A click on the dim backdrop closes; one inside the panel does not.
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("quickSearch.title")}
        className="w-full max-w-xl overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-3">
          <Search className="h-4 w-4 shrink-0 text-[var(--muted)]" aria-hidden="true" />
          <input
            ref={inputRef}
            // Focused as it mounts, not a frame later: someone who presses
            // Ctrl/⌘+K and starts typing at once would otherwise lose the
            // first letters to the page behind the dialog.
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t("quickSearch.placeholder")}
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--muted)]"
            role="combobox"
            aria-expanded={results.length > 0}
            aria-controls={listId}
            aria-activedescendant={activeId}
            aria-autocomplete="list"
          />
          <kbd className="rounded border border-[var(--border)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">Esc</kbd>
        </div>

        {corrected && results.length > 0 && (
          <p className="px-4 pt-2 text-xs text-[var(--muted)]">
            {t("search.resultsFor")} „{corrected}“
          </p>
        )}
        {results.length > 0 && (
          <ul id={listId} role="listbox" className="max-h-[55vh] overflow-y-auto p-2">
            {results.map((r, index) => (
              <li
                key={`${r.project_slug}/${r.version}/${r.page_slug}/${r.language}`}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === active}
                onMouseMove={() => setActive(index)}
                onClick={() => go(searchResultPath(r, scope?.project ?? "", path))}
                className={`flex cursor-pointer gap-3 rounded-lg px-3 py-2 ${
                  index === active ? "bg-[var(--accent-soft)]" : ""
                }`}
              >
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{r.title}</span>
                  <span className="block truncate text-xs text-[var(--muted)]">
                    {r.project_name} › {r.category_name}
                  </span>
                  {r.snippet && (
                    <span className="mt-0.5 line-clamp-2 block text-xs text-[var(--muted)]">
                      <Highlighted text={r.snippet} terms={terms} />
                    </span>
                  )}
                </span>
                {index === active && (
                  <CornerDownLeft className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                )}
              </li>
            ))}
          </ul>
        )}

        {q.length >= 2 && !loading && results.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-[var(--muted)]">{t("quickSearch.noResults")}</p>
        )}

        <div className="flex items-center justify-between gap-3 border-t border-[var(--border)] px-3 py-2 text-[11px] text-[var(--muted)]">
          <span>{t("quickSearch.hint")}</span>
          {q.length >= 2 && (
            <button type="button" onClick={() => go(allResultsPath())} className="hover:text-[var(--accent)]">
              {t("quickSearch.allResults")} →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Opens the quick search on Ctrl/⌘+K anywhere, and on "/" unless the reader
 *  is typing somewhere (then "/" is just a slash). */
export function useQuickSearchShortcut(onOpen: () => void) {
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
        return;
      }
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const typing =
        target?.isContentEditable ||
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT";
      if (typing) return;
      e.preventDefault();
      onOpen();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onOpen]);
}
