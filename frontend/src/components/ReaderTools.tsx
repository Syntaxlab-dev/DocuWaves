// The small helpers around a long page: a reading-progress line at the very
// top, a "back to top" button once the reader is well down, and a text
// settings menu (size, line width). All three stay out of print (index.css).
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Type } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { setReaderPrefs, useReaderPrefs, type ReaderFont, type ReaderSize, type ReaderWidth } from "@/lib/readerPrefs";

function useScroll(): { progress: number; y: number; long: boolean } {
  const [state, setState] = useState({ progress: 0, y: 0, long: false });
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const doc = document.documentElement;
      const room = doc.scrollHeight - window.innerHeight;
      setState({
        y: window.scrollY,
        progress: room > 0 ? Math.min(1, Math.max(0, window.scrollY / room)) : 0,
        // Only a page worth a progress line: more than two screens of it.
        long: room > window.innerHeight * 1.5,
      });
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);
  return state;
}

export function ReadingProgress() {
  const { progress, long } = useScroll();
  if (!long) return null;
  return (
    <div className="reader-chrome pointer-events-none fixed inset-x-0 top-0 z-40 h-0.5" aria-hidden="true">
      <div className="h-full origin-left bg-[var(--accent)]" style={{ transform: `scaleX(${progress})` }} />
    </div>
  );
}

export function BackToTop() {
  const { t } = useI18n();
  const { y } = useScroll();
  const visible = y > 900;
  return (
    <button
      type="button"
      aria-label={t("reader.backToTop")}
      title={t("reader.backToTop")}
      tabIndex={visible ? 0 : -1}
      aria-hidden={!visible}
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      className={`reader-chrome fixed right-4 bottom-4 z-30 flex h-10 w-10 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface)] shadow-lg transition-opacity hover:text-[var(--accent)] ${
        visible ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
    >
      <ArrowUp className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}

export function ReaderSettings() {
  const { t } = useI18n();
  const prefs = useReaderPrefs();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const sizes: [ReaderSize, string][] = [
    ["s", t("reader.sizeSmall")],
    ["m", t("reader.sizeMedium")],
    ["l", t("reader.sizeLarge")],
  ];
  const widths: [ReaderWidth, string][] = [
    ["full", t("reader.widthFull")],
    ["narrow", t("reader.widthNarrow")],
  ];
  const fonts: [ReaderFont, string][] = [
    ["sans", t("reader.fontSans")],
    ["serif", t("reader.fontSerif")],
  ];
  const segment = (active: boolean) =>
    `flex-1 rounded-md px-2 py-1 text-xs transition-colors ${
      active ? "bg-[var(--accent)] text-[var(--accent-ink)]" : "text-[var(--muted)] hover:text-[var(--ink)]"
    }`;

  return (
    <div ref={box} className="reader-chrome relative">
      <button
        type="button"
        aria-expanded={open}
        aria-label={t("reader.settings")}
        title={t("reader.settings")}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]"
      >
        <Type className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="group"
          aria-label={t("reader.settings")}
          className="absolute right-0 z-30 mt-1 w-56 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3 shadow-lg"
        >
          <p className="text-xs font-medium">{t("reader.size")}</p>
          <div className="mt-1 flex gap-1 rounded-lg border border-[var(--border)] p-0.5">
            {sizes.map(([value, label]) => (
              <button key={value} type="button" aria-pressed={prefs.size === value} className={segment(prefs.size === value)} onClick={() => setReaderPrefs({ size: value })}>
                {label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs font-medium">{t("reader.width")}</p>
          <div className="mt-1 flex gap-1 rounded-lg border border-[var(--border)] p-0.5">
            {widths.map(([value, label]) => (
              <button key={value} type="button" aria-pressed={prefs.width === value} className={segment(prefs.width === value)} onClick={() => setReaderPrefs({ width: value })}>
                {label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs font-medium">{t("reader.font")}</p>
          <div className="mt-1 flex gap-1 rounded-lg border border-[var(--border)] p-0.5">
            {fonts.map(([value, label]) => (
              <button key={value} type="button" aria-pressed={prefs.font === value} className={segment(prefs.font === value)} onClick={() => setReaderPrefs({ font: value })}>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
