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

Markdown shortcuts work while typing, too: `## ` at the start of a line
becomes a heading, `- ` a list, `> ` a quote, ` ``` ` a code block.
**⌘/Ctrl+S** saves, as in the Markdown editor.

Images are uploaded into the project like any other
[image](/p/docuwaves/pages/images) and shown in the editor as they will look.

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

> [!NOTE]
> Callouts, tabs, snippets and variables are kept exactly as written, and
> shown as text for now. Proper boxes, tabs and chips for them in the visual
> editor come next.
