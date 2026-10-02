/**
 * The visual editor's engine: Milkdown (ProseMirror underneath, MIT), set up
 * the way DocuWaves needs it. Separate from the React component so the
 * round-trip check -- and its tests -- use exactly the editor the author gets.
 *
 * Markdown in, Markdown out: Milkdown parses with remark, the same parser the
 * site renders with, and writes Markdown back with remark-stringify. The
 * settings below decide the SPELLING of what it writes -- `-` for bullets,
 * `*` for emphasis, fenced code -- once, for every page saved visually.
 */
import {
  Editor,
  defaultValueCtx,
  editorViewCtx,
  editorViewOptionsCtx,
  remarkPluginsCtx,
  remarkStringifyOptionsCtx,
  rootCtx,
} from "@milkdown/kit/core";
import { codeBlockSchema, commonmark } from "@milkdown/kit/preset/commonmark";
import { gfm, remarkGFMPlugin } from "@milkdown/kit/preset/gfm";
import { history } from "@milkdown/kit/plugin/history";
import { clipboard } from "@milkdown/kit/plugin/clipboard";
import { listener, listenerCtx } from "@milkdown/kit/plugin/listener";
import { upload, uploadConfig } from "@milkdown/kit/plugin/upload";
import { callCommand, getMarkdown, insert, replaceAll } from "@milkdown/kit/utils";
import type { Command } from "@milkdown/kit/prose/state";
import type { Node as ProseNode, Schema } from "@milkdown/kit/prose/model";
import { sameDocument } from "@/lib/markdownTree";
import {
  calloutBlockquote,
  insertMathCommand,
  mathBlockSchema,
  mathInlineSchema,
  meaningfulHtml,
  previews,
  remarkMathPlugin,
  renderMath,
  setCalloutCommand,
} from "./extensions";

export interface VisualOptions {
  root: HTMLElement;
  markdown: string;
  editable?: boolean;
  /** Called with the new Markdown after every change. */
  onChange?: (markdown: string) => void;
  /** Uploads an image and answers the Markdown path to it (`../assets/x.png`). */
  uploadImage?: (file: File) => Promise<string | null>;
  /** Turns a Markdown image path into an address the browser can load. */
  resolveImage?: (src: string) => string;
  /** Where the cursor is, for the toolbar: inside a table, inside a callout. */
  onSelection?: (where: { inTable: boolean; callout: string | null }) => void;
}

export interface VisualHandle {
  editor: Editor;
  markdown: () => string;
  setMarkdown: (markdown: string) => void;
  run: <T>(command: { key: unknown }, payload?: T) => void;
  /** A plain ProseMirror command (the table ones, say) on the current state. */
  prose: (command: Command) => void;
  /** Markdown parsed and put where the cursor is. */
  insertMarkdown: (markdown: string, inline?: boolean) => void;
  destroy: () => void;
}

const STRINGIFY = {
  bullet: "-" as const,
  emphasis: "*" as const,
  strong: "*" as const,
  fence: "`" as const,
  fences: true,
  rule: "-" as const,
  listItemIndent: "one" as const,
  incrementListMarker: true,
};

/** remark-stringify escapes the `[` of `> [!WARNING]` (to it, a bracket at
 *  the start of a line might begin a link). DocuWaves would still show the
 *  box, but GitHub would not, and nobody wants to read `\[!WARNING]`. */
