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
  AlignCenter,
  AlignLeft,
  AlignRight,
  ArrowDownToLine,
  ArrowLeftToLine,
  ArrowRightToLine,
  ArrowUpToLine,
  Bold,
  Braces,
  Code,
  Columns3,
  MessageSquareWarning,
  Rows3,
  Sigma,
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
import { insertTableCommand, setAlignCommand, toggleStrikethroughCommand } from "@milkdown/kit/preset/gfm";
import {
  addColumnAfter,
  addColumnBefore,
  addRowAfter,
  addRowBefore,
  deleteColumn,
  deleteRow,
} from "@milkdown/kit/prose/tables";
import { redoCommand, undoCommand } from "@milkdown/kit/plugin/history";
import "@milkdown/kit/prose/view/style/prosemirror.css";
import "@milkdown/kit/prose/tables/style/tables.css";
import { useI18n } from "@/lib/i18n";
import { createVisualEditor, type VisualHandle } from "./milkdown";
import { CALLOUT_KINDS, insertMathCommand, setCalloutCommand } from "./extensions";

/** What can be inserted with the { } button: variable names and snippets. */
export interface Insertables {
  variables: string[];
  snippets: string[];
}

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
  /** Loads the variables and snippets of this project and version. */
  insertables?: () => Promise<Insertables>;
}

