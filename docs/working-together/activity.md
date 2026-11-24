---
order: 3
published: true
title: Activity
---

**Activity** in the admin area answers "who changed what, lately?" It lists
the content repository's commits, newest first: who made each one, its
message, when it was made, and the pages it touched.

```text
Kim    Update page: Installation                      24 Nov 2026, 11:07
       DocuWaves / Installation
Sam    Propose changes: Upgrading                     24 Nov 2026, 10:52
       DocuWaves / Upgrading · proposal
```

It is read straight from the repository's history, so it shows everything:
drafts, [proposals waiting for approval](/p/docuwaves/pages/approval-before-publishing),
review notes, renames and imports, and changes that never went through
DocuWaves at all, such as a push from someone's editor or a
[docs-as-code](/p/docuwaves/pages/docs-as-code) sync. Nothing is recorded
twice and nothing has to be switched on.

Each page is named by its current title and links to it. A `+` marks a page
the commit added, a `−` one it deleted. A page shown struck through is gone
under that address, because it was deleted or renamed since. A commit that
touched many pages, an import for example, names the first few and counts
the rest. Project and category files are counted rather than listed.

The list starts with the latest 50 commits; **Show older** loads more, up to
200. For one page's full history, with a diff for every change, open
[Page history](/p/docuwaves/pages/page-history) in the editor.

## Activity and the public changelog

The [changelog](/p/docuwaves/pages/whats-new-changelog-and-rss) is the
reader's side: only published pages that are new or whose text changed,
with a date and nothing about who or how. Activity is the authors' side and
is shown to every account that can open the admin area. Reader accounts
never see it.
