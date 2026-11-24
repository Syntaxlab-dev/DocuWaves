---
order: 4
published: true
title: A search box on your own website
---

One line of HTML puts the documentation's search on another website, such
as a product site, a shop or an intranet page. Readers search without
leaving that site and land on the matching page of the documentation.

```html
<script src="https://docs.example.com/widget.js" data-project="handbook" async></script>
```

Replace `docs.example.com` with this instance's address. The tag turns into
a **Search the docs** button where it stands. The button, or
**Ctrl/⌘+K** anywhere on the page, opens a search box. Results show as the
reader types, with the arrow keys and **Enter** to pick one.

## Options

Every option is an attribute on the same tag. All of them are optional.

| Attribute | What it does |
|---|---|
| `data-project` | Search only this project (its slug, as in `/p/handbook`) |
| `data-lang` | Search and link pages in this language, e.g. `de` |
| `data-version` | Search this documentation version of the project |
| `data-label` | The button text |
| `data-placeholder` | The hint in the empty search box |
| `data-accent` | The highlight colour, any CSS colour such as `#0f766e` |
| `data-trigger` | A CSS selector, e.g. `#help-search`: clicking those elements opens the box instead of a button of its own |
| `data-shortcut` | `off` leaves **Ctrl/⌘+K** to your page |
| `data-new-tab` | `off` opens results in the same tab instead of a new one |

The button and box speak German when `data-lang` (or, without it, the
page's language) is German, and English otherwise. A script can also open
the box with `DocuWavesSearch.open()`.

## Looks and privacy

The widget draws itself in an isolated part of the page (a shadow root), so
your site's styles can't break it and its styles can't change your site. It
follows the reader's light or dark mode.

It only ever shows what an anonymous reader may see. It searches without
cookies, so a private project stays out of the results even for a reader
who is signed in to DocuWaves in the same browser.

## Which sites may use it

`SEARCH_WIDGET_ORIGINS` decides which websites may read the search results:

```bash
SEARCH_WIDGET_ORIGINS=*                     # any website (the default)
SEARCH_WIDGET_ORIGINS=https://www.example.com,https://shop.example.com
SEARCH_WIDGET_ORIGINS=off                   # no other website
```

The default allows any website, because the widget can only reach what is
public anyway. Narrow it if you don't want other sites to build on your
search. Pages on this instance itself are never affected.
