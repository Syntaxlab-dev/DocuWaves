---
order: 0
published: true
title: The MCP endpoint
---

DocuWaves speaks **MCP** (Model Context Protocol), so an AI assistant can be pointed at your documentation and actually work on it: *"what does the installation page say about Postgres?"*, *"document the two new environment variables"*, *"fix every broken link in the CachePanel docs"*.

It reads the same pages the site serves and — with a token that allows it — writes them back as real commits in your content repository, reviewable and revertable like any other contribution.

This is not a replacement for the admin area and not a second login. It is one endpoint, reachable with one kind of credential, doing exactly the subset of things a documentation assistant needs.

## Connecting

```
https://<your-docuwaves-domain>/api/mcp
Authorization: Bearer dwt_your_token_here
```

Create the token first — see [API tokens and scopes](/p/docuwaves/pages/api-tokens-and-scopes). The admin area's **API tokens** panel shows both lines ready to copy.

A quick check from a shell:

```bash
curl -s https://<your-docuwaves-domain>/api/mcp \
  -H 'Authorization: Bearer dwt_your_token_here' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## The protocol

Plain JSON-RPC 2.0 over `POST`. One message in, one message out.

- **Methods:** `initialize`, `ping`, `tools/list`, `tools/call`. Anything else answers "method not found" and names the four.
- **Protocol revisions:** `2025-06-18`, `2025-03-26` and `2024-11-05`. The client names the one it wants in `initialize`; a revision the server knows is echoed back, anything else gets the newest and the client decides whether it can live with that. An older client keeps working rather than failing the handshake.
- **Capabilities:** tools only. No resources, no prompts, no sampling, no logging — announcing a capability that is not implemented would have clients calling methods that answer nothing.
- **No SSE stream and no batching.** Batches were removed from the protocol in the 2025-06-18 revision, and nothing here runs long enough to need a stream. A batched request is refused with that explanation.
- **A notification** (a message with no `id`) is answered with `202` and an empty body, as JSON-RPC requires. The client's post-handshake `notifications/initialized` is accepted silently rather than answered with an error, which some clients treat as a reason to abandon the session.

### `initialize` tells the model the rules

The `instructions` string an MCP client puts in front of the model is filled in properly, because it is the only place to state what is not visible in any single tool's schema. It names:

- the token you are connected with, and its scope;
- that every write is a real Git commit authored under that token's name;
- that `update_page` **replaces** a page's body;
- that frozen documentation versions are read-only;
- that there is deliberately no way to delete anything here.

A read-only token is told so, and told that a write token is something the operator issues.

## Two different kinds of failure

The distinction is the MCP convention and it matters here:

| Shape | Means | Who reads it |
|---|---|---|
| A JSON-RPC `error` object | The **request** was wrong: malformed JSON, an unknown method, a tool name that is not in the catalogue | The client library |
| A `result` carrying `isError: true` | The request was fine and the **tool refused**: no such page, a frozen version, the wrong scope | The model |

That is why a refusal is not an `error`. "No category 'setup' in project 'cachepanel'; available: getting-started (Getting Started), reference (Reference)" is written for a model to act on, and it has to reach the model rather than only the client.

An unexpected internal failure is logged in full on the server and answered in summary, with an explicit "do not retry the identical call" — a bare 500 through a JSON-RPC transport is the least actionable thing a model can receive.

## Only this endpoint, and only this credential

- **An API token authorizes `/api/mcp` and nothing else.** Presented anywhere else under `/api/`, it is refused with the reason. The scopes describe documentation, not the admin API — a `read` token that could reach `/api/admin/*` would be able to delete a project, which is exactly the authority this feature is built to withhold.
- **An admin browser session is not accepted on `/api/mcp`.** Every answer here depends on the caller's scope, and a session has no scope.
- **There is no anonymous access**, ever.

An expired or revoked token is rejected exactly like an absent one — a single `401` for all three — so whoever holds a stolen token learns nothing about whether it ever worked.

## Rate limit

**120 requests per minute per token.** Far above any pace a real assistant sets, and low enough that an agent stuck in a retry loop stops within a second instead of hammering `git push`.

It is keyed per **token**, not per IP: an assistant and your own browser routinely arrive from the same address, and one misbehaving assistant must not be able to lock you out of your own admin area. Exceeding it answers `429` with the actual number in the message, rather than leaving a client to discover the limit by hitting it again.

Note that this is a throttle on a client that already authenticated, not a defence against guessing a token. 256 bits of entropy is that.

## The same index answers the built-in chat

If you configure it, the [documentation chat](/p/docuwaves/pages/the-documentation-chat)
on the reading site retrieves through the same search this endpoint exposes —
published pages, one language, one version per project. There is no second
retrieval path, so an answer from the panel and an answer from an assistant
holding a token are drawn from the same documentation.
