---
order: 1
published: true
title: Translations, slugs and fallback
---

## A page's language is in its filename

```
content/cachepanel/getting-started/
  _category.yml
  installation.de.md
  installation.en.md
  advanced.de.md          <- German only; the missing English is visible at a glance
```

Putting the language in the filename rather than in the frontmatter is the point: a directory listing shows you what is and is not translated, without opening anything.

## The slug is shared

All of those files are one page. `installation.de.md` and `installation.en.md` both have the slug `installation`, and the page's URL differs only in its language prefix:

```
/de/p/cachepanel/pages/installation
/en/p/cachepanel/pages/installation
```

A reader who switches language stays on the page they were reading, rather than being sent to the home page of another language.

An **unprefixed** URL — every link ever shared before you added a second language — redirects to the default language. Nothing breaks.

A code is only recognised when it is one you configured, so a file named `release.v2.md` keeps the slug `release.v2` and does not become a Venda translation of `release`.

## A missing translation is never a dead end

If a page has no version in the language being read, **the default language's version is served — 200, not 404** — with an unobtrusive notice above it:

> This page has not been translated yet — showing the German version.

In the sidebar and in category listings, such a page is listed normally and marked with a small muted language code after its title, so the language it opens in is not a surprise.

The chain does not stop at the default language either. A page that exists **only** in English is still reachable by a German reader — from a link, from search, or by switching language while reading it. The order is: the reader's own language, then the site default, then whatever else the page exists in, in the order `_site.yml` lists them. Everything below the reader's own language is flagged and says so.

A half-finished translation cannot shadow a published one: unpublished rows are skipped anywhere in that chain, so from outside, such a page is simply not translated yet.

## Search stays in one language

Searching in English returns the English pages, plus the pages that exist **only** in the default language. Never a page and its own translation as two separate hits.

That filter is part of the query rather than a pass over the results, because ranking and the result limit happen in the database — filtering afterwards would quietly return fewer hits than asked for.

## Editing translations

Each page has one tab per configured language. A tab for a language the page does not exist in yet opens an empty editor and saves as `<slug>.<lang>.md` under the same slug — creating a translation, never a new page.

Two rules protect addresses:

- **Only the default language's title steers the slug.** Renaming a translation cannot move the page's URL out from under anyone.
- **`order` belongs to the page, not to one translation.** Reordering writes the new position into every language's file, so a reader who switches language gets the same sidebar order and the same previous/next links.

Each translation has its **own history**, because each is its own file. The History tab names the file it is showing.

**Deleting a page deletes all of its translations.** To remove just one, delete that file in the content repository — see [Editing in Git](/p/docuwaves/pages/editing-in-git).

## Interface language is a separate thing

The language of the buttons and labels is the reader's own choice. On a multi-language instance it follows whichever content language they are reading, for the languages the interface itself has translations for. It has nothing to do with which files exist in your repository.
