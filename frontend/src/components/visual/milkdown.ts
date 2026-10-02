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
import { callCommand, getMarkdown, replaceAll } from "@milkdown/kit/utils";
import type { Node as ProseNode, Schema } from "@milkdown/kit/prose/model";
import { sameDocument } from "@/lib/markdownTree";

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
}

export interface VisualHandle {
  editor: Editor;
  markdown: () => string;
  setMarkdown: (markdown: string) => void;
  run: <T>(command: { key: unknown }, payload?: T) => void;
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
  return markdown
    .split("\n")
    .map((line) => {
      const opening = /^ {0,3}(`{3,}|~{3,})/.exec(line);
      if (opening) {
        if (fence === null) fence = opening[1][0].repeat(opening[1].length);
        else if (line.trim().startsWith(fence)) fence = null;
        return line;
      }
      if (fence !== null) return line;
      // A table's delimiter row the way most people write it: |---|:-:|
      if (/^\|(?:\s*:?-+:?\s*\|)+\s*$/.test(line)) {
        return `|${line
          .trim()
          .slice(1, -1)
          .split("|")
          .map((cell) => cell.trim().replace(/-+/, "---"))
          .join("|")}|`;
      }
      return line.replace(/^((?:>[ \t]?)+)\\\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/i, "$1[!$2]");
    })
    .join("\n");
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
        },
      }));
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
