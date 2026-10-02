---
order: 2
published: true
title: Printing and PDF
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
- **A whole category or project at once is not supported.** Print the pages
  you need. Stitching a book together is a job for a tool built for it, and
  your content is Markdown in a repository, which is what such tools take.
- **Images print** at whatever resolution they were uploaded at.
- **Mermaid diagrams print** as drawn, since they are rendered into the page
  rather than loaded as pictures.
