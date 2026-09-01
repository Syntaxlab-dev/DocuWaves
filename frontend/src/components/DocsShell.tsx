import type { ReactNode } from "react";
import type { ProjectNav } from "@/lib/api";
import { DocsSidebar } from "@/components/DocsSidebar";

/**
 * The three reading views (project, category, page) all sit in the same
 * frame: nav column, the text, and optionally a contents column. The home
 * page deliberately isn't one of them -- it's the entry point, where project
 * tiles are the navigation and there is no project to show a tree for yet.
 *
 * Wider than the max-w-5xl the home and search views keep, because that
 * width is the text column here, not the whole page.
 */
export function DocsShell({
  nav,
  activeCategorySlug,
  activePageSlug,
  aside,
  children,
}: {
  nav: ProjectNav;
  activeCategorySlug?: string;
  activePageSlug?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="lg:flex lg:items-start lg:gap-10">
        <DocsSidebar nav={nav} activeCategorySlug={activeCategorySlug} activePageSlug={activePageSlug} />
        {/* min-w-0: without it a wide code block or table inside the
            Markdown stretches this flex item instead of scrolling in place,
            and pushes the columns off the screen. */}
        <div className="mt-8 min-w-0 flex-1 lg:mt-0">{children}</div>
        {aside}
      </div>
    </div>
  );
}