const VisualEditor = forwardRef<VisualEditorHandle, Props>(function VisualEditor(
  { value, readOnly, onChange, uploadImage, resolveImage, onKeyDown, insertables },
  ref,
) {
  const { t, lang } = useI18n();
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
  // Where the cursor is: the table tools appear inside a table, and the
  // callout picker shows the kind of the box the cursor is in.
  const [where, setWhere] = useState<{ inTable: boolean; callout: string | null }>({ inTable: false, callout: null });
  const [insertMenu, setInsertMenu] = useState<Insertables | "loading" | null>(null);

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
      onSelection: setWhere,
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

  async function toggleInsertMenu() {
    if (insertMenu) {
      setInsertMenu(null);
      return;
    }
    setInsertMenu("loading");
    try {
      setInsertMenu(insertables ? await insertables() : { variables: [], snippets: [] });
    } catch {
      setInsertMenu({ variables: [], snippets: [] });
    }
  }

  function insertVariable(name: string) {
    handleRef.current?.insertMarkdown(`{{${name}}}`, true);
    setInsertMenu(null);
  }

  function insertSnippet(name: string) {
    handleRef.current?.insertMarkdown(`<!-- snippet: ${name} -->`);
    setInsertMenu(null);
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
      {
        label: t("visual.formula"),
        icon: Sigma,
        action: () => {
          const latex = window.prompt(t("visual.formulaPrompt"), "");
          if (latex && latex.trim()) handleRef.current?.run(insertMathCommand, latex.trim());
        },
      },
    ],
  ];

  const prose = (command: Parameters<VisualHandle["prose"]>[0]) => () => handleRef.current?.prose(command);
  const tableTools: { label: string; icon: typeof Bold; action: () => void }[] = [
    { label: t("visual.rowAbove"), icon: ArrowUpToLine, action: prose(addRowBefore) },
    { label: t("visual.rowBelow"), icon: ArrowDownToLine, action: prose(addRowAfter) },
    { label: t("visual.colLeft"), icon: ArrowLeftToLine, action: prose(addColumnBefore) },
    { label: t("visual.colRight"), icon: ArrowRightToLine, action: prose(addColumnAfter) },
    { label: t("visual.deleteRow"), icon: Rows3, action: prose(deleteRow) },
    { label: t("visual.deleteCol"), icon: Columns3, action: prose(deleteColumn) },
    { label: t("visual.alignLeft"), icon: AlignLeft, action: run(setAlignCommand, "left") },
    { label: t("visual.alignCenter"), icon: AlignCenter, action: run(setAlignCommand, "center") },
    { label: t("visual.alignRight"), icon: AlignRight, action: run(setAlignCommand, "right") },
  ];
  const calloutLabels: Record<string, string> = {
    NOTE: t("callout.note"),
    TIP: t("callout.tip"),
    IMPORTANT: t("callout.important"),
    WARNING: t("callout.warning"),
    CAUTION: t("callout.caution"),
  };

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
          <div className="flex items-center gap-1 border-r border-[var(--border)] pr-1">
            <MessageSquareWarning className="h-4 w-4 text-[var(--muted)]" aria-hidden="true" />
            <select
              aria-label={t("visual.callout")}
              title={t("visual.callout")}
              disabled={!ready}
              value={where.callout ?? "-"}
              onChange={(e) => {
                const kind = e.target.value;
                if (kind !== "-") handleRef.current?.run(setCalloutCommand, kind === "QUOTE" ? "" : kind);
              }}
              className="h-7 rounded border border-[var(--border)] bg-[var(--surface)] px-1 text-xs"
            >
              <option value="-">{t("visual.callout")}</option>
              {CALLOUT_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {calloutLabels[kind]}
                </option>
              ))}
              <option value="">{t("visual.plainQuote")}</option>
            </select>
          </div>
          <div className="relative">
            <button
              type="button"
              title={t("visual.insertVariable")}
              aria-label={t("visual.insertVariable")}
              aria-expanded={insertMenu !== null}
              disabled={!ready}
              onMouseDown={(event) => {
                event.preventDefault();
                void toggleInsertMenu();
              }}
              className="rounded p-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)] disabled:opacity-40"
            >
              <Braces className="h-4 w-4" />
            </button>
            {insertMenu !== null && (
              <div className="absolute right-0 top-full z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2 text-sm shadow-lg">
                {insertMenu === "loading" && <p className="text-[var(--muted)]">…</p>}
                {insertMenu !== "loading" && (
                  <>
                    <p className="px-1 text-xs font-medium text-[var(--muted)]">{t("visual.variables")}</p>
                    {insertMenu.variables.length === 0 && <p className="px-1 text-xs text-[var(--muted)]">—</p>}
                    {insertMenu.variables.map((name) => (
                      <button
                        key={`v:${name}`}
                        type="button"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          insertVariable(name);
                        }}
                        className="block w-full rounded px-1 py-0.5 text-left font-mono text-xs hover:bg-[var(--surface-2)]"
                      >
                        {`{{${name}}}`}
                      </button>
                    ))}
                    <p className="mt-2 px-1 text-xs font-medium text-[var(--muted)]">{t("visual.snippets")}</p>
                    {insertMenu.snippets.length === 0 && <p className="px-1 text-xs text-[var(--muted)]">—</p>}
                    {insertMenu.snippets.map((name) => (
                      <button
                        key={`s:${name}`}
                        type="button"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          insertSnippet(name);
                        }}
                        className="block w-full rounded px-1 py-0.5 text-left text-xs hover:bg-[var(--surface-2)]"
                      >
                        ⧉ {name}
                      </button>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
          {where.inTable && (
            <div className="flex items-center gap-0.5 border-l border-[var(--border)] pl-1" aria-label={t("visual.tableTools")}>
              {tableTools.map(({ label, icon: Icon, action }) => (
                <button
                  key={label}
                  type="button"
                  title={label}
                  aria-label={label}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    action();
                  }}
                  className="rounded p-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]"
                >
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          )}
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => void onImageFile(e.target.files)}
          />
        </div>
      )}
      {/* lang: the callout boxes' labels follow the interface language
          (see the .visual-editor :lang() rules in index.css). */}
      <div ref={rootRef} lang={lang} className="visual-editor min-h-[420px] px-4 py-3" onKeyDown={onKeyDown} />
      {!ready && <p className="px-4 pb-3 text-sm text-[var(--muted)]">{t("visual.loading")}</p>}
    </div>
  );
});

export default VisualEditor;
