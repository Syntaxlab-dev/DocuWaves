---
order: 6
published: true
title: Webhooks
---

DocuWaves can post to a **Discord** or **Slack** channel — or send JSON to
any address — when the documentation changes. They are environment
variables rather than an admin setting, because a webhook address is itself
a credential and everything edited in the admin area ends up in the content
repository.

```env
WEBHOOK_URLS=https://discord.com/api/webhooks/…,https://example.org/docs-hook
WEBHOOK_EVENTS=published,updated
WEBHOOK_SECRET=a-long-random-string
```

## Events

| Event | When | On by default |
|---|---|---|
| `published` | a draft goes live | yes |
| `updated` | the title or text of a published page changes | no |
| `unpublished` | a published page goes back to draft, or is deleted | no |
| `review_requested` | a page, or changes to a live page, was submitted for [approval](/p/docuwaves/pages/approval-before-publishing) | no |
| `review_decided` | a submission was approved or sent back | no |

Only a **change** counts. Saving a published page without touching its title
or text — moving it to another category, say — sends nothing, and neither
does anything done to a draft. Leave `updated` off if every typo fix would
be too much for your channel.

The two review events are meant for a team's own channel. They carry no
text from the page — what waits for approval is not published yet — only its
title, whether it is a new page or a change, the decision, and a link to the
admin area.

Private projects never send anything: a channel's members are unknown.

## Formats

The format follows the address:

- `discord.com` gets an embed. No mentions are ever resolved, so a title
  containing `@everyone` pings nobody.
- `hooks.slack.com` gets a linked line of text.
- Anything else gets JSON:

```json
{
  "event": "published",
  "occurred_at": "2026-09-29T10:00:00+00:00",
  "page": {"title": "Installation", "slug": "installation", "language": "en",
           "version": "", "summary": "How to install …",
           "url": "https://docs.example.com/p/demo/pages/installation"},
  "project": {"name": "Demo", "slug": "demo"},
  "category": {"name": "Guides", "slug": "guides"}
}
```

with the header `X-DocuWaves-Event` and, when `WEBHOOK_SECRET` is set,
`X-DocuWaves-Signature: sha256=<HMAC-SHA256 of the body>` — recompute it on
your side to know the message really came from your instance. Links need
`PUBLIC_BASE_URL`.

## Delivery

In the background, with a 5-second timeout and one retry. A slow or dead
endpoint never slows down or fails a save; it shows up in the log — with the
host name only, because the path of a Discord or Slack webhook is its
secret.

Not every change needs a webhook: the
[RSS feeds](/p/docuwaves/pages/whats-new-changelog-and-rss) work with every
chat tool's feed integration and need no configuration at all.
