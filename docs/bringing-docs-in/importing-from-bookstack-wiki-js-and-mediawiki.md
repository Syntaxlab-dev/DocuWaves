---
order: 3
published: true
title: Importing from BookStack, Wiki.js and MediaWiki
---

Three wikis that teams often move away from, each with its own export.
Upload it under **Import** like any ZIP: the importer recognises it by
itself, and then the [usual rules](/p/docuwaves/pages/importing-a-zip)
apply. Preview first, every page arrives as a draft, all in one commit.

## BookStack

In BookStack open the book (or one chapter, or one page) and choose
**Export → Portable ZIP**. That export exists since BookStack v25.02; on an
older version, update first.

- **Chapters** become categories, pages directly in the book go into
  "General", both in BookStack's order.
- **Pages** written in the Markdown editor keep their Markdown; pages from
  the visual editor are converted from HTML.
- **Images** are copied, and links between pages, chapters and the book
  point at the imported pages.
- **Attachments** are listed at the end of their page. Links stay links,
  images, audio and video are copied. Other files, such as PDFs, are named
  but not copied, because DocuWaves keeps no documents. The preview lists
  each one.
- Tags, revisions and permissions are not taken over.

## Wiki.js

Wiki.js 2 stores every page as a file when a storage target is on: with
**Git** (Administration → Storage), the pages are in that repository; with
**Local File System**, in its folder. Import the repository straight
[from its URL](/p/docuwaves/pages/importing-from-a-git-repository), or ZIP
the folder and upload it.

- The head every Wiki.js page starts with (`<!-- title: … -->`) becomes the
  page title. Unpublished pages stay unpublished.
- **Folders** become categories, `home` is the first page of its folder.
- **Links** like `/guide/install` and uploaded images are resolved against
  the export.
- **Callouts** (a quote with `{.is-info}`, `{.is-success}`,
  `{.is-warning}` or `{.is-danger}` under it) become DocuWaves callouts.
- Pages from the visual editor (`.html`) are converted from HTML.
- In a wiki with several languages, the language with the most pages is
  imported. The preview names the others, so they can go into a
  [language of their own](/p/docuwaves/pages/enabling-a-second-language)
  later.

## MediaWiki

Export the pages with **Special:Export** (current revision only), or on the
server with `php maintenance/dumpBackup.php --current`. Upload the XML file
as it is, or ZIP it together with the wiki's `images/` folder to bring the
images too.

- **Categories:** every page goes into the category of its first
  `[[Category:…]]`, pages without one into "General".
- **Only articles** come over: talk pages, user pages, templates and
  redirects are left out.
- **Wikitext** is converted: headings, bold and italics, lists (nested and
  numbered), definitions, internal links with sections, external links,
  images with their caption, `<pre>`, `<syntaxhighlight>` and indented
  lines as code blocks, tables as Markdown tables, `<ref>` as footnotes.
- **Templates** (`{{…}}`) only work inside MediaWiki. They are removed, and
  the preview lists them per page, so what they showed can be written in
  by hand.
- Links to pages that are not in the export stay as plain text and are
  listed too.
