/**
 * DocuWaves' own Markdown, made visible in the visual editor -- without
 * changing a character of what is saved (milkdown.ts's round-trip check and
 * roundtrip.test.ts hold every one of these to that):
 *
 * - CALLOUTS: `> [!WARNING]` is a blockquote that knows its kind, shown as
 *   the coloured box readers see; written back as the same marker line.
 * - VARIABLES and SNIPPETS: `{{port}}` and `<!-- snippet: name -->` stay text
 *   and an HTML comment, but look like what they are -- chips -- and tab
 *   markers say "tabs start/end" instead of showing raw comments.
 * - FORMULAS: `$…$` and `$$…$$` are nodes of their own (remark-math, the
 *   parser the site renders them with), shown rendered and edited as LaTeX
 *   with a double click -- their source is never touched as ordinary text,
 *   where `\,` and `_` would be escapes.
 * - DIAGRAMS: ```mermaid blocks keep their source editable, with a live
 *   preview right below it.
 *
 * Previews are decorations: drawn beside the document, never part of it, so
 * they can never end up in the saved file.
 */
import { $command, $nodeSchema, $prose, $remark } from "@milkdown/kit/utils";
import remarkMath from "remark-math";
import { blockquoteSchema, htmlSchema } from "@milkdown/kit/preset/commonmark";
import { Plugin, PluginKey } from "@milkdown/kit/prose/state";
import { Decoration, DecorationSet } from "@milkdown/kit/prose/view";
import type { Node as ProseNode } from "@milkdown/kit/prose/model";
import { wrapIn } from "@milkdown/kit/prose/commands";

export const CALLOUT_KINDS = ["NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"] as const;
export type CalloutKindName = (typeof CALLOUT_KINDS)[number];

const MARKER = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\r?\n|$)/i;

type MdNode = { type: string; value?: string; children?: MdNode[] };

/** Takes `[!KIND]` off the front of a blockquote's first paragraph, and
 *  says which kind it was ("" for an ordinary quote). */
function takeMarker(quote: MdNode): { kind: string; children: MdNode[] } {
  const children = quote.children ?? [];
  const first = children[0];
  const text = first?.type === "paragraph" ? first.children?.[0] : undefined;
  if (!text || text.type !== "text" || !text.value) return { kind: "", children };
  const match = MARKER.exec(text.value);
  if (!match) return { kind: "", children };
  const rest = text.value.slice(match[0].length);
  let paragraphChildren = rest ? [{ ...text, value: rest }, ...(first.children ?? []).slice(1)] : (first.children ?? []).slice(1);
  // Milkdown turns the line break after the marker into a node of its own;
  // with the marker gone it would be an empty first line in the box.
  while (paragraphChildren[0]?.type === "break" || (paragraphChildren[0]?.type === "text" && !paragraphChildren[0].value?.trim())) {
    paragraphChildren = paragraphChildren.slice(1);
  }
  const remaining = paragraphChildren.length ? [{ ...first, children: paragraphChildren }, ...children.slice(1)] : children.slice(1);
  return { kind: match[1].toUpperCase(), children: remaining.length ? remaining : [{ type: "paragraph", children: [] }] };
}

/** A blockquote that may be a callout. */
export const calloutBlockquote = blockquoteSchema.extendSchema((previous) => (ctx) => {
  const base = previous(ctx);
  return {
    ...base,
    attrs: { kind: { default: "", validate: "string" } },
    toDOM: (node) => {
      const kind = String(node.attrs.kind || "");
      return kind
        ? ["blockquote", { class: `callout callout-${kind.toLowerCase()}`, "data-kind": kind }, 0]
        : ["blockquote", {}, 0];
    },
    parseDOM: [
      {
        tag: "blockquote",
        getAttrs: (dom) => ({ kind: (dom as HTMLElement).dataset.kind ?? "" }),
      },
    ],
    parseMarkdown: {
      match: base.parseMarkdown.match,
      runner: (state, node, type) => {
        const { kind, children } = takeMarker(node as unknown as MdNode);
        state.openNode(type, { kind }).next(children as never).closeNode();
      },
    },
    toMarkdown: {
      match: base.toMarkdown.match,
      runner: (state, node) => {
        state.openNode("blockquote");
        if (node.attrs.kind) {
          // Written as a paragraph of its own; tidyMarkdown pulls it back onto
          // the line above the text, where GitHub and DocuWaves expect it.
          state.openNode("paragraph").addNode("text", undefined, `[!${node.attrs.kind}]`).closeNode();
        }
        state.next(node.content).closeNode();
      },
    },
  };
});

/** Turns the quote around the cursor into a callout of this kind (or "" for
 *  a plain quote) -- or wraps the selection in one. */
export const setCalloutCommand = $command("SetCallout", (ctx) => (kind: string = "NOTE") => (state, dispatch) => {
  const type = calloutBlockquote.type(ctx);
  const { $from } = state.selection;
  for (let depth = $from.depth; depth > 0; depth--) {
    const node = $from.node(depth);
    if (node.type === type) {
      dispatch?.(state.tr.setNodeMarkup($from.before(depth), undefined, { ...node.attrs, kind }));
      return true;
    }
  }
  return wrapIn(type, { kind })(state, dispatch);
});

