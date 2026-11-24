/** Nested categories in the admin area, where the list comes flat in sort
 *  order (the public nav already arrives in reading order, see lib/nav.ts).
 *  Pure, so the rules -- reading order, no moving a category into its own
 *  branch, how deep is too deep -- are tested without a browser. */

/** As deep as the server allows (content_sync.MAX_CATEGORY_DEPTH). */
export const MAX_CATEGORY_DEPTH = 4;

interface Node {
  slug: string;
  parent?: string;
}

/** Each category followed by everything under it, with its depth (0 at the
 *  top); siblings keep their order. A category whose parent is not in the
 *  list counts as top-level, so nothing is ever dropped. */
export function categoryTree<T extends Node>(categories: T[]): { category: T; depth: number }[] {
  const slugs = new Set(categories.map((c) => c.slug));
  const children = new Map<string, T[]>();
  for (const c of categories) {
    const parent = c.parent && slugs.has(c.parent) && c.parent !== c.slug ? c.parent : "";
    children.set(parent, [...(children.get(parent) ?? []), c]);
  }
  const ordered: { category: T; depth: number }[] = [];
  const seen = new Set<string>();
  const walk = (parent: string, depth: number) => {
    for (const category of children.get(parent) ?? []) {
      if (seen.has(category.slug)) continue;
      seen.add(category.slug);
      ordered.push({ category, depth });
      walk(category.slug, depth + 1);
    }
  };
  walk("", 0);
  // A loop the server would have cut (it never sends one): still listed.
  for (const category of categories) {
    if (!seen.has(category.slug)) ordered.push({ category, depth: 0 });
  }
  return ordered;
}

/** Where `slug` may be moved to: every category outside its own branch
 *  whose depth still leaves room for that branch. "" (the top level) is
 *  always allowed and not in the list. `slug` null = a new category. */
export function parentChoices<T extends Node>(categories: T[], slug: string | null): { category: T; depth: number }[] {
  const tree = categoryTree(categories);
  const index = slug === null ? -1 : tree.findIndex((e) => e.category.slug === slug);
  let branch = new Set<string>();
  let branchHeight = 1;
  if (index >= 0) {
    const base = tree[index].depth;
    const below = [];
    for (const entry of tree.slice(index + 1)) {
      if (entry.depth <= base) break;
      below.push(entry);
    }
    branch = new Set([slug as string, ...below.map((e) => e.category.slug)]);
    branchHeight = 1 + Math.max(0, ...below.map((e) => e.depth - base));
  }
  return tree.filter((e) => !branch.has(e.category.slug) && e.depth + 1 + branchHeight <= MAX_CATEGORY_DEPTH);
}

/** The categories sharing `category`'s parent, in order -- what the up and
 *  down arrows move it among. */
export function siblingsOf<T extends Node>(categories: T[], category: T): T[] {
  return categories.filter((c) => (c.parent ?? "") === (category.parent ?? ""));
}
