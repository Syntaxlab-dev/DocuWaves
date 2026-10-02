---
order: 2
published: true
title: Importing from Notion
---

In Notion: **Settings → Export content** (or **… → Export** on a page), with
the format **Markdown & CSV** and sub-pages included. Upload the ZIP Notion
gives you as it is — including the ZIP-inside-a-ZIP it usually is — under
**Import**. Then the [usual rules](/p/docuwaves/pages/importing-a-zip)
apply: preview first, drafts, one commit.

## What is converted

- **Names.** Notion appends a 32-character id to every file and folder
  (`Server 0123…cdef.md`). The ids are removed everywhere, images included,
  and links follow.
- **The page tree**, by the same rule as Confluence: one top page is the
  home page; it and top-level pages without sub-pages go into "General",
  every top-level page with sub-pages becomes a category.
- **Databases** become a page with the table from the CSV (at most 500
  rows). The first column links to the entry's own page, and the entry pages
  become its sub-pages.
- **Callouts** (`<aside>`) become DocuWaves callouts by their emoji:
  💡 tip, ⚠️ warning, ❗ or 🚨 caution, anything else a note.
- **Titles.** Notion starts every page with its title as a heading; that
  heading becomes the page title and is not shown twice.
