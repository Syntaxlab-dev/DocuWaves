/**
 * "Do these two Markdown texts say the same thing?" -- asked of a page and of
 * what the visual editor would write back for it (components/visual/).
 *
 * Compared as the Markdown TREE the site renders from (the same parser and
 * extensions as MarkdownView: GFM and math), not as text. Two spellings of one
 * document -- `*` or `-` for a bullet, `*em*` or `_em_`, a reference link or an
 * inline one, a blank line more or less -- are the same document to a reader,
 * and the visual editor is allowed to change them. A word, a link target, a
 * table cell, a code block's language or file name, an HTML comment that
 * marks tabs or a snippet: those are content, and any difference there means
 * the visual editor would lose something -- so the page opens in Markdown
 * instead.
 */
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

type Node = {
  type: string;
  children?: Node[];
  value?: string;
  url?: string;
  identifier?: string;
  label?: string | null;
  referenceType?: string;
  [key: string]: unknown;
};

const parser = unified().use(remarkParse).use(remarkGfm).use(remarkMath);

// Spelling, not content: where a node sits, how a list or table was spaced.
const IGNORED = new Set(["position", "spread", "data"]);

function definitions(tree: Node): Map<string, Node> {
  const found = new Map<string, Node>();
  const walk = (node: Node) => {
    if (node.type === "definition" && node.identifier) found.set(node.identifier.toLowerCase(), node);
    node.children?.forEach(walk);
  };
  walk(tree);
  return found;
}

function normalize(node: Node, defs: Map<string, Node>): Node | null {
  if (node.type === "definition") return null; // folded into the links below
  let current = node;
  // `[text][ref]` + `[ref]: url` reads exactly like `[text](url)`.
  if ((node.type === "linkReference" || node.type === "imageReference") && node.identifier) {
    const def = defs.get(node.identifier.toLowerCase());
    if (def) {
      current = {
        type: node.type === "linkReference" ? "link" : "image",
        url: def.url,
        title: def.title ?? null,
        ...(node.type === "imageReference" ? { alt: node.alt } : {}),
        children: node.children,
      };
    }
  }
  const out: Node = { type: current.type };
  for (const [key, value] of Object.entries(current)) {
    if (key === "type" || key === "children" || IGNORED.has(key)) continue;
    if (key === "start" && value === 1) continue; // `1.` is the default start
    if (value === null || value === undefined) continue;
    out[key] = typeof value === "string" && (key === "value" || key === "meta") ? value.replace(/\s+$/, "") : value;
  }
  if (current.children) {
    const children: Node[] = [];
    for (const child of current.children) {
      const normalized = normalize(child, defs);
      if (!normalized) continue;
      // Adjacent text is one text, however it was split.
      const last = children[children.length - 1];
      if (normalized.type === "text" && last?.type === "text") {
        last.value = `${last.value ?? ""}${normalized.value ?? ""}`;
      } else {
        children.push(normalized);
      }
    }
    // Whitespace at the edges of a block is layout.
    const first = children[0];
    if (first?.type === "text" && typeof first.value === "string") first.value = first.value.replace(/^\s+/, "");
    const lastChild = children[children.length - 1];
    if (lastChild?.type === "text" && typeof lastChild.value === "string") {
      lastChild.value = lastChild.value.replace(/\s+$/, "");
    }
    out.children = children.filter((c) => !(c.type === "text" && c.value === ""));
  }
  return out;
}

/** The document a Markdown text describes, without its spelling. */
export function markdownTree(markdown: string): Node {
  const tree = parser.parse(markdown.replace(/\r\n/g, "\n")) as unknown as Node;
  return normalize(tree, definitions(tree)) ?? { type: "root", children: [] };
}

/** Whether two Markdown texts describe the same document. */
export function sameDocument(a: string, b: string): boolean {
  return JSON.stringify(markdownTree(a)) === JSON.stringify(markdownTree(b));
}

/** Where they first differ, for a test failure or a log line. */
export function firstDifference(a: string, b: string): string {
  const left = JSON.stringify(markdownTree(a), null, 1).split("\n");
  const right = JSON.stringify(markdownTree(b), null, 1).split("\n");
  const index = left.findIndex((line, i) => line !== right[i]);
  if (index === -1) return left.length === right.length ? "" : "(one document is longer)";
  return `line ${index}: ${left[index]?.trim()}  ≠  ${right[index]?.trim()}`;
}
