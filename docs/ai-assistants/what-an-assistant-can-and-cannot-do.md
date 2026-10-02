---
order: 2
published: true
title: What an assistant can and cannot do
---

Ten tools. Four read, six write.

## Reading

| Tool | What it does |
|---|---|
| `list_projects` | Every project, with the slug that identifies it everywhere else, plus this instance's content languages and, per project, its documentation versions — which one writes land in, which are frozen |
| `list_pages` | One project's categories and the pages in them, **one entry per language**, drafts included and marked `"published": false` |
| `read_page` | One page's full Markdown, exactly as it sits in the content repository, with the frontmatter split off into separate fields |
| `search` | Full-text search across **published** pages, in one language and one version per project, optionally scoped to one project |

## Writing

Each of these requires a `write` token, and each is a real commit.

| Tool | What it does |
|---|---|
| `create_project` | A new project — the top level. Every other tool takes a project slug, so on an empty instance this is where an assistant starts |
| `create_category` | A new category in a project. Always in the version being edited, so it takes no `version` argument at all |
| `create_page` | A new page in a category, created as a draft unless `published` is true |
| `update_page` | Replaces a page's Markdown; optionally its title and published state |
| `translate_page` | A second language of an existing page. Shares the page's slug and its position, so the two are one page and not two that happen to say similar things |
| `move_page` | One position up or down within its category — the same thing the arrows in the admin list do |

## Rules the tools inherit rather than reimplement

Writes go through the same functions the admin editor uses, so they get the same behaviour by construction:

- **Slugs are derived, not chosen.** A title becomes a slug exactly as the editor would derive it, `-2` suffix and all, and the answer reports the slug that was actually used. Two implementations of "what is this page's address" agree right up until the first collision.
- **`update_page` replaces the body.** It does not append. Read the page first and send the complete new text — the tool's own description says so, twice.
- **Only the default language's title steers the slug.** Renaming a translation cannot move the page's URL.
- **Frozen versions refuse a write**, with the same message the admin API gives — never a silent redirect into `current`, which would leave the assistant believing it had corrected a released version.
- **Approval applies to assistants too.** In a project that [requires approval](/p/docuwaves/pages/approval-before-publishing), an assistant's change to a live page — or `published: true` on a new one — is submitted for approval, and a person approves it. The tool's answer says so.
- **Synced projects refuse a write.** Their pages come from a code repository ([docs-as-code](/p/docuwaves/pages/docs-as-code)); a change here would be replaced by the next sync.
- **`read_page` falls back rather than failing.** If the page has no version in the language asked for, another language's text is returned with `"fallback": true`. Updating against a fallback would overwrite the wrong translation, so the flag is there to be checked.

## Errors are instructions

Every refusal names what was wrong **and what is actually available**:

```
No category 'setup' in project 'cachepanel' (version 'current');
available: getting-started (Getting Started), reference (Reference).
Use the slug. To add one, call create_category.
```

"Category not found" tells a model nothing it can act on. This tells it exactly what to call next.

## There is deliberately no delete tool

An assistant can create pages and rewrite them. It **cannot** delete a page, a category or a project, and that is a decision rather than an omission.

Creating and editing are recoverable. Each one is a commit, so `git revert` puts a page back exactly as it was, and a wrong edit is visible — the page reads wrong. Deleting is the one operation whose damage is invisible afterwards: nothing looks broken, something is simply gone, and nobody notices for weeks. An assistant that is wrong about a page being obsolete is wrong in a way nobody catches.

Set against that, the benefit of handing deletion to an autonomous agent is close to zero. Deleting stays in the admin area, where a human confirms it.

`create_project` is the counter-example that shows the line is about recoverability rather than about caution: it was missing at first, and it was added, because creating a project is exactly as recoverable as creating a page — one commit adding one `_project.yml`. Deletion is not.

An assistant can also not touch branding, cannot create another token, and cannot reach any other part of the admin API.

## Every write is a commit, attributed to the token

A change made through a token is committed with the **author**:

```
Claude (API token: notes-bot) <claude-api-token-notes-bot@local>
```

The **committer** stays `DocuWaves`, which is the honest description: this instance committed on the assistant's behalf.

So:

```bash
git log --author='API token'            # everything any assistant ever wrote
git log --author='notes-bot'            # everything this one token wrote
git blame content/cachepanel/getting-started/installation.md
git revert <sha>                        # undo one of them
```

Attribution is in the **author** rather than in the commit message on purpose. The message stays the same sentence a human edit produces, so the history reads uniformly and a diff is not cluttered — while `--author`, `git blame` and every Git UI's author column answer "which of my tokens wrote this?" without anyone opening a diff.

The email address is derived from the name rather than pasted into it, so a token called `notes-bot` and one called `Claude, the notes bot` both produce a valid address.
