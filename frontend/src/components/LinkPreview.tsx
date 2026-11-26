// A link to another page of the docs shows what is behind it on hover: the
// page's title, its category and its first lines -- enough to decide
// whether to follow it before leaving the paragraph. Only where there is a
// pointer that can hover (a tap just follows the link) and only after a
// short pause, so a mouse passing over a paragraph doesn't set off fetches.
import { useEffect, useId, useRef, useState, type AnchorHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { useContentLang } from "@/lib/lang";
import { excerpt } from "@/lib/textStats";

const DELAY_MS = 350;
const WIDTH = 320;

interface Preview {
  title: string;
  category: string;
  text: string;
}

/** Fetched once per page and language for as long as the tab is open. */
const cache = new Map<string, Promise<Preview | null>>();

/** The project and page a docs link points at, or null for anything else.
 *  Accepts a language prefix and a version segment in front of /pages/. */
export function internalPage(href: string | undefined): { project: string; page: string } | null {
  if (!href || !href.startsWith("/")) return null;
  const match = /^(?:\/[a-z]{2}(?:-[A-Za-z]{2,4})?)?\/p\/([^/?#]+)(?:\/v\/[^/?#]+)?\/pages\/([^/?#]+)/.exec(href);
  return match ? { project: decodeURIComponent(match[1]), page: decodeURIComponent(match[2]) } : null;
}

function load(project: string, page: string, lang: string): Promise<Preview | null> {
  const key = `${lang}|${project}|${page}`;
  let entry = cache.get(key);
  if (!entry) {
    entry = api
      .publicGetPage(project, page, lang)
      .then((r) => ({ title: r.page.title, category: r.category.name, text: excerpt(r.page.markdown_content, 180) }))
      .catch(() => null);
    cache.set(key, entry);
  }
  return entry;
}

const canHover = () => typeof window !== "undefined" && window.matchMedia?.("(hover: hover)").matches;

export function PreviewLink({ children, href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const { lang } = useContentLang();
  const target = internalPage(href);
  const anchor = useRef<HTMLAnchorElement>(null);
  const timer = useRef(0);
  const id = useId();
  const [shown, setShown] = useState<{ preview: Preview; top: number; left: number } | null>(null);

  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {
    if (!shown) return;
    const hide = () => setShown(null);
    window.addEventListener("scroll", hide, { passive: true });
    return () => window.removeEventListener("scroll", hide);
  }, [shown]);

  if (!target || href?.split("#")[0] === window.location.pathname) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  }

  function start() {
    if (!canHover() || !target) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      void load(target.project, target.page, lang).then((preview) => {
        const el = anchor.current;
        if (!preview || !el || !el.matches(":hover, :focus-visible")) return;
        const rect = el.getClientRects()[0] ?? el.getBoundingClientRect();
        const left = Math.max(8, Math.min(rect.left, window.innerWidth - WIDTH - 8));
        setShown({ preview, top: rect.bottom + 6, left });
      });
    }, DELAY_MS);
  }
  function stop() {
    window.clearTimeout(timer.current);
    setShown(null);
  }

  return (
    <>
      <a
        ref={anchor}
        href={href}
        {...props}
        onMouseEnter={start}
        onMouseLeave={stop}
        onFocus={start}
        onBlur={stop}
        aria-describedby={shown ? id : undefined}
      >
        {children}
      </a>
      {shown &&
        createPortal(
          <span
            id={id}
            role="tooltip"
            className="link-preview fixed z-50 block rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 text-left shadow-xl"
            style={{ top: shown.top, left: shown.left, width: WIDTH }}
          >
            <span className="block text-xs text-[var(--muted)]">{shown.preview.category}</span>
            <span className="mt-0.5 block font-semibold text-[var(--ink)]">{shown.preview.title}</span>
            {shown.preview.text && (
              <span className="mt-1 line-clamp-3 block text-sm text-[var(--muted)]">{shown.preview.text}</span>
            )}
          </span>,
          document.body,
        )}
    </>
  );
}
