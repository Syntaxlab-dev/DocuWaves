---
order: 3
published: true
title: The visual editor
---

Write a page the way it will look — headings, bold text, lists, tables and
images, with a toolbar — or write Markdown directly. Both edit the same file:
**what is saved is always Markdown**, so the content repository, Git history,
[docs-as-code](/p/docuwaves/pages/docs-as-code) and the
[import](/p/docuwaves/pages/importing-a-zip) work exactly the same either way.

## Switching

**Visual | Markdown** next to the editor's tabs. New authors start in
**Visual**; whichever you pick is remembered in your browser for every page.
Switch at any time, even halfway through a page — it is the same text.

## What the toolbar does

| | |
|---|---|
| Undo, redo | also ⌘/Ctrl+Z and ⌘/Ctrl+Shift+Z |
| Normal text, heading, subheading | |
| Bold, italic, strikethrough, inline code | ⌘/Ctrl+B and ⌘/Ctrl+I work too |
| Link | asks for the address |
| Bulleted and numbered list, quote | |
| Code block | keeps its language and [file name](/p/docuwaves/pages/callouts-and-code-blocks) |
| Table | 3 × 3 to start; Tab moves to the next cell |
| Divider | |
| Upload an image | also by pasting a screenshot or dropping a file |
| Formula | asks for the LaTeX source |
| Tabs | inserts a [tab group](/p/docuwaves/pages/tabs) with two tabs |
| **Callout** | turns the paragraph into a box of that kind — or changes the kind of the box the cursor is in |
| **{ }** | inserts one of the project's [variables or snippets](/p/docuwaves/pages/snippets-and-variables) |

Inside a table, a second row of tools appears: insert a row above or below,
a column left or right, delete the row or column, and align the column left,
centred or right.

Markdown shortcuts work while typing, too: `## ` at the start of a line
becomes a heading, `- ` a list, `> ` a quote, ` ``` ` a code block.
**⌘/Ctrl+S** saves, as in the Markdown editor.

Images are uploaded into the project like any other
[image](/p/docuwaves/pages/images) and shown in the editor as they will look.

## DocuWaves' own blocks

- **Callouts** are shown as the coloured boxes readers see, labelled in your
  language, and saved as GitHub's `> [!WARNING]`.
- **Variables** (`{{port}}`) and **snippets** appear as chips. They stay
  exactly what they are in the file; what they stand for is managed under
  **Snippets & variables**.
- **Formulas** — `$…$` in a sentence, `$$…$$` on their own — are shown
  rendered. Double-click one to edit its LaTeX.
- **Diagrams** — ` ```mermaid ` blocks — keep their source editable,
  with the drawing right below it, updated as you type.
- **Tabs** are tabs: click a tab to see its content, double-click it to
  rename it, **+** adds one, **×** removes the one shown. A group the site
  would not show as tabs (no heading first, never closed) is left exactly as
  written.

## Nothing is lost — or the page opens in Markdown

A visual editor has to turn every page back into Markdown, and whatever it
does not understand it could drop. So before a page opens visually, DocuWaves
converts it to the visual editor and back, and compares the result with the
original — not as text, but as the document a reader sees. If anything would
be lost, the page opens in the **Markdown editor** instead, with a note
saying why. You can always edit it there.

What may change when a page is saved visually is **spelling, not content**:
`-` for every bullet, `*` for emphasis, a blank line between blocks. Pages
written in that style — like these docs — come back character for
character.

