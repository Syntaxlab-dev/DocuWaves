import type { Heading } from "@/lib/headings";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The ids linked here come from collectHeadings(), which is also what
 * MarkdownView puts on the rendered headings -- see lib/headings.ts.
 *
 * `variant` is the same list in the two places it fits: its own column
 * beside the text on a wide screen, and a collapsed disclosure above the
 * text where that column doesn't exist. Not rendering it at all below the
 * wide breakpoint would take a long page's overview away from exactly the
 * screen where scrolling one is worst.
 */
export function TableOfContents({ headings, variant }: { headings: Heading[]; variant: "column" | "inline" }) {
  const { t } = useI18n();

  if (variant === "inline") {
    // toc-inline so the print stylesheet can drop this one <details> without
    // touching a collapsible an author wrote inside a page -- that is
    // content, and it has to print.
    return (
      <details className="toc-inline mb-6 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 xl:hidden">
        <summary className="cursor-pointer text-sm font-medium">{t("page.onThisPage")}</summary>
        <List headings={headings} className="mt-2" />
      </details>
    );
  }

  return (
    <aside className="hidden xl:block xl:w-56 xl:shrink-0">
      <div className="sticky top-6 max-h-[calc(100vh-5rem)] overflow-y-auto">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{t("page.onThisPage")}</div>
        <List headings={headings} className="mt-2" />
      </div>
    </aside>
  );
}

function List({ headings, className }: { headings: Heading[]; className?: string }) {
  return (
    <ul className={cn("flex flex-col gap-1 text-sm", className)}>
      {headings.map((heading) => (
        <li key={heading.id}>
          <a
            href={`#${heading.id}`}
            className={cn(
              "block text-[var(--muted)] hover:text-[var(--accent)]",
              heading.level === 3 && "pl-3 text-xs",
            )}
          >
            {heading.text}
          </a>
        </li>
      ))}
    </ul>
  );
}
