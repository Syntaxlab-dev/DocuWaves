// The public site's keyboard shortcuts, and the overview of them behind "?".
// Single keys only fire when the reader isn't typing somewhere, so "b" in a
// search field is still a "b".
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!(
    el?.isContentEditable ||
    el?.tagName === "INPUT" ||
    el?.tagName === "TEXTAREA" ||
    el?.tagName === "SELECT"
  );
}

/** Wires the single-key shortcuts. The actions that belong to a page
 *  (bookmark, previous, next) click that page's own control, found by a
 *  data attribute -- so a shortcut can never do what the button can't. */
export function useReaderShortcuts({ onHelp, onTheme }: { onHelp: () => void; onTheme: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      // An open dialog (quick search, an enlarged image) owns the keyboard.
      if (document.querySelector('[aria-modal="true"]')) return;
      const click = (selector: string) => {
        const el = document.querySelector<HTMLElement>(selector);
        if (!el) return false;
        el.click();
        return true;
      };
      let handled = true;
      if (e.key === "?") onHelp();
      else if (e.key === "b") handled = click("[data-bookmark-toggle]");
      else if (e.key === "[") handled = click('[data-page-nav="previous"]');
      else if (e.key === "]") handled = click('[data-page-nav="next"]');
      else if (e.key === "t") onTheme();
      else handled = false;
      if (handled) e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onHelp, onTheme]);
}

export function ShortcutsDialog({ open, onClose, isMac }: { open: boolean; onClose: () => void; isMac: boolean }) {
  const { t } = useI18n();
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "?") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  const rows: [string[], string][] = [
    [[isMac ? "⌘" : "Ctrl", "K"], t("shortcuts.search")],
    [["/"], t("shortcuts.search")],
    [["["], t("shortcuts.prev")],
    [["]"], t("shortcuts.next")],
    [["b"], t("shortcuts.bookmark")],
    [["t"], t("shortcuts.theme")],
    [["?"], t("shortcuts.help")],
    [["Esc"], t("shortcuts.close")],
  ];
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        className="w-full max-w-sm rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <h2 id="shortcuts-title" className="text-base font-semibold">
            {t("shortcuts.title")}
          </h2>
          <button
            ref={closeButton}
            type="button"
            onClick={onClose}
            aria-label={t("shortcuts.close")}
            className="rounded-md p-1 text-[var(--muted)] hover:bg-[var(--surface-2)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <dl className="mt-4 space-y-2 text-sm">
          {rows.map(([keys, label], i) => (
            <div key={i} className="flex items-center justify-between gap-4">
              <dt className="text-[var(--muted)]">{label}</dt>
              <dd className="flex gap-1">
                {keys.map((k) => (
                  <kbd
                    key={k}
                    className="min-w-[1.75rem] rounded border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 text-center text-xs"
                  >
                    {k}
                  </kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