/** HTML comments DocuWaves gives a meaning, shown as what they mean. */
export const meaningfulHtml = htmlSchema.extendSchema((previous) => (ctx) => {
  const base = previous(ctx);
  return {
    ...base,
    toDOM: (node) => {
      const value = String(node.attrs.value ?? "");
      const snippet = /^<!--\s*snippet:\s*([\w./-]+)\s*-->$/i.exec(value.trim());
      const tabs = /^<!--\s*(\/?)tabs\s*-->$/i.exec(value.trim());
      const label = snippet
        ? `⧉ ${snippet[1]}`
        : tabs
          ? tabs[1]
            ? "⇥ tabs"
            : "⇤ tabs"
          : value;
      const kind = snippet ? "snippet" : tabs ? "tabs" : "html";
      return ["span", { "data-type": "html", "data-value": value, class: `visual-chip visual-chip-${kind}`, title: value }, label];
    },
  };
});

const VARIABLE = /(?<![$\\])\{\{\s*[A-Za-z0-9_.-]+\s*\}\}/g;

type Katex = typeof import("katex").default;
let katex: Katex | null = null;
let katexLoading: Promise<void> | null = null;

export function renderMath(target: HTMLElement, source: string, display: boolean) {
  const draw = () => {
    try {
      katex!.render(source, target, { displayMode: display, throwOnError: false });
    } catch {
      target.textContent = source;
    }
  };
  if (katex) {
    draw();
    return;
  }
  katexLoading ??= Promise.all([import("katex"), import("katex/dist/katex.min.css")]).then(([module]) => {
    katex = module.default;
  });
  void katexLoading.then(draw);
}

type MermaidApi = (typeof import("mermaid"))["default"];
let mermaidCounter = 0;

function renderMermaid(target: HTMLElement, source: string) {
  const id = `visual-mermaid-${++mermaidCounter}`;
  void import("mermaid").then(async ({ default: mermaid }: { default: MermaidApi }) => {
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
    try {
      await mermaid.parse(source);
      const { svg } = await mermaid.render(id, source);
      target.innerHTML = svg;
    } catch (err) {
      target.textContent = err instanceof Error ? err.message.split("\n")[0] : String(err);
      target.classList.add("visual-preview-error");
    }
  });
}

/** Decorations: variable chips, formula and diagram previews. */
function decorate(doc: ProseNode): DecorationSet {
  const decorations: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (node.type.name === "code_block") {
      if (String(node.attrs.language).toLowerCase() === "mermaid" && node.textContent.trim()) {
        const source = node.textContent;
        decorations.push(
          Decoration.widget(
            pos + node.nodeSize,
            () => {
              const box = document.createElement("div");
              box.className = "visual-preview visual-preview-diagram";
              box.contentEditable = "false";
              renderMermaid(box, source);
              return box;
            },
            { side: -1, key: `mermaid:${source}` },
          ),
        );
      }
      return false; // nothing inside code is a variable or a formula
    }
    if (!node.isText || node.marks.some((mark) => mark.type.name === "code")) return true;
    const text = node.text ?? "";
    for (const match of text.matchAll(VARIABLE)) {
      const from = pos + (match.index ?? 0);
      decorations.push(Decoration.inline(from, from + match[0].length, { class: "visual-chip visual-chip-variable" }));
    }
    return false;
  });
  return DecorationSet.create(doc, decorations);
}

const previewKey = new PluginKey("docuwaves-previews");

export const previews = $prose(
  () =>
    new Plugin({
      key: previewKey,
      state: {
        init: (_config, state) => decorate(state.doc),
        apply: (tr, old) => (tr.docChanged ? decorate(tr.doc) : old),
      },
      props: {
        decorations: (state) => previewKey.getState(state),
      },
    }),
);


// ---- Formulas ----

/** remark-math in Milkdown's own parser: `$…$` and `$$…$$` become math
 *  nodes before anything could read them as text. */
export const remarkMathPlugin = $remark("remarkMath", () => remarkMath);

export const mathBlockSchema = $nodeSchema("math_block", () => ({
  group: "block",
  atom: true,
  selectable: true,
  attrs: { value: { default: "", validate: "string" } },
  parseDOM: [{ tag: "div[data-type=math]", getAttrs: (dom) => ({ value: (dom as HTMLElement).dataset.value ?? "" }) }],
  toDOM: (node) => ["div", { "data-type": "math", "data-value": node.attrs.value, class: "visual-math visual-math-block" }],
  parseMarkdown: {
    match: ({ type }) => type === "math",
    runner: (state, node, type) => {
      state.addNode(type, { value: String(node.value ?? "") });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === "math_block",
    runner: (state, node) => {
      state.addNode("math", undefined, node.attrs.value);
    },
  },
}));

export const mathInlineSchema = $nodeSchema("math_inline", () => ({
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  attrs: { value: { default: "", validate: "string" } },
  parseDOM: [{ tag: "span[data-type=math]", getAttrs: (dom) => ({ value: (dom as HTMLElement).dataset.value ?? "" }) }],
  toDOM: (node) => ["span", { "data-type": "math", "data-value": node.attrs.value, class: "visual-math visual-math-inline" }],
  parseMarkdown: {
    match: ({ type }) => type === "inlineMath",
    runner: (state, node, type) => {
      state.addNode(type, { value: String(node.value ?? "") });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === "math_inline",
    runner: (state, node) => {
      state.addNode("inlineMath", undefined, node.attrs.value);
    },
  },
}));

/** A formula at the cursor (inline), from its LaTeX source. */
export const insertMathCommand = $command("InsertMath", (ctx) => (value: string = "") => (state, dispatch) => {
  if (!value) return false;
  dispatch?.(state.tr.replaceSelectionWith(mathInlineSchema.type(ctx).create({ value })).scrollIntoView());
  return true;
});
