---
order: 0
published: true
title: Accounts and roles
---

The first person to open a new instance creates the first account, and it is
an administrator. Everybody after that is created by an administrator under
**Accounts**.

## The four roles

| Role | May |
|---|---|
| **Reader** | Read the documentation, including [private projects](/p/docuwaves/pages/private-projects), on the public site. Never the admin area. |
| **Read** | Open the admin area and see everything in it — drafts, page history, which translations exist, the feedback and broken-link reports. Change nothing. |
| **Write** | All of the documentation: projects, categories, pages, images, versions, review notes, preview links. |
| **Manage** | The above, plus the instance itself: other accounts, API tokens, branding, diagnostics and the export. |

**Read** is the role worth explaining, because it is the one with a job:
the reviewer. Somebody asked whether a page is right, who should be able to
read the draft and its history and *not* be able to quietly fix it in
passing. (To show one draft to somebody with no account at all, use a
[preview link](/p/docuwaves/pages/draft-preview-links) instead.) In a project
that [requires approval](/p/docuwaves/pages/approval-before-publishing), Read
accounts can **approve** and **request changes** — the two changes reviewing
needs, and nothing else.

The line between **Write** and **Manage** is not seniority, it is blast
radius. Rewriting every page is recoverable from the Git history; handing
out a credential, changing what the site claims to be, and downloading the
whole instance are different kinds of mistake.

**Reader** exists for [private projects](/p/docuwaves/pages/private-projects):
a colleague who should read the internal docs but has no business seeing
drafts and page history. Every other role can read private projects too. On
an instance without private projects nobody needs it — public documentation
needs no login.

## How it is enforced

In one place — the middleware in front of every API route — and by two rules
rather than a list of endpoints:

- **The write rule is the HTTP method.** `GET` and `HEAD` read; anything
  else changes something. So "Read" is *"GET and HEAD only"*, stated once,
  and an endpoint added in a later version is covered by it before anybody
  has to remember to think about roles.
- **The manage rule is a short list of path prefixes**: accounts, tokens,
  branding, diagnostics, export.
- **The reader rule is the admin prefix**: a Reader is refused everything in
  the admin area.

The role is read from the database **on every request**, not from the
session cookie. A role that is taken away is taken away now, for sessions
that are already open. Lowering a role, resetting somebody's password, or
deleting an account also ends that account's sessions — the middleware had
already stopped them, but being returned to the login screen beats clicking
around an interface that has quietly started refusing everything.

## Locking yourself out

Two things are refused, always:

- **Deleting your own account.** Unlike a role change there is no version of
  it that leaves you anywhere.
- **Resetting your own password from the Accounts panel.** That panel's
  password box does not ask for the current password — it is for the case
  where somebody else is locked out. Pointing it at yourself would be a way
  around **Account**, which does ask.

And one is refused when it would leave nobody in charge: **the last
administrator cannot be demoted or deleted**, including by themselves.

An administrator *may* step down while another one is left. That is what
makes a handover possible: make her an administrator, then make yourself an
editor. It signs you out, which the confirmation says before it happens.

## Deleting an account does not touch what that person wrote

The content repository attributes commits by **name**. Their history keeps
their name on it, forever, with no account row required. Removing somebody's
access and erasing their authorship are different things, and this only does
the first.

## Upgrading from a single-account instance

Nothing to do. The account that already exists becomes the administrator,
its sessions keep working, and the three new columns are added to the
existing table in place — the table holding the password hashes is never
rebuilt.

## Single sign-on

[SSO](/p/docuwaves/pages/single-sign-on) matches an identity from your
provider to an account **that already exists here**, by username. Being able
to authenticate against the provider does not create an account: accounts
are created deliberately, by an administrator, and the role is decided here
rather than by whoever the provider lets in.
