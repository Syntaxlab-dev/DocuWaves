---
order: 0
published: true
title: Private projects
---

A project can be **private**: only signed-in accounts see it — any role,
including **Reader**, which exists for exactly this. For everybody else it
does not exist at all: its pages, search results, changelog entries, images
and PDF view answer with the same "not found" as a project that was never
there.

## Making a project private

In the admin area, in the project's settings under **Visibility**: *Public*
or *Private*. The project then carries a lock badge for everybody who can
see it. In the file, it is one line:

```yaml title="content/internal/_project.yml"
name: Internal handbook
visibility: private
```

Only the exact word `private` counts. Anything else — or no line at all — is
public, so a typo never hides docs nobody meant to hide.

## Signing in to read

As soon as an instance has a private project, the header offers **Sign in**,
and a "not found" page offers it too, for somebody who was sent a link. It
uses the same login as the admin area, single sign-on included, and returns
the reader to the page they came from. A Reader account that opens `/admin`
is told what the account is for instead of being shown an admin area it
cannot use.

On an instance without private projects there is no sign-in button at all.

## Where private projects never appear

Some places do not show a private project to anybody, signed in or not,
because whoever reads them never signs in or is shared with everybody:

- the **RSS feeds** and the **sitemap**,
- the search's **typo suggestions** (built from public projects only),
- **[webhooks](/p/docuwaves/pages/webhooks)** — a channel's members are unknown,
- the **page description** that link previews and search engines read.

The [documentation chat](/p/docuwaves/pages/the-documentation-chat) answers
a signed-in reader from private pages too, and a stranger from public ones
only. Answers to signed-in readers are sent with
`Cache-Control: private, no-store`, so no proxy or CDN keeps a copy.

A [preview link](/p/docuwaves/pages/draft-preview-links) still works for
its one page: it was made by somebody who could see the page, for somebody
who should.

## Private is about the website, not the files

> [!WARNING]
> A private project's pages are ordinary files in the content repository.
> If that repository is public — on GitHub, say — everything in it can be
> read there, private projects included.

Because that is the easiest way to get this wrong, DocuWaves asks the
content repository's remote what a stranger could: `git ls-remote` with **no
credentials**. The admin status bar then says where the content lives — *on
this server only* or *also at github.com/…* — and whether that remote is
**readable by anybody**, in red when private projects exist. Making a
project private while the remote is public needs an explicit confirmation.
