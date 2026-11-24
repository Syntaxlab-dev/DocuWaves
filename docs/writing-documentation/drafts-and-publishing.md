---
order: 10
published: true
title: Drafts and publishing
---

A page is invisible to the public site until you publish it. That is one field in the page's file:

```markdown
---
title: Installation
order: 0
published: true
---
```

Omit `published`, or set it to `false`, and the page is a draft. In the editor it is the **Published** toggle above the tabs; switching it is its own commit, `Publish page: <title>` or `Unpublish page: <title>`.

It is a separate commit on purpose. Publishing is a decision about what readers should see, not an edit to the text, and keeping the two apart means the history says which one happened.

## What a draft is invisible to

- The **public site** — a reader asking for its URL gets a 404.
- **Search** — the index the public search box uses covers published pages only.
- **`/sitemap.xml`** — the one query it is built on filters on `published`, so a draft cannot appear there by any path. This file is public, and a leaked slug is a leaked page.
- **Crawlers and link previews** — an unpublished URL produces the site's default metadata and nothing else: no title, no snippet of its text.

## What a draft is still visible to

- The **admin area**, obviously.
- **Both [API token scopes](/p/docuwaves/pages/api-tokens-and-scopes).** A `read` token can read drafts, not only a `write` one. That is the point — an assistant asked to finish a draft has to be able to read it. If a draft would be a problem to share, it is a problem to hand out any token for.
- **Anyone with access to the content repository.** A draft is a committed file. The repository, not the publish toggle, is the confidentiality boundary.
- **Anyone holding a [preview link](/p/docuwaves/pages/draft-preview-links) to it.** That is what those are for: showing one unpublished page to somebody who has no account here, until a date you pick.

## Per language, per version

The flag lives in each file, so it is per language: an unfinished English translation stays a draft while the German original it was translated from is published. A reader in English sees the published German page with a notice, never the half-finished English one.

Frozen [documentation versions](/p/docuwaves/pages/after-the-freeze) refuse the toggle like any other write.

## A project with nothing published stays off the public site

A project has no published flag of its own — only pages do. So the rule is derived: **a project with no published page anywhere in it does not appear on the public home page, and is not in the sitemap.** The admin area is unchanged; nothing vanishes from the place you manage it from.

There is deliberately no separate switch for this. A project with nothing to show is not shown, which is both the sensible default for a project between "created" and "first page written", and the way to keep a **private set of notes** in the same instance: a project whose pages are all drafts is simply not part of the public site.

Be precise about what that is, though. It removes the project from the listings a visitor browses; it is **not access control**. A direct link to such a project's URL still resolves — the page just has no category tiles on it, because a category with nothing published in it is not shown either. Anything that must actually be secret does not belong in a documentation instance.

## Publishing at a set time

A saved draft can go live by itself. Under the title, **Schedule
publishing** takes a date and time, in your own time zone. From then on the
editor says when the page goes live and who scheduled it, and **Unschedule**
takes it back.

At that time DocuWaves publishes the page exactly as the toggle would: one
commit, `Publish page: <title>`, in the name of whoever scheduled it. The
[e-mail notifications](/p/docuwaves/pages/e-mail-notifications) and
[webhooks](/p/docuwaves/pages/webhooks) for a published page go out then,
not when it was scheduled. It happens within a minute of the time. If the
instance was down at that moment, it happens right after it starts again,
late rather than never.

A few things change the plan on their own:

- **Publishing the page by hand first** clears the schedule; there is
  nothing left for it to do.
- **Renaming the page** keeps the schedule; **deleting it** removes it.
- **In a project that [requires approval](/p/docuwaves/pages/approval-before-publishing)**
  scheduling is not offered: there, going live is what the approval does,
  and a timer must not be a way around it. A schedule left over when a
  project starts requiring approval is dropped rather than carried out.

The schedule is kept in the instance's database, not in the page file, so
it is not part of the content repository's history and not in a pull
request. The commit that publishes the page is.

## Several pages at once

Tick pages in a category's list (or **Select all**) and a bar appears above
it: **Publish**, **Unpublish**, **Move to …** another category of the same
project, and **Delete**. Whatever the bar does is **one commit** for all of
the pages, `Publish 12 pages`, so it is also undone in one step in the
history.

Each page is still checked as if it were done on its own. A page that
already is what you asked for, one in a project that
[requires approval](/p/docuwaves/pages/approval-before-publishing), or one
from another project when moving, is skipped and counted, and the rest go
ahead. A selection that includes a project your account may only read is
refused as a whole, before anything changes.

On a multilingual instance, publishing and unpublishing act on the default
language's version of each page: a translation that is not finished stays a
draft. Moving and deleting take every language with them, as they do for a
single page.

## Practical order of work

1. Create the page. It is a draft.
2. Write it, saving as often as you like. Every save is a commit; none of them is visible to a reader.
3. Show it to somebody first, if it needs that — a [preview link](/p/docuwaves/pages/draft-preview-links) reaches one page and nothing else.
4. Publish when it is worth reading.
5. Keep editing. A published page's saves are immediately live — there is no second "publish this change" step, because there is no separate published copy.

In a project that [requires approval](/p/docuwaves/pages/approval-before-publishing),
steps 4 and 5 go through a second person: a draft is submitted rather than
published, and saving a live page creates a proposal that readers see only
once it is approved.
