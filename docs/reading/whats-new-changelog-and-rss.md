---
order: 1
published: true
title: "What's new: changelog and RSS"
---

`/changes` lists what is new in the documentation, newest first and grouped
by day; `/p/<project>/changes` does the same for one project. Both are
linked from the home and project pages.

## The feeds

The same list is an **RSS feed**: `/feed.xml` for the whole site,
`/p/<project>/feed.xml` for one project. On a multilingual site add
`?lang=en` for another language. Every page announces the site feed in its
`<head>`, so a feed reader finds it from wherever somebody subscribes.

## Following one page or one category

A reader who only cares about part of the docs can subscribe to just that.
Every category and every page has **Subscribe via RSS** under its title or
at the end of its text:

- `/p/<project>/c/<category>/feed.xml` for one category
- `/p/<project>/pages/<page>/feed.xml` for one page

A page's feed holds one item, its latest change, and every new change
arrives as a new item. That is what subscribing to a page is for: being
told when it changes. Both are also announced in the page's `<head>`, next
to the site feed, so a browser extension or a feed reader offers them too.

They follow the version a reader lands on. A draft, a category with nothing
published in it, and anything in a private project have no feed.

Point a Slack, Discord or Mattermost **feed integration** at any of these feeds and the docs'
news arrives in a channel — no [webhooks](/p/docuwaves/pages/webhooks) to
configure.

## What counts as news

It is built from the content repository's history, and only two things
count:

- **New** — a page went live (created published, or a draft published)
- **Updated** — a published page's title or text changed

Reordering pages, a review note, front matter edits and anything done to a
draft are not news and do not appear. Each page appears once, with its
latest change; only pages that are published now, in each project's default
version, are listed.

Commit messages and authors never appear. Like the "last updated" line on a
page, the public side says *when*, not who or why.

Private projects never appear in the changelog or the feeds — a feed reader
never signs in, and whatever it fetched once it keeps.
