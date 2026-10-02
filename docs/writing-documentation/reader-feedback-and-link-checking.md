---
order: 13
published: true
title: Reader feedback and link checking
---

Three reports in the admin area, under **Insights**. Both are about the
documentation rather than about the instance, and both are things you look
at occasionally rather than while writing.

## What readers searched for and did not find

A search that finds nothing is the clearest hint that a page is missing — a
reader said, in their own words, what they were looking for. The first list
under **Insights** shows those words, most searched first, with how often and
when they were last searched.

- **Create a page with this title** starts a new page with the search words
  as its title: pick the category, and the editor opens.
- **Remove from the list** once a page covers it; **Clear list** empties it.

What is stored is deliberately little: the words (lower-cased, at most 100
characters), the language and project, a count, and the first and last day.
No address, no account, no time of day, nothing that links two searches.
Entries not seen for 90 days are dropped. Not counted at all:

- searches by signed-in accounts, and searches inside a
  [private project](/p/docuwaves/pages/private-projects);
- search-as-you-type — only the full results page counts, or every
  half-typed word would be a "gap";
- anything that looks like an e-mail address or a long number (customer,
  order or phone numbers): a search box is where people paste things.

It is on by default; `SEARCH_GAPS=off` switches it off and nothing is
written. If your site is public, your privacy policy can say:

> Search terms that return no results are stored anonymously and in
> aggregate — without IP address or account — for up to 90 days, to find
> missing documentation.

## "Was this page helpful?"

Under every published page, two buttons. A reader clicks one; nothing else
happens on their screen beyond a thank-you.

The report lists the pages that have been voted on, **worst ratio first** —
which is the order that answers the question an author actually has, namely
which page to open next. Pages with no votes are absent rather than listed
as zeroes; a documentation site has many pages and few votes, and rows of
zeroes would bury the handful that say something.

**Forgetting a page's votes** is one click. It is there because a page that
has been rewritten in response to its own feedback is being judged on text
nobody voted on. Without it the only honest thing to do would be to remember
to discount the numbers.

### Where the votes live, and what they are not

In the **database**, not in your content repository — the one kind of
content-ish state that is not a file. An anonymous click must not become a
commit, and a repository taking a write per vote would be unusable.

That has a consequence worth knowing: votes are the one thing a fresh clone
of your content repository would not bring back. They are included in the
[export](/p/docuwaves/pages/backups-and-updates).

A vote is: which page, which answer, and when. No address, no identifier, no
user-agent, nothing that ties two votes together. There is no way to ask
"who voted", because nothing is stored that could answer it. Votes are rate
limited per address so one browser cannot swing a page, and that counter is
in memory and never written down.

## Links that no longer go anywhere

The second report walks every published page and reports links that do not
resolve:

- **Pages and categories** in this instance that do not exist (usually a
  page that was renamed — a rename changes the slug).
- **Heading anchors** — `#installing-with-docker` when no such heading is on
  the target page. This one is easy to get wrong by hand and impossible to
  notice by reading.
- **Files** in a project's `assets/` that are gone.

**External addresses are deliberately not fetched.** Two reasons, and both
are about the report being useful: an application that fetches arbitrary
URLs written into its own content is an application that can be pointed at
your internal network from a pull request, and a link checker that reports
every site behind a login, a rate limit or a bot wall as "broken" is a
report nobody reads twice.

So the rule is: this checks the links whose target this instance actually
knows about. For the rest, a broken external link is the same problem every
site has, and the same tools solve it.
