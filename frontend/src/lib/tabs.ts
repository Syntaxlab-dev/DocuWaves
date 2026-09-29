/**
 * Tabs: the same step written for several systems, shown one at a time.
 *
 *     <!-- tabs -->
 *     #### macOS
 *     ```bash
 *     brew install docuwaves
 *     ```
 *     #### Linux
 *     ```bash
 *     apt install docuwaves
 *     ```
 *     <!-- /tabs -->
 *
 * The markers are HTML comments and the tab names are ordinary headings, for
 * the same reason callouts use GitHub's own syntax (see lib/callouts.ts): the
 * content repo has to read correctly anywhere else. On GitHub the comments
 * are invisible and what is left is a heading per system with its steps
 * underneath -- exactly how one would write it without tabs. A container
 * syntax of our own (`:::tabs`, MkDocs' `=== "macOS"`) would show up there as
 * stray punctuation, or turn the indented steps into a code block.
 *
 * Whatever heading level comes first after the opening marker names the
 * tabs; deeper headings are content of the tab they are in. A block that
 * does not start with a heading, or is never closed, loses just its markers
 * and reads like the page without tabs.
 *
 * Choosing a tab is remembered BY NAME and applies to every group on every
 * page: someone on Linux picks "Linux" once, not once per code sample.
 */
import { useSyncExternalStore } from "react";

const OPEN = /^<!--\s*tabs\s*-->$/i;
const CLOSE = /^<!--\s*\/tabs\s*-->$/i;

type MdNode = {
  type: string;
  value?: string;
  depth?: number;
  children?: MdNode[];
  data?: Record<string, unknown>;
};

export function isTabsOpen(line: string): boolean {
  return OPEN.test(line.trim());
}

export function isTabsClose(line: string): boolean {
  return CLOSE.test(line.trim());
}

export function remarkTabs() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

function isMarker(node: MdNode | undefined, marker: RegExp): boolean {
  return node?.type === "html" && typeof node.value === "string" && marker.test(node.value.trim());
}

function walk(node: MdNode): void {
  const children = node.children;
  if (!children) return;
  for (let i = 0; i < children.length; i += 1) {
    if (isMarker(children[i], OPEN)) {
      const end = children.findIndex((child, j) => j > i && isMarker(child, CLOSE));
      const group = end === -1 ? null : tabGroup(children.slice(i + 1, end));
      if (group) {
        children.splice(i, end - i + 1, group);
      } else {
        // Not a usable group: drop just the markers, so the page reads as it
        // would without them rather than showing "<!-- tabs -->" as text
        // (raw HTML is displayed, not interpreted -- see MarkdownView).
        if (end !== -1) children.splice(end, 1);
        children.splice(i, 1);
        i -= 1;
        continue;
      }
    } else if (isMarker(children[i], CLOSE)) {
      children.splice(i, 1);
      i -= 1;
      continue;
    }
    // Into the group too: a tab may hold a callout, a list -- or tabs.
    walk(children[i]);
  }
}

function tabGroup(nodes: MdNode[]): MdNode | null {
  const first = nodes[0];
  if (first?.type !== "heading" || !first.depth) return null;
  const depth = first.depth;

  const panels: MdNode[] = [];
  for (const node of nodes) {
    if (node.type === "heading" && node.depth === depth) {
      panels.push({
        type: "tabPanel",
        data: { hName: "div", hProperties: { dataTabLabel: plainText(node).trim() || "–" } },
        children: [],
      });
    } else {
      panels[panels.length - 1].children!.push(node);
    }
  }
  return { type: "tabGroup", data: { hName: "div", hProperties: { dataTabs: "true" } }, children: panels };
}

/** A heading's text without its markup -- `` #### `npm` `` names the tab "npm". */
function plainText(node: MdNode): string {
  if (typeof node.value === "string") return node.value;
  return (node.children ?? []).map(plainText).join("");
}

// ---- Which tab is chosen ----

const STORAGE_KEY = "docuwaves.tabs";
const MAX_REMEMBERED = 20;

/** Most recently chosen first. A group shows the first of these it has; a
 *  reader who picked "Linux" and later "Docker" sees Docker where there is
 *  one, and still Linux where there isn't. */
let chosen: string[] = load();
const listeners = new Set<() => void>();

function normalize(label: string): string {
  return label.trim().toLowerCase();
}

function load(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
  } catch {
    // Private window, blocked storage: tabs still work, just unremembered.
    return [];
  }
}

export function chooseTab(label: string): void {
  const key = normalize(label);
  chosen = [key, ...chosen.filter((l) => l !== key)].slice(0, MAX_REMEMBERED);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chosen));
  } catch {
    // see load()
  }
  listeners.forEach((listener) => listener());
}

export function activeTabIndex(labels: string[], preferences: string[]): number {
  const keys = labels.map(normalize);
  for (const preference of preferences) {
    const index = keys.indexOf(preference);
    if (index !== -1) return index;
  }
  return 0;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTabPreferences(): string[] {
  return useSyncExternalStore(subscribe, () => chosen, () => chosen);
}
