/**
 * Three small blocks, written so the page still reads right anywhere else
 * Markdown is shown (GitHub, an editor, the content repo) -- the same rule
 * tabs and callouts follow (lib/tabs.ts, lib/callouts.ts):
 *
 * STEPS: a list after `<!-- steps -->` is shown as numbered steps, each
 * with a big number and a line down to the next.
 *
 *     <!-- steps -->
 *
 *     1. **Download** the installer.
 *     2. **Run** it and follow the prompts.
 *
 * CARDS: a list after `<!-- cards -->` is shown as a grid of cards. A link
 * in an item makes the whole card clickable.
 *
 *     <!-- cards -->
 *
 *     - **[Install](/p/docs/pages/install)** Get it running in five minutes.
 *     - **[Configure](/p/docs/pages/config)** Every setting explained.
 *
 * BADGES: inline code starting with `badge:` is a small label, optionally
 * with a colour: `badge:Beta`, `badge:success:New`, `badge:warning:Deprecated`.
 *
 * On GitHub the comments are invisible and what is left is an ordinary list;
 * a badge shows as the code `badge:Beta`, which still says what it means.
 * A marker not followed by a list is simply dropped.
 */

const STEPS = /^<!--\s*steps\s*-->$/i;
const CARDS = /^<!--\s*cards\s*-->$/i;
const BADGE = /^badge:(?:(info|success|warning|danger|neutral):)?(.+)$/i;

type MdNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
  data?: Record<string, unknown>;
};

export function remarkBlocks() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

function marker(node: MdNode | undefined): "steps" | "cards" | null {
  if (node?.type !== "html" || typeof node.value !== "string") return null;
  const text = node.value.trim();
  if (STEPS.test(text)) return "steps";
  if (CARDS.test(text)) return "cards";
  return null;
}

function addClass(node: MdNode, name: string) {
  const data = (node.data ??= {});
  const properties = ((data.hProperties as Record<string, unknown> | undefined) ??= {});
  const existing = Array.isArray(properties.className) ? (properties.className as string[]) : [];
  properties.className = [...existing, name];
}

function firstLink(node: MdNode): MdNode | null {
  if (node.type === "link") return node;
  for (const child of node.children ?? []) {
    const found = firstLink(child);
    if (found) return found;
  }
  return null;
}

function walk(node: MdNode): void {
  const children = node.children;
  if (!children) return;
  for (let i = 0; i < children.length; i += 1) {
    const child = children[i];
    const kind = marker(child);
    if (kind) {
      const next = children[i + 1];
      if (next?.type === "list") {
        addClass(next, kind === "steps" ? "steps" : "cards");
        if (kind === "cards") {
          for (const item of next.children ?? []) {
            addClass(item, "card");
            if (firstLink(item)) addClass(item, "card-linked");
          }
        }
      }
      children.splice(i, 1);
      i -= 1;
      continue;
    }
    if (child.type === "inlineCode" && typeof child.value === "string") {
      const badge = BADGE.exec(child.value.trim());
      if (badge && badge[2].trim()) {
        children[i] = {
          type: "badge",
          data: {
            hName: "span",
            hProperties: { className: ["badge", `badge-${(badge[1] ?? "info").toLowerCase()}`] },
          },
          children: [{ type: "text", value: badge[2].trim() }],
        };
        continue;
      }
    }
    walk(child);
  }
}