export function tidyMarkdown(markdown: string): string {
  let fence: string | null = null;
  const lines = markdown.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const opening = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (opening) {
      if (fence === null) fence = opening[1][0].repeat(opening[1].length);
      else if (line.trim().startsWith(fence)) fence = null;
      out.push(line);
      continue;
    }
    if (fence !== null) {
      out.push(line);
      continue;
    }
    // A table's delimiter row the way most people write it: |---|:-:|
    if (/^\|(?:\s*:?-+:?\s*\|)+\s*$/.test(line)) {
      out.push(
        `|${line
          .trim()
          .slice(1, -1)
          .split("|")
          .map((cell) => cell.trim().replace(/-+/, "---"))
          .join("|")}|`,
      );
      continue;
    }
    const callout = /^((?:>[ \t]?)+)\\?\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/i.exec(line);
    if (callout) {
      out.push(`${callout[1]}[!${callout[2].toUpperCase()}]`);
      // The callout's text right below its marker, not after an empty quote
      // line: `> [!TIP]` / `> Text`, as GitHub writes it.
      if (/^(?:>[ \t]?)+$/.test(lines[i + 1] ?? "") && /^>/.test(lines[i + 2] ?? "")) i += 1;
      continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

type MdNode = { type: string; title?: string | null; children?: MdNode[] };

/** remark leaves a link's or image's missing title as null; Milkdown's
 *  schema insists on a string and, handed null, drops the image without a
 *  word. An empty title is written back as no title at all. */
function remarkStringTitles() {
  return (tree: MdNode) => {
    const walk = (node: MdNode) => {
      if ((node.type === "image" || node.type === "link") && node.title == null) node.title = "";
      node.children?.forEach(walk);
    };
    walk(tree);
  };
}

/** The code block, plus what follows its language on the fence line:
 *  ```python title="app/main.py" -- DocuWaves' file name for a block
 *  (see MarkdownView). Milkdown's own block keeps the language only and
 *  would drop the rest. Shown above the block, written back unchanged. */
const codeBlockWithMeta = codeBlockSchema.extendSchema((previous) => (ctx) => {
  const base = previous(ctx);
  return {
    ...base,
    attrs: { ...base.attrs, meta: { default: "", validate: "string" } },
    toDOM: (node) => {
      const [tag, attrs, ...rest] = base.toDOM!(node) as [string, Record<string, string>, ...unknown[]];
      const title = /title="([^"]*)"/.exec(String(node.attrs.meta ?? ""))?.[1];
      return [tag, { ...attrs, ...(title ? { "data-title": title } : {}) }, ...rest] as never;
    },
    parseMarkdown: {
      match: base.parseMarkdown.match,
      runner: (state, node, type) => {
        state.openNode(type, { language: String(node.lang ?? ""), meta: String(node.meta ?? "") });
        if (node.value) state.addText(String(node.value));
        state.closeNode();
      },
    },
    toMarkdown: {
      match: base.toMarkdown.match,
      runner: (state, node) => {
        state.addNode("code", undefined, node.content.firstChild?.text || "", {
          lang: node.attrs.language,
          meta: node.attrs.meta || null,
        });
      },
    },
  };
});

function mathView(
  node: ProseNode,
  view: import("@milkdown/kit/prose/view").EditorView,
  getPos: () => number | undefined,
  display: boolean,
) {
  const dom = document.createElement(display ? "div" : "span");
  dom.className = `visual-math ${display ? "visual-math-block" : "visual-math-inline"}`;
  dom.title = String(node.attrs.value);
  renderMath(dom, String(node.attrs.value), display);
  dom.addEventListener("dblclick", () => {
    if (!view.editable) return;
    const value = window.prompt("LaTeX", String(node.attrs.value));
    const pos = getPos();
    if (value === null || pos === undefined) return;
    view.dispatch(view.state.tr.setNodeMarkup(pos, undefined, { value }));
  });
  return { dom, ignoreMutation: () => true };
}

