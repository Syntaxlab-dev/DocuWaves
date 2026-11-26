import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Bookmark, CornerDownLeft, FileText, History, Home, Keyboard, Search, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useReaderHistory } from "@/lib/readerHistory";
import { api, type SearchResult } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { Highlighted, searchResultPath, termsOf } from "@/lib/search";

const MAX_HITS = 8;
/** Per group, before anything is typed. */
const MAX_SUGGESTIONS = 4;

/** One row of the list: a search hit, or -- before anything is typed -- a
 *  bookmark, a recently read page or an action. One shape, so the arrow
 *  keys walk one list whatever is in it. */
interface Row {
  key: string;
  group?: string;
  title: string;
  sub?: string;
  snippet?: string;
  icon: LucideIcon;
  run: () => void;
}
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
  onShortcuts,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The project and version being read, when that is a versioned project --
   *  exactly what the header search passes along. */
  scope: { project: string; version: string } | null;
  /** Opens the keyboard-shortcut overview (offered as an action). */
  onShortcuts?: () => void;
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
  const { history, bookmarks } = useReaderHistory();

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

  const typed = query.trim().length >= 2;
  const rows: Row[] = typed
    ? results.map((r) => ({
        key: `${r.project_slug}/${r.version}/${r.page_slug}/${r.language}`,
        title: r.title,
        sub: `${r.project_name} › ${r.category_name}`,
        snippet: r.snippet,
        icon: FileText,
        run: () => go(searchResultPath(r, scope?.project ?? "", path)),
      }))
    : [
        ...bookmarks.slice(0, MAX_SUGGESTIONS).map((b) => ({
          key: `b:${b.path}`,
          group: t("reader.bookmarks"),
          title: b.title,
          sub: b.context,
          icon: Bookmark,
          run: () => go(b.path),
        })),
        ...history
          .filter((h) => !bookmarks.some((b) => b.path === h.path))
          .slice(0, MAX_SUGGESTIONS)
          .map((h) => ({
            key: `h:${h.path}`,
            group: t("reader.recent"),
            title: h.title,
            sub: h.context,
            icon: History,
            run: () => go(h.path),
          })),
        { key: "a:home", group: t("quickSearch.actions"), title: t("quickSearch.goHome"), icon: Home, run: () => go(path("/")) },
        {
          key: "a:changes",
          group: t("quickSearch.actions"),
          title: t("quickSearch.goChanges"),
          icon: Sparkles,
          run: () => go(path("/changes")),
        },
        ...(onShortcuts
          ? [
              {
                key: "a:keys",
                group: t("quickSearch.actions"),
                title: t("quickSearch.shortcuts"),
                icon: Keyboard,
                run: () => {
                  close();
                  onShortcuts();
                },
              },
            ]
          : []),
      ];

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (rows.length ? (i + 1) % rows.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (rows.length ? (i - 1 + rows.length) % rows.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (rows[active]) rows[active].run();
      else if (query.trim()) go(allResultsPath());
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  if (!open) return null;

  const q = query.trim();
  const activeId = rows[active] ? `${listId}-${active}` : undefined;

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
            aria-expanded={rows.length > 0}
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
        {rows.length > 0 && (
          <ul id={listId} role="listbox" className="max-h-[55vh] overflow-y-auto p-2">
            {rows.map((row, index) => {
              const Icon = row.icon;
              const heading = row.group && row.group !== rows[index - 1]?.group ? row.group : null;
              return (
                <li
                  key={row.key}
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === active}
                  onMouseMove={() => setActive(index)}
                  onClick={row.run}
                  className="cursor-pointer"
                >
                  {heading && (
                    <span aria-hidden="true" className="block px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-[var(--muted)]">
                      {heading}
                    </span>
                  )}
                  <span className={`flex gap-3 rounded-lg px-3 py-2 ${index === active ? "bg-[var(--accent-soft)]" : ""}`}>
                    <Icon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{row.title}</span>
                      {row.sub && <span className="block truncate text-xs text-[var(--muted)]">{row.sub}</span>}
                      {row.snippet && (
                        <span className="mt-0.5 line-clamp-2 block text-xs text-[var(--muted)]">
                          <Highlighted text={row.snippet} terms={terms} />
                        </span>
                      )}
                    </span>
                    {index === active && (
                      <CornerDownLeft className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                    )}
                  </span>
                </li>
              );
            })}
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
