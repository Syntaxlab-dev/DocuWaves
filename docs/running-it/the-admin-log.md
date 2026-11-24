---
order: 5
published: true
title: The admin log
---

**Log**, in the admin area's header, lists what administrators changed
about the instance itself, newest first:

- accounts created, deleted, given another role or other
  [permissions per project](/p/docuwaves/pages/accounts-and-roles), and
  passwords and two-factor sign-ins reset
- API tokens created and revoked
- branding saved and branding images uploaded
- the [export](/p/docuwaves/pages/backups-and-updates) downloaded

Each entry says when, who, from which address, what, and to what. Only
administrators can read it.

## Why page changes are not in it

They are already written down, better: every change to the documentation is
a commit in the content repository, with its author, and **Activity** shows
them. What an administrator does to the instance writes no file and leaves
no commit, which is why it needs a log of its own.

## What it never contains

No password, no token value and no request body. Branding changes are
listed by the names of the settings that changed, not their values. A log is
the thing that gets copied into a support thread, so it is written as if it
will be.

## How long it is kept

The newest 5,000 entries. Most instances never reach that, and nothing has
to be cleaned up by hand.

A change made through a route that does not describe itself still appears,
as its method and address. The log is filled in where requests are checked,
not only where each feature remembers to write to it.
