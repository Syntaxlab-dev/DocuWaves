---
order: 2
published: true
title: Syncing and conflicts
---

DocuWaves keeps a working clone of the content repository under `CONTENT_REPO_PATH` (`/data/content-repo` by default). Everything it serves is read from that clone, and everything it writes is written there and pushed.

## How a change made elsewhere gets picked up

Three moments, all doing the same two steps — `git pull`, then reindex:

| When | What triggers it |
|---|---|
| **On startup** | Every start. The clone lives on the persistent volume, so without this the index would be rebuilt from a checkout that could be days old |
| **On a timer** | Every `CONTENT_REPO_SYNC_INTERVAL_SECONDS`, 300 by default. A merged pull request appears within five minutes without anyone doing anything |
| **On demand** | The **Sync now** button in the admin status bar |

The clone is made once per installation, not once per start — it survives container recreates on the `/data` volume. Its remote URL is re-pointed on every start, so rotating `CONTENT_REPO_TOKEN` reaches an existing clone instead of leaving it pushing with a revoked credential forever.

A single failed sync — a network blip, a transient error — is logged and retried at the next interval. It never crashes the application, and it never empties the index: "no files on disk" is not the same statement as "every page was deleted", so a failed clone leaves the previous index in place.

## What reindexing actually does

It reconciles the database with the files. Rows are matched to files **by slug**, not by id:

- a slug still present on disk keeps its existing row id, so admin deep links stay valid;
- a slug that is new gets a fresh row;
- a row whose file is gone is deleted, and everything under it with it.

Which is why the index is disposable. If it ever looks wrong, press **Sync now**; if that is not enough, delete the database file and restart.

## Writing: commit, push, and one retry

Every write follows the same sequence: write the file, commit it, push it.

If the push is rejected because the remote has commits the clone does not, DocuWaves pulls once (a **merge**, never a rebase — a rebase would rewrite the commit it just made) and pushes again. That covers the ordinary case of a pull request being merged in the same minute you pressed Save.

## When it genuinely conflicts

If the merge itself conflicts — the same file changed on both sides — the merge is **aborted immediately** rather than left half-finished, and the save reports:

> Your change was saved locally but conflicts with a newer version in the content repo (same file changed on both sides). It was NOT pushed — resolve the conflict manually in the repo, then use 'Sync now'.

Read that literally, because both halves matter:

- **Your text is not lost.** It is committed in the working clone inside the container.
- **It is not on the remote.** Anyone else cloning the repository does not have it yet.

To resolve it, work in the content repository as you would with any conflicted merge — reconcile the two versions of that file, push the result — and then press **Sync now**. Nothing picks a side on your behalf, and nothing is silently discarded.

This is rare by construction: one file per project, category and page means two people have to be editing the same page at the same time to collide at all.

An **unsupported** way to reach the same state is pointing two DocuWaves instances at one content repository. It fails loudly rather than corrupting anything, but do not do it. Give each instance its own repository — that is also what gives each its own [branding](/p/docuwaves/pages/branding-this-instance).

## Files the index could not use

Not every problem is a conflict. If two categories in a project hold the same page slug, one of them has to be ignored — the first wins, the rest are skipped. Those skips are listed under [Diagnostics](/p/docuwaves/pages/diagnostics).

A page that silently never appears is the hardest kind of problem to chase in a file-backed CMS, because the file is right there in the repository. So the reason is put where you are already looking.
