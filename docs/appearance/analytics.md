---
order: 2
published: true
title: Analytics
---

Optional, off by default, and **Umami only**. An instance that does not
configure it loads no third-party script and makes no request on a reader's
behalf.

## Turning it on

Under **Branding**, two fields:

```yaml
analytics:
  umami_url: https://umami.example.com/script.js
  umami_website_id: 2f4a1b0c-1111-2222-3333-444455556666
```

Both, or neither. A script URL with no website id loads a counter that
reports to nowhere while looking, on the settings page, exactly like a
working one — so half a pair is dropped rather than stored.

Like everything else on that page it is written to `_site.yml` in your
content repository. It is not a secret: a Umami website id names a
dashboard, it does not open one.

## What it puts on the page

One tag, in the head, written by the server:

```html
<script defer src="…/script.js" data-website-id="…" data-do-not-track="true"></script>
```

**Not measured:** the admin area, and [preview
links](/p/docuwaves/pages/draft-preview-links). A preview link is an
unfinished page somebody was sent personally — counting the view would put
its address, and the fact that it was read, into a dashboard.

## Why a named tool and not a snippet box

A "paste your tracking code here" field is a script tag in the head of every
public page, writable by anyone with the admin password **and** by anyone
whose pull request to `_site.yml` gets merged. Two fields with two narrow
validators can only ever produce the tag above: the URL has to be an
absolute `http(s)` address ending in `.js`, and the website id has to be a
plain token. Anything else is dropped on the way in.

Umami is the tool because it is self-hostable, sets no cookies and keeps no
cross-site identifier — which is the only kind of analytics that fits an
application whose [scope
page](/p/docuwaves/pages/scope-and-limitations) lists everything it stores.
The tag is written with do-not-track respected.

Nothing here stops another tool being added in a later version. What is
being refused is arbitrary script.
