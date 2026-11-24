---
order: 15
published: true
title: Search and replace
---

The product was renamed, a command changed its name, a link moved: **Search and replace**, in the bar above a project's categories, changes the text of many pages at once.

1. Enter what to find and what to put in its place, and press **Search**.
2. Every page with a match is listed, with how many and a few words around each one, the match struck through and the replacement next to it. Every page is ticked.
3. Untick the pages that should stay as they are, and press **Replace in … pages**.

All the pages change in **one commit**, `Replace "old" with "new" in 12 pages`, so the whole replacement is one entry in the [history](/p/docuwaves/pages/page-history) and is undone in one step.

## What is searched

- Only the **text of the pages**, not their titles and not the front matter.
- Every language and every page of the version you are looking at, drafts included. A [frozen version](/p/docuwaves/pages/after-the-freeze) cannot be changed, so it offers no search and replace.
- The text as the editor would open it: when changes to a page [wait for approval](/p/docuwaves/pages/approval-before-publishing), the proposed text.

**Match case** and **Whole words only** narrow it down. Whole words means `Wave` does not match inside `WaveDocs`.

It is **plain text, not regular expressions**, and the replacement is taken literally too. A regular expression runs on the server with no time limit, and one unlucky pattern can keep it busy for minutes. For anything cleverer than a rename, edit the files in the content repository with a text editor.

## What it does not overwrite

- **A page saved since the search** is skipped, not changed: the replacement would otherwise land on text nobody looked at. Search again to include it.
- **A live page in a project that requires approval** gets a *proposal* with the replacement, like any other edit there. Readers keep the live text until somebody approves it. The list marks these pages.
- **Review notes** are removed from the pages whose text changed, as with any edit (see [Review notes](/p/docuwaves/pages/review-notes)).

Search and replace is a write: an account that may only read a project does not get it there (see [Accounts and roles](/p/docuwaves/pages/accounts-and-roles)). Through the API it is `POST /api/admin/projects/{id}/replace/preview`, then `POST /api/admin/projects/{id}/replace` with the revisions the preview returned.
