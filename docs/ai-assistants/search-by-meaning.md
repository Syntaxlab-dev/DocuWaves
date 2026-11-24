---
order: 6
published: true
title: Search by meaning
---

Full-text search finds the words a reader typed. Search by meaning also
finds pages that are **about** what they asked, in other words. Someone
searching "make it start on boot" finds the page "Running as a systemd
service", even though it never says "boot".

It is **off by default** and optional. Without it, search works exactly as
before.

## Switching it on

Two environment variables, with a third if the provider wants a key:

```bash
EMBEDDINGS_API_BASE=http://ollama.example.lan:11434/v1
EMBEDDINGS_MODEL=nomic-embed-text
# EMBEDDINGS_API_KEY=...   only if the endpoint wants one
```

The endpoint must speak the OpenAI-compatible `POST {base}/embeddings`.
A local [Ollama](https://ollama.com) does (`ollama pull nomic-embed-text`),
and so do llama.cpp's server, OpenAI and most hosted providers. **With a
local model, no page text leaves your server.** Other local models that
work well include `mxbai-embed-large` and, for German and other languages,
`bge-m3`.

Restart DocuWaves. It then works through the published pages in the
background. **Diagnostics** shows the model and how many sections are
indexed, for example "312 of 312 sections indexed", along with the last
error if the endpoint could not be reached.

## What readers see

On the search results page, pages found by meaning join the full-text
results:

- A page found both ways rises to the top.
- A page found only by meaning is marked **related**. Its snippet is the
  section that matched, because the reader's words may not be in it.

Search as you type, in the header box, stays plain full-text search. One
request to the model per keystroke would be slow and costly for no gain. The
**documentation chat** and the **MCP** `search` tool use both kinds of
search together, so assistants find pages by meaning too.

The usual rules still apply. A search returns only published pages, in the
reader's language and the version they are reading. Private projects appear
only for signed-in accounts.

## How it works

- Each published page is cut into sections at its headings, and long
  sections again at sentence ends.
- Each section is sent to the model once and gets a vector: a list of
  numbers that places texts with similar meaning close together.
- A search compares the question's vector with every section's vector. A
  page scores as its best section.
- Vectors are stored in the database, keyed by the model and the exact
  text. An unchanged section is never sent twice, and editing a page only
  re-sends the section that changed. A reindex costs nothing. Switching to
  another model indexes everything once with the new one.

If the endpoint is down, search falls back to full-text results. It never
fails because of this feature.

## Choosing between local and hosted

A local model costs nothing per request and keeps the text on your server.
`nomic-embed-text` runs comfortably on a CPU. A hosted model may match a
little better in some languages, but every page and every search query is
sent to the provider. Indexing a few hundred pages takes well under a minute
with either.
