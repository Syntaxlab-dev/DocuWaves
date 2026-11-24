---
order: 5
published: true
title: Compared with other tools
---

DocuWaves is not the only self-hosted place to keep documentation. This page is an honest map of where it sits next to four tools people often weigh it against, so you can tell quickly whether it is the right one for you. It describes each tool as of late 2026. They all change, so check their own documentation before you decide.

## In one table

| | DocuWaves | BookStack | Wiki.js | Docusaurus | Outline |
|---|---|---|---|---|---|
| What it is | Documentation site with a browser editor | Wiki organised as books, chapters and pages | General-purpose wiki | Static site generator | Team knowledge base |
| Where content lives | Markdown files in **your Git repository**; the database is only an index | Database (MySQL/MariaDB) | Database, with optional Git sync | Markdown/MDX files in your repository | Database (PostgreSQL) |
| Editing | Browser editor, or any text editor and a pull request | Browser editor (WYSIWYG or Markdown) | Browser editor (several editors) | Text editor and a build | Browser editor, real-time collaborative |
| Several projects, public home page | Yes | Yes, as shelves and books | Yes, as a page tree | One site per build (or plugins) | Collections, mainly internal |
| Versions of the docs | Yes, frozen per release | No | No | Yes | No |
| Languages per page | Yes, with fallback to the original | Interface only | Yes | Yes | Interface only |
| Approval before publishing | Optional, per project | No | No | Through pull requests | No |
| AI assistant access | MCP endpoint, read and write, as commits | No built-in | No built-in | No built-in | Built-in AI features |
| Runs as | One container (SQLite or PostgreSQL) | PHP app with a database | Node.js app with a database | Static files on any web server | Node.js app with PostgreSQL, Redis and file storage |
| License | MIT | MIT | AGPL-3.0 | MIT | BSL 1.1 (source-available, not open source) |

## When another tool is the better choice

- **BookStack**, if your team wants a classic internal wiki with a WYSIWYG editor, fine-grained permissions and a familiar book structure, and does not care where the content is stored.
- **Wiki.js**, if you want a general wiki with many editors and authentication options, and the content being in a database is fine.
- **Docusaurus**, if your documentation is written by developers anyway, should be a static site, and needs custom React components. Nobody edits in a browser there, and that is the point.
- **Outline**, if you want an internal team knowledge base with real-time collaborative editing, rather than public product documentation.

## When DocuWaves is

- The documentation is **public product documentation**, for one or several projects, and should look like it.
- The content must stay **plain Markdown in a Git repository you own**: reviewable, portable and readable without the app.
- **Both kinds of people write**: some in the browser, some through a pull request, and neither gets in the other's way.
- You need **versions per release** and **languages per page** without building a site.
- An **AI assistant** should be able to read and write the docs, with every change landing as a commit you can review or revert.

What DocuWaves deliberately leaves out is on [Scope and limitations](/p/docuwaves/pages/scope-and-limitations).
