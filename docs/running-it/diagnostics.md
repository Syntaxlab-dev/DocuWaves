---
order: 4
published: true
title: Diagnostics
---

An administrators-only page answering the questions you would otherwise
answer with `docker exec`.

## What is on it

**Checks**, first, because they are the only lines that can say something is
wrong:

- the content repository is writable
- the content repository can be opened
- the remote is reachable — marked *not applicable* rather than passing on a
  local-only instance, which is a complete state and not a broken one

**Files the index could not take.** This one is easy to miss otherwise: two
files wanting the same slug. A slug is a page's address and has to be unique
within its project, so one of the two wins and the other is invisible on the
public site while sitting perfectly happily in the repository. Nothing else
in the application says so. Rename or remove one of them.

**Instance** — which database, which languages, the content repository path,
the sync interval, whether a public address is pinned, and whether the
[documentation chat](/p/docuwaves/pages/the-documentation-chat) is configured (it is
set through environment variables, so this is the only place it can be read
off).

**Content** — projects, categories, pages, and how many of those are still
drafts. That difference is usually the answer to "a page of mine isn't
showing up".

**Storage** — the size of the content, the size of the database, and how
much disk is left.

**Operations** — API tokens, live preview links, reader votes, and when the
index was last rebuilt.

## Two things it deliberately does not do

**It contains no secrets.** No token values, no password hash, no remote URL
(that one carries the push credential), no environment dump. This is the
page you screenshot into a forum thread when you are stuck, and it is built
to be safe to do that with.

**There is no repair button.** Every failure it can show — a full disk, a
read-only volume, an unreachable remote — is fixed in your deployment. A
button claiming to fix one from inside the container would be lying about
what it can reach.

## When one section cannot be measured

It says so, and the rest of the page still renders. A diagnostics page that
fails when one thing is broken is a diagnostics page that is unavailable in
exactly the situation it exists for.
