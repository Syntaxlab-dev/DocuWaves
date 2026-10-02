---
order: 3
published: true
title: Backups and updates
---

## What is worth backing up

Sort everything DocuWaves stores into two piles.

**Rebuildable** — losing it costs a restart, nothing more:

| Thing | Where | Rebuilt from |
|---|---|---|
| The search/browse index | `/data/docuwaves.db`, or PostgreSQL | the working clone, on the next start |
| The working clone | `/data/content-repo` | the Git remote, on the next start |

**Not rebuildable** — losing it means recreating it by hand:

| Thing | Where | Consequence of losing it |
|---|---|---|
| Your documentation | the **content repository** | this is the real one |
| [Accounts](/p/docuwaves/pages/accounts-and-roles) | the database, `auth` table | you are sent back through first-run setup |
| [API tokens](/p/docuwaves/pages/api-tokens-and-scopes) | the database, `api_tokens` table | every assistant needs a new token |
| [Reader votes](/p/docuwaves/pages/reader-feedback-and-link-checking) | the database, `page_feedback` table | the "was this helpful?" report starts from nothing |
| [Preview links](/p/docuwaves/pages/draft-preview-links) | the database, `preview_links` table | links you handed out stop working; make new ones |
| The session signing secret | `/data` | everyone is logged out |

So the backup story is short: **your content is already backed up, because it is a Git repository with a remote.** Clone it anywhere and you have every page, every image, the branding, and the full history.

What is *not* covered by that is the accounts, the tokens and the reader votes. If you back up `/data` you have them; if you do not, restoring means going through setup again, recreating the accounts and issuing new tokens. Neither is a disaster, but know which it is before you find out.

Do not treat the index as a backup of anything. It is a cache with a schema.

**And if you have no remote at all**, none of the above applies to your
content: on a local-only instance the `/data` volume is the *only* copy, and
backing it up is the whole job. That is the case the export below exists
for.

## The export

Under **Diagnostics** — administrators only — is one button that produces
one zip:

```
content-repo/        the repository's working tree, exactly as on disk
history.bundle       the complete version history, as a git bundle
page-feedback.json   the "was this page helpful?" answers
README-EXPORT.md     what is in here, and how to restore it
```

Restoring needs no special tooling and, for the content, does not need this
application at all — the Markdown *is* the documentation. To bring the
history back too:

```bash
git clone history.bundle content-repo
```

**Why a bundle and not the `.git` folder.** `.git/config` holds the remote
URL, and on a remote-backed instance that URL has the push token embedded in
it. An archive is a file made to be emailed to yourself and dropped in cloud
storage, so a `.git` directory in it would be a leaked credential with a
delivery mechanism attached. A bundle carries the objects and the refs and
nothing else.

**Deliberately not in the archive:** the password hashes, live sessions, API
tokens and preview links. All four are credentials, and none of them is
something a restore needs — a restored instance asks whoever opens it to
create an administrator account, which is the right thing for it to do.

It is not a snapshot: files are read while the instance keeps running, so an
export taken during a save can catch one page a version older or newer than
its neighbours. Locking every write in the application to avoid that would
cost more than it buys.

## Restoring

1. Start a container with the same `.env`.
2. It clones the content repository, indexes it, and serves it.

That is the whole procedure. If you restored `/data` as well, your login and tokens come with it; if not, the first screen is first-run setup.

This is also how you move an instance to another machine, and how you find out whether your backups work — a restore that ends with the site looking exactly as it did is a test you can run any time. The export above is the same test in one file: download it, unzip it, and read a page.

## Updating

```bash
git pull
docker compose up -d --build
```

Or, if you run the published image, `docker compose pull` and then `up -d`.

What happens on the way up:

1. **The schema is brought up to date.** If the content tables' layout changed, they are dropped and recreated — and then refilled from the files. That is safe precisely because they hold no source data.
2. **The `auth`, `sessions` and `api_tokens` tables are never dropped**, in any rebuild. They hold state that exists nowhere else, and no reindex could bring them back.
3. **The content repository is pulled and reindexed.** Commits pushed while the container was down are picked up immediately rather than waiting for the first timer tick.

A failed pull at that moment does not stop the start: the clone is on the persistent volume, so the index is rebuilt from the files that are there, and the admin area's status bar shows the connection problem. Losing the network must not cost you the site.

Nothing in an update touches your content repository. If an update goes badly, roll the image back; the documentation is untouched, because it was never in the image.

## About the image and its rebuilds

The published image is rebuilt weekly with no code change. Most of what a container scan reports lives in the Debian userland of the base image rather than in this project's own dependencies, and those findings only clear when the image is built again after Debian publishes fixes. Without a scheduled rebuild, an image sits unchanged for as long as nobody pushes, quietly accumulating everything that was patched upstream in the meantime.

The Python side stays reproducible regardless: every dependency is pinned to an exact version.

So pulling a fresh image occasionally is worth doing even when nothing about DocuWaves has changed.
