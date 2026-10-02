/**
 * The visual editor: write the page as it will look, with a toolbar, and
 * Markdown is what gets saved (see milkdown.ts for the engine and why a page
 * only ever opens here when nothing in it would be lost).
 *
 * Loaded on demand (React.lazy in the page editor): ProseMirror and Milkdown
 * are a few hundred kilobytes nobody reading the docs should download.
 */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent } from "react";
import {
  Bold,
  Code,
  Heading2,
  Heading3,
  ImagePlus,
  Italic,
  Link2,
  List,
  ListOrdered,
  Minus,
  Pilcrow,
  Quote,
  Redo2,
  SquareCode,
  Strikethrough,
  Table,
  Undo2,
} from "lucide-react";
import {
  createCodeBlockCommand,
  insertHrCommand,
  insertImageCommand,
  toggleEmphasisCommand,
  toggleInlineCodeCommand,
  toggleLinkCommand,
  toggleStrongCommand,
  turnIntoTextCommand,
  wrapInBlockquoteCommand,
  wrapInBulletListCommand,
  wrapInHeadingCommand,
  wrapInOrderedListCommand,
} from "@milkdown/kit/preset/commonmark";
import { insertTableCommand, toggleStrikethroughCommand } from "@milkdown/kit/preset/gfm";
import { redoCommand, undoCommand } from "@milkdown/kit/plugin/history";
import "@milkdown/kit/prose/view/style/prosemirror.css";
import "@milkdown/kit/prose/tables/style/tables.css";
import { useI18n } from "@/lib/i18n";
import { createVisualEditor, type VisualHandle } from "./milkdown";

export interface VisualEditorHandle {
  insertImage: (markdownPath: string) => void;
  focus: () => void;
  /** The text as it is RIGHT NOW. Milkdown reports changes a moment after
   *  the typing stops, so a save straight after a keystroke has to ask. */
  markdown: () => string | null;
}

interface Props {
  value: string;
  readOnly: boolean;
  onChange: (markdown: string) => void;
  uploadImage: (file: File) => Promise<string | null>;
  resolveImage: (src: string) => string;
  /** Ctrl/⌘+S and the like, handled by the page editor. */
  onKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void;
}

