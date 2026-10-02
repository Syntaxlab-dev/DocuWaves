---
order: 10
published: true
title: Draft preview links
---

An unpublished page is invisible to readers, which leaves a gap: the
colleague who knows whether the steps are right, or the person the release
notes are about, has no way to read it. A preview link is that gap, and
nothing wider — one URL, one page, one expiry date.

## Making one

In the page editor, open **Draft preview**, pick how many days, and create
one. The link is shown **once**:

```
https://docs.example.com/preview/dwp_xTEkQ9UTjOvJA7BeNKUztYCCglYLtxKat2lbucDQhr4
```

Copy it then. Only a checksum of it is stored, exactly as with [API
tokens](/p/docuwaves/pages/api-tokens-and-scopes), so a link that was not
copied cannot be shown again — making another one costs a click.

Send it however you already send things. DocuWaves sends no mail.

## What the recipient gets

The page, published or not, and nothing else. No navigation, no sidebar, no
search box, no other draft in the same category, no way into the admin area.
The view is deliberately not the normal documentation layout, because every
one of those things is a way out of the one page they were given.

Above the text it says that this is a preview, that it is not part of the
published documentation, that it may still change, and the date the link
stops working. If the page has been published in the meantime it says that
too, so nobody reviews something that has already gone out.

## Limits, and why each one

- **Ten links per page.** More than that means nothing is ever being
  revoked, not a use case.
- **Ninety days maximum, and no "never expires".** Unlike an API token,
  which an operator configures once and uses for years, a preview link is
  made for a conversation that is over in a week. A link that outlives its
  reason is the one that turns up in a forwarded email two years later.
- **Rate limits do not apply** — there is nothing to guess. The token is 32
  bytes of randomness.

## What ends a link

- Its date passes.
- You revoke it, in the same panel.
- The page is deleted; its links go with it, so a slug somebody reuses later
  cannot inherit one.

**Renaming the page does not break it.** Links follow the page's slug when
it changes, so fixing a typo in a title does not silently kill every link
you have handed out.

## Search engines

`/preview` is excluded twice over: the app answers those URLs with
`noindex`, and `robots.txt` disallows the path. Note that if your reverse
proxy or hosting panel serves its own static `robots.txt` in front of
DocuWaves, that file is the one crawlers read — check it.

## This is still not access control

A preview link is unguessable, not secret. Whoever has the URL has the page,
and can pass it on. It is the right tool for showing a draft to a named
person for a week; it is not a way to keep something confidential. Anything
that must actually be secret does not belong in a documentation instance —
see [Scope and limitations](/p/docuwaves/pages/scope-and-limitations).
