---
order: 3
published: true
title: What it costs
---

The honest answer has two halves, and only one of them is about DocuWaves.

## DocuWaves' half: nothing

The MCP endpoint is a **tool server**. It answers an assistant's requests about your documentation — list the projects, read this page, search for that phrase, write this text back — and it **never calls a language model itself**.

So it needs no AI provider account, no API key, and no configuration of any kind beyond the token you issue. It adds nothing to any AI bill. Turning it on costs you a token and some CPU on requests you can count.

## The other half: whatever your assistant costs

That is between you and whoever provides the assistant, and it does not change because DocuWaves is on the other end.

- On a **subscription plan**, the usage sits inside the plan.
- Through a **pay-as-you-go API**, the provider bills per request.

Documentation work is not cheap in tokens, either. `read_page` returns a page's full Markdown, and `update_page` requires the complete new body — so editing a long page means that page's text crossing the wire at least twice.

That distinction is worth knowing before you hand out a token. "It's free" would be true for this endpoint and wrong for the other half of the setup.

## Keeping the cost down

- Use a **`read` token** when reading is all that is needed.
- Point the assistant at **one project** — `search` and `list_pages` both take a project, and scoping the work scopes the reading.
- Prefer `search` to walking every page with `list_pages` and `read_page`.
- Give the token an **expiry date**, so an assistant nobody is watching any more stops working.

## What it costs your server

Very little, and it is bounded. Requests are capped at [120 per minute per token](/p/docuwaves/pages/the-mcp-endpoint), reads are ordinary indexed queries, and a write is one `git commit` and one `git push` plus a reindex.

The reindex is the expensive part on a large instance, since it runs after every write. An assistant rewriting fifty pages one at a time does fifty of them. That is a reason to batch a documentation sprint sensibly, not a reason to avoid the endpoint.
