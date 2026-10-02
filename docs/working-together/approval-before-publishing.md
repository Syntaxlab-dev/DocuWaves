---
order: 2
published: true
title: Approval before publishing
---

A project can require that **nothing goes live without a second person's
approval**. Off by default; switch it on in the project's settings under
**Approval → Approval required**, or in the file:

```yaml title="content/handbook/_project.yml"
name: Handbook
review: required
```

## What changes for authors

**A published page keeps its live text while somebody works on it.** Saving
in the editor stores a *proposed version* next to the page; readers keep
reading the live one. The editor says so after every save.

**A draft goes live through an approval.** The publish switch is off for
drafts in such a project; submit the page instead.

When the text is ready: **Submit for approval**, optionally with a note for
the reviewer ("please check the second paragraph"). Until somebody decides,
you can **withdraw** the submission, or **discard** the proposed changes
entirely — the live page never had them.

## What reviewers do

**Approvals** in the admin header lists everything waiting, with a counter.
An entry opens the page in its editor, where the review panel shows:

- who submitted it, when, and their note,
- **Show changes** — the proposed text against the live one, line by line,
- **Approve**, and **Request changes** with a comment.

Approving publishes in one step: the proposal replaces the live text (one
commit), and the approver's name and the date are written as the page's
[review note](/p/docuwaves/pages/review-notes). Requesting changes sends the
page back to its author with the comment; they edit and submit again.

## Four eyes

**Whoever last changed the text cannot approve it** — not the person who
submitted it, the person who *wrote* it. The Approve button is disabled for
them, and says why. Editing a submitted text takes the submission back, so
nothing changes under a reviewer's eyes.

**Read** accounts can approve and request changes, and nothing else.
Reviewing is reading, and the right reviewer is often somebody who should
not be editing.

## Assistants and synced docs

[AI assistants](/p/docuwaves/pages/the-mcp-endpoint) go through the same
door: in such a project, an assistant's change to a live page — or
`published: true` on a new one — is submitted for approval automatically,
and a person approves it.

Projects whose pages come from a code repository
([docs-as-code](/p/docuwaves/pages/docs-as-code)) are approved where they
are written: the pull request is the review.

## Telling a channel

Two optional [webhook](/p/docuwaves/pages/webhooks) events,
`review_requested` and `review_decided`, announce submissions and decisions
in a team channel. They carry no page text — what waits for approval is not
published yet.

## Where it lives

In the content repository, like everything else: the review state is a few
lines of front matter on the text under review, and a proposal is a file in
`<category>/_pending/`. The queue survives a reindex, a restore from backup
and a fresh clone.
