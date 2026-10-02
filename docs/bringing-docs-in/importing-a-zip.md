---
order: 0
published: true
title: Importing a ZIP
---

**Import** in the admin header takes a ZIP of Markdown files — an export
from another tool, or simply a folder of `.md` files — into a new project or
an existing one.

## Preview first

After choosing the file and where it goes, **Preview** shows what would
happen, without writing anything:

- which tool the archive was recognised as,
- the categories and pages it would create, each with the file it came from,
- how many images and media files it would copy,
- **notes** — links that point nowhere, MDX components that need rewriting,
- **files not taken over**, and why.

Then **Import**. Every page arrives as a **draft**, in **one commit** —
reverting that commit undoes the whole import. Nothing that exists is
overwritten: a name that is taken gets `-2`.

## How the archive becomes a project

- **A folder becomes a category, a Markdown file a page.** Files at the top
  go into "General". DocuWaves has one level of categories, so
  `guide/advanced/` becomes the category "Guide / Advanced" — flatter, but
  nothing is lost.
- **Titles** come from the front matter, else the page's first `# heading`,
  else the file name.
- **Order** comes from the tool's own navigation when there is one, else from
  numbered prefixes (`01-intro.md`), else alphabetically — with
  `index.md` / `README.md` first.
- **Links** to other pages in the archive are rewritten to their new
  addresses; **images and media** are copied into the project's
  `assets/imported/`, each through the same checks as an upload.
- **Callouts** in the common dialects become DocuWaves
  [callouts](/p/docuwaves/pages/callouts-and-code-blocks).
- **Code blocks are never touched**: a tutorial *about* MkDocs keeps its
  `!!! note` example.

## Recognised automatically

| Tool | Recognised by | Taken over |
|---|---|---|
| MkDocs | `mkdocs.yml` | `docs_dir`, the `nav` order, `!!! note "Title"` admonitions |
| GitBook | `SUMMARY.md` | the summary's order, `{% hint %}` blocks, `{% embed %}` as links |
| Docusaurus | `docusaurus.config.*` | `docs/`, `sidebar_position`, `_category_.json`, `:::tip` containers, `/img/…` from `static/` |
| Obsidian | `.obsidian/` | `[[wiki links]]`, `![[embeds]]`, `> [!info]` callouts |
| DocuWaves | `_category.yml` | a content folder from another instance, names, icons and order included |
| [Confluence](/p/docuwaves/pages/importing-from-confluence) | an HTML space export | the page tree, macros, attachments |
| [Notion](/p/docuwaves/pages/importing-from-notion) | Notion's ids in the file names | the page tree, databases, callouts |

## Limits

An uploaded archive is untrusted, so: at most **50 MB** (200 MB unpacked,
5000 files); ZIP bombs, absolute paths and `..` are refused; only Markdown,
image and media files and the navigation files above are read. Only
accounts that may write can import.
