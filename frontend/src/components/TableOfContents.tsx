import { useEffect, useState } from "react";
import type { Heading } from "@/lib/headings";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * Which section the reader is currently in, by id.
 *
 * An IntersectionObserver over the rendered headings rather than a scroll
 * handler: a scroll listener runs on every frame of every scroll and has to
 * measure each heading's position to decide anything, which is exactly the
 * layout thrashing that makes a long page stutter on a phone. The observer
 * is told once what to watch and reports only when something crosses the
 * line.
 *
 * The line is the TOP 30% of the viewport (`0px 0px -70% 0px`): the section
 * a reader is reading is the one whose heading is above them, not the one
 * whose heading happens to be visible at the very bottom of the screen. Any
 * heading inside that band counts as entered, and the FIRST one in source
 * order wins when several are -- which is what makes a run of short
 * subsections behave, rather than flickering between them.
 *
 * When nothing is in the band at all -- the middle of a long section, or the
 * foot of the page -- the previous answer is kept. Clearing it there would
 * blank the marker for most of the time spent reading, which is the opposite
 * of what it is for.
 */
function useActiveHeading(headings: Heading[]): string {
  const [active, setActive] = useState("");

  useEffect(() => {
    if (headings.length === 0) return;
    const elements = headings
      .map((heading) => document.getElementById(heading.id))
      .filter((element): element is HTMLElement => element !== null);
    if (elements.length === 0) return;

    // Kept across callbacks: one callback only carries the headings that
    // CHANGED state, so deciding from it alone would forget everything else
    // that is still on screen.
    const visible = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        }
        const first = headings.find((heading) => visible.has(heading.id));
        if (first) setActive(first.id);
      },
      { rootMargin: "0px 0px -70% 0px", threshold: 0 },
    );
    for (const element of elements) observer.observe(element);
    return () => observer.disconnect();
    // The headings array is memoized by the page that builds it, so this
    // re-runs when the page's content changes and not on every render.
  }, [headings]);

  return active;
}

/**
 * The ids linked here come from collectHeadings(), which is also what
 * MarkdownView puts on the rendered headings -- see lib/headings.ts.
 *
 * `variant` is the same list in the three places it fits:
 * - `column`  -- its own column beside the text on a wide screen.
 * - `inline`  -- a collapsed disclosure above the text, on the screens that
 *   have no room for that column. Not rendering it at all below the wide
 *   breakpoint would take a long page's overview away from exactly the
 *   screen where scrolling one is worst. It hides itself once the column
 *   appears, since the page renders both and only one should be visible.
 * - `standalone` -- the same disclosure, on a page that has no column to
 *   defer to at any width (the preview view, which is one narrow text and
 *   deliberately no sidebar). Without it, a wide screen there would show no
 *   contents at all, which is the one case `inline` alone gets wrong.
 */
export function TableOfContents({
  headings,
  variant,
}: {
  headings: Heading[];
  variant: "column" | "inline" | "standalone";
}) {
  const { t } = useI18n();
  const active = useActiveHeading(headings);

  if (variant === "inline" || variant === "standalone") {
    // toc-inline so the print stylesheet can drop this one <details> without
    // touching a collapsible an author wrote inside a page -- that is
    // content, and it has to print.
    return (
      <details
        className={cn(
          "toc-inline mb-6 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2",
          variant === "inline" && "xl:hidden",
        )}
      >
        <summary className="cursor-pointer text-sm font-medium">{t("page.onThisPage")}</summary>
        <List headings={headings} active={active} className="mt-2" />
      </details>
    );
  }

  return (
    <aside className="hidden xl:block xl:w-56 xl:shrink-0">
      <div className="sticky top-6 max-h-[calc(100vh-5rem)] overflow-y-auto">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{t("page.onThisPage")}</div>
        <List headings={headings} active={active} className="mt-2" />
      </div>
    </aside>
  );
}

function List({ headings, active, className }: { headings: Heading[]; active: string; className?: string }) {
  return (
    <ul className={cn("flex flex-col gap-1 text-sm", className)}>
      {headings.map((heading) => {
        const current = heading.id === active;
        return (
          <li key={heading.id}>
            <a
              href={`#${heading.id}`}
              // aria-current="location" is the attribute for "this entry is
              // the place in the document you are at" -- so the marker is not
              // only a colour, and a screen reader announces it too.
              aria-current={current ? "location" : undefined}
              className={cn(
                "block border-l-2 pl-2 -ml-[2px] hover:text-[var(--accent)]",
                // The left rule is always there, transparent when inactive:
                // colouring a border that only exists on the active entry
                // would shift every other line by two pixels as the reader
                // scrolls.
                current
                  ? "border-[var(--accent)] font-medium text-[var(--accent)]"
                  : "border-transparent text-[var(--muted)]",
                heading.level === 3 && "pl-4 text-xs",
              )}
            >
              {heading.text}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
