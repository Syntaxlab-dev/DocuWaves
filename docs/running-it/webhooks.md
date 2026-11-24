---
order: 8
published: true
title: Webhooks
---

DocuWaves can post to a **Discord**, **Slack**, **Microsoft Teams** or
**Matrix** channel — or send JSON to any address — when the documentation changes. They are environment
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
- Microsoft Teams gets an Adaptive Card with the page's title, summary and an
  **Open the page** button. Both kinds of Teams address work: a **Workflow**
  ("Post to a channel when a webhook request is received", on
  `logic.azure.com` or `api.powerplatform.com`) and an old **Incoming
  Webhook** connector (`webhook.office.com`).
- Matrix gets a notice (`m.notice`, the message type for bots) with an HTML
  version. See below for the address.
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

If an address does not show which service it is — a relay of your own in
front of Teams, say — name the format at its end: `#teams`, `#matrix`,
`#slack`, `#discord` or `#json`. That part is never sent.

## Matrix

Matrix has no webhooks of its own. There are two ways in:

**Directly, with a bot account.** Create an account for DocuWaves, invite it
to the room, and give its access token in the room's send address:

```env
WEBHOOK_URLS=https://matrix.example.org/_matrix/client/v3/rooms/!roomid:example.org/send/m.room.message?access_token=syt_…
```

DocuWaves recognises `/_matrix/client/`, moves the token into the
`Authorization` header and sends each message with its own transaction id,
so the retry below can never post it twice. Use the room's ID (starting with
`!`, under the room's advanced settings), not its alias.

**Through [Hookshot](https://matrix-org.github.io/matrix-hookshot/).** If your
homeserver runs it, create a generic webhook in the room and add `#matrix`
to the address Hookshot gives you:

```env
WEBHOOK_URLS=https://hookshot.example.org/webhook/abc123#matrix
```

## Delivery

In the background, with a 5-second timeout and one retry. A slow or dead
endpoint never slows down or fails a save; it shows up in the log — with the
host name only, because the path of a webhook (and a Matrix address's
token) is its secret.

Not every change needs a webhook: the
[RSS feeds](/p/docuwaves/pages/whats-new-changelog-and-rss) work with every
chat tool's feed integration and need no configuration at all.
