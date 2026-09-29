/**
 * Callouts ("admonitions") in GitHub's own syntax:
 *
 *     > [!WARNING]
 *     > Back up the data volume before upgrading.
 *
 * GitHub's syntax rather than a `:::warning` container of our own, for the
 * same reason images are plain relative paths (see MarkdownView): the content
 * repo is meant to read correctly on GitHub too, and GitHub renders exactly
 * these five kinds as coloured boxes. Anywhere else they degrade to an
 * ordinary quote that starts with "[!WARNING]" -- still readable.
 *
 * A remark plugin, run on the Markdown tree before it becomes HTML: it finds
 * a blockquote whose first line is the marker, removes the marker and tags
 * the blockquote with the kind. MarkdownView's `blockquote` renderer does the
 * rest. Nothing else in the document is touched.
 */

export const CALLOUT_KINDS = ["note", "tip", "important", "warning", "caution"] as const;
export type CalloutKind = (typeof CALLOUT_KINDS)[number];

const MARKER = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\r?\n|$)/i;

// The few mdast shapes this plugin touches, spelled out rather than pulling in
// @types/mdast for three fields.
type MdNode = {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hProperties?: Record<string, unknown> } & Record<string, unknown>;
};

export function calloutKind(firstText: string): CalloutKind | null {
  const match = MARKER.exec(firstText);
  return match ? (match[1].toLowerCase() as CalloutKind) : null;
}

export function remarkCallouts() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

function walk(node: MdNode): void {
  if (node.type === "blockquote") tagCallout(node);
  for (const child of node.children ?? []) walk(child);
}

function tagCallout(quote: MdNode): void {
  const paragraph = quote.children?.[0];
  if (paragraph?.type !== "paragraph") return;
  const text = paragraph.children?.[0];
  if (text?.type !== "text" || typeof text.value !== "string") return;

  const match = MARKER.exec(text.value);
  if (!match) return;
  const kind = match[1].toLowerCase() as CalloutKind;

  text.value = text.value.slice(match[0].length);
  // The marker was the whole first line: drop what is left empty, so the box
  // does not open with a blank paragraph.
  if (text.value === "") paragraph.children!.shift();
  // A soft line break right after the marker is its own node in some trees.
  const next = paragraph.children?.[0];
  if (next?.type === "break") paragraph.children!.shift();
  if (paragraph.children!.length === 0) quote.children!.shift();

  quote.data = {
    ...quote.data,
    // camelCase: hast property names are, and this is what the renderer
    // reads back from the element (it becomes data-callout in the DOM).
    hProperties: { ...(quote.data?.hProperties ?? {}), dataCallout: kind },
  };
}