export async function createVisualEditor(options: VisualOptions): Promise<VisualHandle> {
  let suppress = true;
  const editor = await Editor.make()
    .config((ctx) => {
      ctx.set(rootCtx, options.root);
      ctx.set(defaultValueCtx, options.markdown);
      ctx.update(remarkStringifyOptionsCtx, (prev) => ({ ...prev, ...STRINGIFY }));
      ctx.update(remarkPluginsCtx, (prev) => [...prev, { plugin: remarkStringTitles, options: {} }]);
      // `| a | b |` rather than columns padded to the widest cell: padding
      // turns a one-word edit into a diff of the whole table.
      ctx.set(remarkGFMPlugin.options.key, { tablePipeAlign: false });
      ctx.update(editorViewOptionsCtx, (prev) => ({
        ...prev,
        editable: () => options.editable !== false,
        attributes: { class: "markdown-body visual-editor-body", spellcheck: "true" },
        nodeViews: {
          // Pages point at `../assets/x.png`, relative to the page's own
          // file; in the admin area that address means nothing, so the
          // picture is shown from where the site serves it. What is WRITTEN
          // back stays the relative path.
          image: (node: ProseNode) => {
            const img = document.createElement("img");
            const src = String(node.attrs.src ?? "");
            img.src = options.resolveImage ? options.resolveImage(src) : src;
            img.alt = String(node.attrs.alt ?? "");
            if (node.attrs.title) img.title = String(node.attrs.title);
            img.className = "visual-editor-image";
            return { dom: img };
          },
          // A formula shows rendered; a double click edits its LaTeX.
          math_block: (node: ProseNode, view, getPos) => mathView(node, view, getPos as () => number | undefined, true),
          math_inline: (node: ProseNode, view, getPos) => mathView(node, view, getPos as () => number | undefined, false),
        },
      }));
      ctx.get(listenerCtx).selectionUpdated((_ctx, selection) => {
        if (!options.onSelection) return;
        let inTable = false;
        let callout: string | null = null;
        const { $from } = selection;
        for (let depth = $from.depth; depth > 0; depth--) {
          const node = $from.node(depth);
          if (node.type.name === "table") inTable = true;
          if (node.type.name === "blockquote" && callout === null) callout = String(node.attrs.kind ?? "");
        }
        options.onSelection({ inTable, callout });
      });
      ctx.get(listenerCtx).markdownUpdated((_ctx, markdown, previous) => {
        if (!suppress && markdown !== previous) options.onChange?.(tidyMarkdown(markdown));
      });
      if (options.uploadImage) {
        const uploadImage = options.uploadImage;
        ctx.update(uploadConfig.key, (prev) => ({
          ...prev,
          enableHtmlFileUploader: false,
          uploader: async (files: FileList, schema: Schema) => {
            const nodes: ProseNode[] = [];
            for (const file of Array.from(files)) {
              if (!file.type.startsWith("image/")) continue;
              const path = await uploadImage(file);
              const node = path ? schema.nodes.image.createAndFill({ src: path, alt: "" }) : null;
              if (node) nodes.push(node);
            }
            return nodes;
          },
        }));
      }
    })
    .use(commonmark)
    .use(codeBlockWithMeta)
    .use(calloutBlockquote)
    .use(meaningfulHtml)
    .use(setCalloutCommand)
    .use(remarkMathPlugin)
    .use(mathBlockSchema)
    .use(mathInlineSchema)
    .use(insertMathCommand)
    .use(previews)
    .use(gfm)
    .use(history)
    .use(clipboard)
    .use(listener)
    .use(upload)
    .create();
  suppress = false;

  return {
    editor,
    markdown: () => tidyMarkdown(editor.action(getMarkdown())),
    setMarkdown: (markdown: string) => {
      suppress = true;
      editor.action(replaceAll(markdown));
      suppress = false;
    },
    run: (command, payload) => {
      editor.action(callCommand(command.key as never, payload as never));
    },
    prose: (command) => {
      editor.action((ctx) => {
        const view = ctx.get(editorViewCtx);
        command(view.state, view.dispatch, view);
        view.focus();
      });
    },
    insertMarkdown: (markdown, inline = false) => {
      editor.action(insert(markdown, inline));
    },
    destroy: () => {
      void editor.destroy();
    },
  };
}

/** What the visual editor would write back for this Markdown, unedited. */
export async function visualRoundTrip(markdown: string): Promise<string> {
  const root = document.createElement("div");
  const handle = await createVisualEditor({ root, markdown, editable: false });
  try {
    return handle.markdown();
  } finally {
    handle.destroy();
  }
}

/** Whether a page can be edited visually without losing anything. */
export async function editableVisually(markdown: string): Promise<boolean> {
  try {
    return sameDocument(markdown, await visualRoundTrip(markdown));
  } catch {
    return false;
  }
}
