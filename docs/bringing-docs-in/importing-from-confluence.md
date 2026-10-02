---
order: 1
published: true
title: Importing from Confluence
---

In Confluence, in the space: **Space settings → Export space → HTML**. Upload
the ZIP it produces as it is, under **Import**. Every page is converted to
Markdown and then follows the [same rules as any import](/p/docuwaves/pages/importing-a-zip):
preview first, drafts, one commit.

## The page tree

Confluence nests pages without limit; DocuWaves has one level of categories.
So:

- the space's **home page** and every top-level page **without** children go
  into "General",
- every top-level page **with** children becomes a **category** — the page
  first, then everything below it in Confluence's order.

## Macros

| In Confluence | In DocuWaves |
|---|---|
| Info, Tip | NOTE, TIP callouts |
| Note (yellow) | WARNING callout |
| Warning (red) | CAUTION callout |
| Code block | fenced code with its language |
| Expand | a callout with the expand's title |
| Status | **bold** text |
| Emoticons, @mentions | their text |
| Table of contents, attachments list, labels, likes, comments, page footer | left out — DocuWaves shows its own contents |

Any other macro keeps the text it rendered to and is **listed in the
preview**, so you know which pages to look at afterwards.

## Links and attachments

Links between pages follow the pages. Images from `attachments/` are copied
like any other image. Attachments that are not images or media — PDFs,
Office files — are not imported and are listed.
