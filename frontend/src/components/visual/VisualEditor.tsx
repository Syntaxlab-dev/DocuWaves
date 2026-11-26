/**
 * The visual editor: write the page as it will look, with a toolbar, and
 * Markdown is what gets saved (see milkdown.ts for the engine and why a page
 * only ever opens here when nothing in it would be lost).
 *
 * Loaded on demand (React.lazy in the page editor): ProseMirror and Milkdown
 * are a few hundred kilobytes nobody reading the docs should download.
 */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent } from "react";
import type { Command } from "@milkdown/kit/prose/state";
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
  PanelsTopLeft,
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
import { createVisualEditor, type VisualHandle, type VisualWhere } from "./milkdown";
import { CALLOUT_KINDS, insertMathCommand, insertTabsCommand, setCalloutCommand } from "./extensions";

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
  uploadImage: (file: File, edit?: boolean) => Promise<string | null>;
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
  const [where, setWhere] = useState<VisualWhere>({ inTable: false, callout: null, selected: null, slash: null });
  // The floating parts are placed against this box, so they scroll with it.
  const frame = useRef<HTMLDivElement>(null);
  const [slashActive, setSlashActive] = useState(0);
  // Escape closes the slash menu for that "/" only; typing a new one opens it.
  const [slashClosedAt, setSlashClosedAt] = useState<number | null>(null);
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
      onSelection: (next) => {
        setWhere(next);
        if (!next.slash) setSlashClosedAt(null);
      },
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

  function formula() {
    const latex = window.prompt(t("visual.formulaPrompt"), "");
    if (latex && latex.trim()) handleRef.current?.run(insertMathCommand, latex.trim());
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
      { label: t("visual.tabs"), icon: PanelsTopLeft, action: run(insertTabsCommand, ["Tab 1", "Tab 2"]) },
      { label: t("visual.formula"), icon: Sigma, action: formula },
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

  /** The blocks the slash menu offers: what the toolbar inserts, and the
   *  callout boxes. `words` are what it is also found by, in English, so
   *  "/h2" and "/note" work whatever the interface language. */
  const slashItems: { label: string; words: string; icon: typeof Bold; action: () => void }[] = [
    { label: t("visual.paragraph"), words: "text paragraph p", icon: Pilcrow, action: run(turnIntoTextCommand) },
    { label: t("visual.heading2"), words: "heading h2 title", icon: Heading2, action: run(wrapInHeadingCommand, 2) },
    { label: t("visual.heading3"), words: "heading h3 subtitle", icon: Heading3, action: run(wrapInHeadingCommand, 3) },
    { label: t("visual.bulletList"), words: "list bullet ul", icon: List, action: run(wrapInBulletListCommand) },
    { label: t("visual.orderedList"), words: "list numbered ordered ol", icon: ListOrdered, action: run(wrapInOrderedListCommand) },
    { label: t("visual.quote"), words: "quote blockquote", icon: Quote, action: run(wrapInBlockquoteCommand) },
    ...CALLOUT_KINDS.map((kind) => ({
      label: calloutLabels[kind],
      words: `callout ${kind.toLowerCase()}`,
      icon: MessageSquareWarning,
      action: () => {
        handleRef.current?.run(wrapInBlockquoteCommand);
        handleRef.current?.run(setCalloutCommand, kind);
      },
    })),
    { label: t("visual.codeBlock"), words: "code block pre", icon: SquareCode, action: run(createCodeBlockCommand) },
    { label: t("visual.table"), words: "table grid", icon: Table, action: run(insertTableCommand, { row: 3, col: 3 }) },
    { label: t("visual.image"), words: "image picture img", icon: ImagePlus, action: () => fileInput.current?.click() },
    { label: t("visual.tabs"), words: "tabs", icon: PanelsTopLeft, action: run(insertTabsCommand, ["Tab 1", "Tab 2"]) },
    { label: t("visual.formula"), words: "formula math latex", icon: Sigma, action: formula },
    { label: t("visual.rule"), words: "rule divider hr line", icon: Minus, action: run(insertHrCommand) },
  ];
  const slash = where.slash && where.slash.from !== slashClosedAt && !readOnly ? where.slash : null;
  const slashQuery = slash?.query.toLowerCase() ?? "";
  const slashMatches = slash
    ? slashItems
        .map((item) => {
          const words = `${item.label} ${item.words}`.toLowerCase().split(/\s+/);
          // A word that starts with what was typed beats one that merely holds it.
          const rank = words.some((w) => w.startsWith(slashQuery)) ? 0 : words.some((w) => w.includes(slashQuery)) ? 1 : 2;
          return { item, rank };
        })
        .filter(({ rank }) => rank < 2)
        .sort((a, b) => a.rank - b.rank)
        .map(({ item }) => item)
    : [];
  const slashIndex = Math.min(slashActive, Math.max(0, slashMatches.length - 1));

  /** Takes the "/word" out, then does what was picked in its place. */
  function pickSlash(item: (typeof slashItems)[number]) {
    if (!slash) return;
    const { from, to } = slash;
    const remove: Command = (state, dispatch) => {
      dispatch?.(state.tr.delete(from, to));
      return true;
    };
    handleRef.current?.prose(remove);
    item.action();
    setSlashActive(0);
  }

  function onSlashKeys(event: KeyboardEvent<HTMLDivElement>) {
    if (!slash) return;
    const keys: Record<string, () => void> = {
      ArrowDown: () => setSlashActive((slashIndex + 1) % Math.max(1, slashMatches.length)),
      ArrowUp: () => setSlashActive((slashIndex - 1 + slashMatches.length) % Math.max(1, slashMatches.length)),
      Enter: () => slashMatches[slashIndex] && pickSlash(slashMatches[slashIndex]),
      Tab: () => slashMatches[slashIndex] && pickSlash(slashMatches[slashIndex]),
      Escape: () => setSlashClosedAt(slash.from),
    };
    const handle = keys[event.key];
    if (!handle || (event.key !== "Escape" && slashMatches.length === 0)) return;
    // Before ProseMirror sees it: Enter here picks, it doesn't split the line.
    event.preventDefault();
    event.stopPropagation();
    handle();
  }

  /** A position on screen, as a place inside the frame. */
  const inFrame = (rect: { top: number; bottom: number; left: number }) => {
    const box = frame.current?.getBoundingClientRect();
    return box ? { top: rect.top - box.top, bottom: rect.bottom - box.top, left: rect.left - box.left, width: box.width } : null;
  };
  const slashAt = slash ? inFrame(slash.at) : null;
  const selectedAt = where.selected && !readOnly ? inFrame(where.selected) : null;
  const formatBar = groups[2];

  return (
    <div ref={frame} className="relative rounded-lg border border-[var(--border)] bg-[var(--surface)]">
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
      <div
        ref={rootRef}
        lang={lang}
        className="visual-editor min-h-[420px] px-4 py-3"
        onKeyDown={onKeyDown}
        onKeyDownCapture={onSlashKeys}
        onBlur={(event) => {
          // Leaving the text for something outside the editor: the floating
          // parts go with it (their own buttons keep the focus where it is).
          if (!frame.current?.contains(event.relatedTarget as Node | null)) {
            setWhere((w) => ({ ...w, selected: null, slash: null }));
          }
        }}
      />
      {selectedAt && !slash && (
        <div
          role="toolbar"
          aria-label={t("visual.formatBar")}
          data-format-bar
          // Above the selection, or below it on the first lines, where
          // above would cover the toolbar.
          className={`absolute z-20 flex -translate-x-1/2 items-center gap-0.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-0.5 shadow-lg ${
            selectedAt.top < 140 ? "" : "-translate-y-full"
          }`}
          style={{
            top: selectedAt.top < 140 ? selectedAt.bottom + 6 : selectedAt.top - 6,
            left: Math.min(Math.max(selectedAt.left, 72), selectedAt.width - 72),
          }}
        >
          {formatBar.map(({ label, icon: Icon, action }) => (
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
      {slash && slashAt && (
        <div
          role="listbox"
          aria-label={t("visual.slashMenu")}
          className="absolute z-20 max-h-72 w-60 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1 text-sm shadow-lg"
          style={{ top: slashAt.bottom + 4, left: Math.min(slashAt.left, Math.max(0, slashAt.width - 248)) }}
        >
          {slashMatches.length === 0 && <p className="px-2 py-1.5 text-[var(--muted)]">{t("visual.slashEmpty")}</p>}
          {slashMatches.map((item, i) => (
            <button
              key={item.label}
              type="button"
              role="option"
              aria-selected={i === slashIndex}
              onMouseEnter={() => setSlashActive(i)}
              onMouseDown={(event) => {
                event.preventDefault();
                pickSlash(item);
              }}
              className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left ${
                i === slashIndex ? "bg-[var(--accent-soft)] text-[var(--ink)]" : "text-[var(--muted)]"
              }`}
            >
              <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {item.label}
            </button>
          ))}
        </div>
      )}
      {!ready && <p className="px-4 pb-3 text-sm text-[var(--muted)]">{t("visual.loading")}</p>}
    </div>
  );
});

export default VisualEditor;
