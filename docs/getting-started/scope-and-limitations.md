---
order: 4
published: true
title: Scope and limitations
---

DocuWaves is a tool for writing, versioning and publishing documentation. This page states what that includes and what it does not, so that nobody has to infer it — and so that anyone weighing it up for a regulated setting can rule it out in half a minute rather than half a project.

## What it is

- **Writing.** A Markdown editor with a preview, and the same content editable as plain files in a Git repository.
- **Versioning.** Every save is a Git commit with an author, a message and a diff. A release's documentation can be frozen into a snapshot that is read-only from then on.
- **Publishing.** A public site with navigation, full-text search, per-page metadata and an optional second language.

That is the whole of it. Everything else in these docs is detail about those three things.

## What it is not

**Not a quality-management system, and not compliance software.** There is no electronic signature, no locked record and no audit trail beyond the ordinary Git history of the files. By default a page goes live when one person switches **Published** on. A project can [require a second person's approval](/p/docuwaves/pages/approval-before-publishing) — a useful four-eyes habit, and nothing more than that: it records who approved in the page's front matter, which anybody with access to the repository can edit.

There is a [review note](/p/docuwaves/pages/review-notes) — a line saying who checked a page and on what day, which disappears again the moment the text is edited. Read it for what it is: somebody typed a name into a box while signed in as some account. It is not a signature, it establishes nothing about identity, it gates nothing, and a page can be published without one. It is a reminder, useful for the question "has anybody looked at this since we shipped 3.0", and it is not evidence of anything.

**Certified against nothing.** No certification, accreditation, conformity assessment or audit of any kind is claimed for this software — not against any standard, framework or regulation, named or unnamed. Nobody has assessed it for that purpose. If a requirement of yours reads "the system must be certified", "the system must be validated", or "the system must be qualified", DocuWaves does not satisfy it, and no way of configuring it will.

**Roles, but not separation of duties.** There are [accounts with three roles](/p/docuwaves/pages/accounts-and-roles), so "the person who writes" and "the person who reviews" *can* be two different people, and a reviewer can be given an account that cannot change anything. What is missing is the enforcement: nothing requires a second person to have looked, nothing prevents an editor publishing their own page, and there is no per-project or per-page permission — an account that may edit may edit everything.

Attribution is by **name**, in the commit. It is a record of which account was signed in, or of which credential wrote something when the change came through an [API token](/p/docuwaves/pages/api-tokens-and-scopes) — not a signature, and not proof of who was holding either.

**Not access control.** An unpublished page is invisible to readers; it is not secret. It is a committed file, and anyone with the content repository has it. Anything that must actually be confidential does not belong in a documentation instance — see [Drafts and publishing](/p/docuwaves/pages/drafts-and-publishing).

## What it stores about people

Everything you write — projects, categories, pages, images, branding — is files in your content repository. Whatever personal data ends up there is data you put there, and it is yours to manage.

DocuWaves adds three things of its own. They live in the database, which is otherwise only a rebuildable index over your files:

| Table | What it holds |
|---|---|
| `auth` | One row per [account](/p/docuwaves/pages/accounts-and-roles): the username, a bcrypt hash of the password, the role, when it was created and when it last signed in. Never the password itself. With [single sign-on](/p/docuwaves/pages/single-sign-on) the username comes from your provider and the stored hash is of a random value that is never used |
| `sessions` | One row per active login: a random session id, the username, when it was created, when it was last seen, the client IP address and the browser's user-agent string. The row is deleted on logout, and when the account is deleted or its role is lowered |
| `api_tokens` | One row per API token: the name you gave it, a SHA-256 hash of its value, its scope, its expiry, when it was created and when it was last used. Never the token itself |
| `preview_links` | One row per [preview link](/p/docuwaves/pages/draft-preview-links): a SHA-256 hash of its value, which page it points at, its expiry, when it was made and by whom. Never the link itself. Expired rows are deleted rather than kept |
| `page_feedback` | One row per ["was this page helpful?"](/p/docuwaves/pages/reader-feedback-and-link-checking) answer: which page, which answer, and when. No address, no identifier, no user-agent — nothing that ties two answers together |

Beyond that:

- **One cookie, for the admin only.** The signed session cookie is set when you log in and lasts 30 days. A reader who never logs in is never sent a cookie at all.
- **No third-party requests unless you ask for them.** By default the application calls nothing outside itself except your own Git remote. Three things can change that, and all three are off until you configure them: your own [SSO provider](/p/docuwaves/pages/single-sign-on); [Umami analytics](/p/docuwaves/pages/analytics), which adds one script tag to public pages (never to the admin area or to preview links); and the [documentation chat](/p/docuwaves/pages/the-documentation-chat), which sends a reader's question and excerpts of your published pages to the model endpoint you named. An instance that configures none of them still makes no third-party request at all.
- **No request log of its own.** The container is deliberately started without one, because a reverse proxy in front of it already logs requests with the real client IP. That log is yours, in your proxy, under your retention policy.
- **A little browser storage.** The reader's light/dark preference, and an author's unsaved editor text, are kept in that browser's own storage. Neither is uploaded and neither reaches the server.

That list is complete as of this version. If you need it for a data-protection record, those five tables plus your proxy's access log are the whole inventory the software itself creates. Note what is *not* in it: there is no table of chat questions, no analytics store of DocuWaves' own, and no record of who read what.

## The licence, in plain words

DocuWaves is MIT-licensed. You may run it, change it, and pass it on. It comes **with no warranty of any kind**: nobody promises it works, nobody promises it is fit for what you have in mind, and nobody accepts liability if it loses data or gets something wrong. That is not a formality bolted onto a stronger promise underneath — it is the entire promise, and it is the same one every MIT-licensed project makes.

Practically, that means the backups are yours to make. The content repository is the copy that matters; see [Backups and updates](/p/docuwaves/pages/backups-and-updates).

## A page that looks official is still just a page

You can write anything you like into a page: a revision table, a document number, an "Approved by" line, a header that looks like a controlled document. DocuWaves will render it faithfully.

It will not check it, enforce it, or attach any meaning to it. Such a layout is a starting structure for a process **you** run, and it carries no legal effect. That DocuWaves displayed it is evidence of nothing beyond the commit that put it there — the same evidence a text file in a folder would give you.

## Who decides what it is fit for

You do. Whoever runs an instance chooses what it is used for, and is responsible for that choice — including whether the honest limits above are compatible with the obligations they are under. This page exists so that decision can be made with the facts rather than around them.

If you need controlled documents with enforced review, signatures and an auditable approval trail, use software built and assessed for that. If you need documentation that is quick to write, honestly versioned, portable in a Git repository, and cheap to host on your own hardware, that is exactly what this is.
