---
order: 2
published: true
title: Printing, PDF and EPUB
---

Print any page from the browser, or save it as PDF from the same dialog —
or print a **whole manual** at once. There is no export service, because the
browser's own print dialog already does both and produces a file that opens
everywhere.

## A whole manual as PDF

**PDF / print** on a project page — or **Chapter as PDF** on a category
page — opens a print view of all of it: a cover with the project, version
and date, a table of contents, and every published page on a fresh sheet,
in the sidebar's order. The button becomes active once every diagram has
rendered and every image has loaded; then choose **Save as PDF** in the
print dialog. The contents and all links stay clickable in the PDF, and
[tabs](/p/docuwaves/pages/tabs) print with every tab shown under its name.

The browser does the PDF on purpose: nothing to install or run on the
server, no fonts to ship, and diagrams, formulas and code come out exactly as
the site renders them, because it is the site's own rendering.

## EPUB and Markdown

Next to **PDF / print**, a project page offers two downloads of the same
content — every published page of the version you are reading, in your
language, in the sidebar's order:

- **EPUB** — an e-book for an e-reader, a tablet or reading offline: a table
  of contents per category, the pages with their images, callouts and
  tables, and links between pages that work inside the book.
- **Markdown (zip)** — each page as a Markdown file with its title, the
  images next to them and an `index.md` listing everything, for another
  tool. Links between pages point at the files.

Snippets and variables are filled in, as on the site. Diagrams and formulas
stay as their source text: drawing them takes the site's JavaScript. A
private project is only offered to someone signed in who may read it. For a
copy of the whole instance with its history, use the export under
**Diagnostics** instead.

## What the printed page looks like

The screen furniture goes: the header, the sidebar, the contents column, the
footer, every button, the feedback prompt and the chat panel. What is left
is the article, laid out for paper — dark text on white regardless of
whether you were reading in dark mode, and links shown with their addresses
so a printed reference is followable.

Collapsed `<details>` blocks in the text print **open**. On paper there is
nothing to click, so a folded section would just be missing.

## Where it came from, and when

At the foot of every printout, and nowhere on screen, is a block carrying
the page's address, the date it was printed and the date the page was last
updated — plus a **QR code** of the address.

That block is the whole point of printing support. A page found on a desk in
six months otherwise says nothing about where it came from or whether it is
still true. The QR code is there so getting back to the live version is a
phone camera rather than retyping a URL with three path segments in it.

The code is drawn in the page itself, as vector paths — it is not fetched
from a rendering service, so an instance with no internet access prints one
just as well, and printing a page phones nobody.

## Practical notes

- **Print from the reading page**, not the editor's preview tab.
- **Images print** at whatever resolution they were uploaded at.
- **Mermaid diagrams print** as drawn, since they are rendered into the page
  rather than loaded as pictures.
