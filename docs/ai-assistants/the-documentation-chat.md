---
order: 4
published: true
title: The documentation chat
---

A panel on every reading page: a reader asks a question and gets an answer
built from the published pages, with those pages listed under it.

**It is off until you configure a model.** DocuWaves ships none, bundles no
API key, and an instance that leaves the three variables blank makes no
outbound request for this, ever.

## Configuring it

```bash
CHAT_API_BASE=http://ollama.example.lan:11434/v1
CHAT_MODEL=llama3.1:8b
CHAT_API_KEY=ollama          # any non-empty value for a local server
```

The endpoint is the OpenAI-compatible one — `POST {base}/chat/completions` —
which a local **Ollama**, a llama.cpp server, OpenAI and most hosted
providers all speak. Self-hosted documentation does not have to mean a cloud
account.

All three or none: a base URL with no model names nothing to call, and a
model with no base URL has nowhere to call.

**Why environment variables and not a settings page.** The key is a
credential, and every setting the admin UI writes goes into `_site.yml` — a
file in a repository built to be cloned and read in pull requests. The same
reasoning keeps [API tokens](/p/docuwaves/pages/api-tokens-and-scopes) out
of the content repository. Whether it took shows up under
[Diagnostics](/p/docuwaves/pages/diagnostics).

## How an answer is made

The question goes through the same search the site's search box and the [MCP
endpoint](/p/docuwaves/pages/the-mcp-endpoint) use: published pages, the
reader's language, and the project and documentation version they are
standing in. Somebody asking while reading the 2.0 documentation is answered
out of 2.0.

The best few pages are converted to plain prose, numbered, and handed to the
model as the **only** material it may use. The answer comes back with all of
those pages listed under it, marked by whether it actually cited them — the
ones it passed over are what a reader whom the answer did not help wants
next.

## What it will not do

- **Answer from anything but your documentation.** The instruction forbids
  filling gaps from general knowledge and forbids inventing a page, a link,
  a flag or a version number.
- **Answer when nothing matched.** If the search finds no pages, **no model
  is called at all** and the reader is told the documentation does not cover
  it. Asking a model to answer with nothing in front of it is asking it to
  invent something, at your expense.
- **Cite a page it was not given.** A `[7]` against four supplied sources is
  dropped before the answer is rendered, so it cannot become a link to
  nowhere.
- **Remember.** There is no conversation table and no question log. A
  question is a request parameter, the answer is the response, and both are
  gone when it returns. Each question is asked against the documentation,
  not against the previous answer.
- **Render as HTML.** The model's output is shown as plain text, so nothing
  it produces can act on the page.

Before the first question, the panel says that the text goes to the model
you configured and names it. What your provider does with it is between you
and them.

## Costs and abuse

This is a **public** endpoint that spends your model budget. It is rate
limited to six questions a minute per address, and a question is capped in
length. A question that matches no pages costs nothing at all, because it
never reaches the model.

If you are pointing it at a paid API rather than a local model, that limit
is the only thing between your bill and the open internet — put the usual
rate limiting in your reverse proxy as well.

## It is a summary, not the documentation

The panel says so under every answer, and it is worth repeating here:
answers can be wrong. The pages are what the documentation says; the answer
is a model's paraphrase of a few of them, and it is one click away from the
originals precisely so a reader can check.
