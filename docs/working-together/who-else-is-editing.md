---
order: 1
published: true
title: Who else is editing
---

Open a page in the editor while somebody else has it open, and a note above
the editor says so:

> *Michel is editing this page right now (for 5 min) — with unsaved changes.*

The page list marks pages that are open elsewhere with a pencil. Your own
second browser tab counts too — *"You also have this page open in another
tab"* — because its save would overwrite this one just the same.

## A warning, never a lock

Anybody can still save. Locks are worse than the problem they solve: a lock
held by a laptop that went to sleep blocks everybody until somebody finds
out whose it is.

What stops two people overwriting each other is the save itself: a save made
on top of text that changed in the meantime is refused, and you are asked
before anything is overwritten. The other person's version stays in the
[page history](/p/docuwaves/pages/page-history) either way.

## How it works

Each open editor checks in every 20 seconds. One that stops — a closed
laptop, a crashed browser — disappears after a minute, and closing the
editor removes it at once. Read-only accounts see who is there without being
announced themselves.

Nothing of this is stored: it lives in the server's memory, and after a
restart it is back within 20 seconds.