const VisualEditor = forwardRef<VisualEditorHandle, Props>(function VisualEditor(
  { value, readOnly, onChange, uploadImage, resolveImage, onKeyDown },
  ref,
) {
  const { t } = useI18n();
  const rootRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<VisualHandle | null>(null);
  // What the editor last wrote out -- so a value coming back from the parent
  // is told apart from one the parent changed itself (a restored draft, a
  // template, an image inserted from the panel below).
  const lastEmitted = useRef(value);
  const latest = useRef({ onChange, uploadImage, resolveImage });
  latest.current = { onChange, uploadImage, resolveImage };
  const [ready, setReady] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    let created: VisualHandle | null = null;
    createVisualEditor({
      root: rootRef.current!,
      markdown: value,
      editable: !readOnly,
      onChange: (markdown) => {
        lastEmitted.current = markdown;
        latest.current.onChange(markdown);
      },
      uploadImage: (file) => latest.current.uploadImage(file),
      resolveImage: (src) => latest.current.resolveImage(src),
    }).then((handle) => {
      if (!alive) {
        handle.destroy();
        return;
      }
      created = handle;
      handleRef.current = handle;
      setReady(true);
    });
    return () => {
      alive = false;
      created?.destroy();
      handleRef.current = null;
      if (rootRef.current) rootRef.current.innerHTML = "";
    };
    // The editor is made once per mount; text changes flow in below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly]);

  useEffect(() => {
    if (!ready || value === lastEmitted.current) return;
    lastEmitted.current = value;
    handleRef.current?.setMarkdown(value);
  }, [value, ready]);

  useImperativeHandle(ref, () => ({
    insertImage: (path) => handleRef.current?.run(insertImageCommand, { src: path, alt: "" }),
    focus: () => handleRef.current?.editor && (rootRef.current?.querySelector(".ProseMirror") as HTMLElement)?.focus(),
    markdown: () => {
      const handle = handleRef.current;
      if (!handle) return null;
      const markdown = handle.markdown();
      lastEmitted.current = markdown;
      return markdown;
    },
  }));

  const run = <T,>(command: { key: unknown }, payload?: T) => () => handleRef.current?.run(command, payload);

  function onLink() {
    const href = window.prompt(t("visual.linkPrompt"), "https://");
    if (href && href.trim() && href.trim() !== "https://") {
      handleRef.current?.run(toggleLinkCommand, { href: href.trim() });
    }
  }

  async function onImageFile(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    const path = await uploadImage(file);
    if (path) handleRef.current?.run(insertImageCommand, { src: path, alt: "" });
    if (fileInput.current) fileInput.current.value = "";
  }

  const groups: { label: string; icon: typeof Bold; action: () => void }[][] = [
    [
      { label: t("visual.undo"), icon: Undo2, action: run(undoCommand) },
      { label: t("visual.redo"), icon: Redo2, action: run(redoCommand) },
    ],
    [
      { label: t("visual.paragraph"), icon: Pilcrow, action: run(turnIntoTextCommand) },
      { label: t("visual.heading2"), icon: Heading2, action: run(wrapInHeadingCommand, 2) },
      { label: t("visual.heading3"), icon: Heading3, action: run(wrapInHeadingCommand, 3) },
    ],
    [
      { label: t("visual.bold"), icon: Bold, action: run(toggleStrongCommand) },
      { label: t("visual.italic"), icon: Italic, action: run(toggleEmphasisCommand) },
      { label: t("visual.strike"), icon: Strikethrough, action: run(toggleStrikethroughCommand) },
      { label: t("visual.inlineCode"), icon: Code, action: run(toggleInlineCodeCommand) },
      { label: t("visual.link"), icon: Link2, action: onLink },
    ],
    [
      { label: t("visual.bulletList"), icon: List, action: run(wrapInBulletListCommand) },
      { label: t("visual.orderedList"), icon: ListOrdered, action: run(wrapInOrderedListCommand) },
      { label: t("visual.quote"), icon: Quote, action: run(wrapInBlockquoteCommand) },
      { label: t("visual.codeBlock"), icon: SquareCode, action: run(createCodeBlockCommand) },
      { label: t("visual.table"), icon: Table, action: run(insertTableCommand, { row: 3, col: 3 }) },
      { label: t("visual.rule"), icon: Minus, action: run(insertHrCommand) },
      { label: t("visual.image"), icon: ImagePlus, action: () => fileInput.current?.click() },
    ],
  ];

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
      {!readOnly && (
        <div
          role="toolbar"
          aria-label={t("visual.toolbar")}
          className="sticky top-0 z-10 flex flex-wrap items-center gap-1 border-b border-[var(--border)] bg-[var(--surface)] px-2 py-1.5"
        >
          {groups.map((group, i) => (
            <div key={i} className="flex items-center gap-0.5 border-r border-[var(--border)] pr-1 last:border-r-0">
              {group.map(({ label, icon: Icon, action }) => (
                <button
                  key={label}
                  type="button"
                  title={label}
                  aria-label={label}
                  disabled={!ready}
                  // mousedown, not click: a click first moves the focus out
                  // of the text, and the command would land on no selection.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    action();
                  }}
                  className="rounded p-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)] disabled:opacity-40"
                >
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          ))}
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => void onImageFile(e.target.files)}
          />
        </div>
      )}
      <div ref={rootRef} className="visual-editor min-h-[420px] px-4 py-3" onKeyDown={onKeyDown} />
      {!ready && <p className="px-4 pb-3 text-sm text-[var(--muted)]">{t("visual.loading")}</p>}
    </div>
  );
});

export default VisualEditor;
