---
order: 11
published: true
title: Review notes
---

A page can carry one line saying who checked it and when:

> Reviewed by Alex Winter on 4 September 2026

It sits under the text, next to "Last updated", in the same quiet register.
No icon, no badge, no colour.

## Setting one

Open the page in the editor. Under the title is either the note or **Mark as
reviewed**, which asks for a name — prefilled with the account you are
signed in as, and editable, because the person carrying a change into the
repository is often not the person who read it.

The date is the instance's own, always today, and never something you can
type. A note whose date could be entered would be a note that can say
anything.

It is stored in the page's file, so it is versioned like everything else:

```markdown
---
title: Installation
order: 0
published: true
reviewed_by: Alex Winter
reviewed_at: "2026-09-04"
---
```

Both keys or neither. A name with no date says nothing about whether the
check is from this week or from three years ago, so half a note is written
as no note. On a page nobody has reviewed the keys are absent entirely — an
instance that never uses this sees no change in any of its files.

## It is dropped the moment the text changes

This is the only thing that makes the note worth anything.

Edit a page's body and save, and the note goes with it. What was checked was
a **text**, and after an edit the note would be claiming that somebody
approved words they have never seen.

Renaming the page, or moving it to another category, keeps the note —
neither changes a sentence of what was read. Restoring an older version from
the [history](/p/docuwaves/pages/page-history) drops it, because that
replaces the body too.

Per language, like publishing. A translation is a different text that a
different reader reads; the German page having been checked says nothing
about the English one.

## What it is not

**It is a note, not a signature.** It establishes nothing about identity: it
says what somebody typed into a box while signed in as some account. It has
no legal or regulatory weight, it is not an approval gate — a page can be
published with no note at all — and DocuWaves does not check it, enforce it
or attach meaning to it beyond displaying it.

What it *is* good for: a page in a documentation set of two hundred, where
the useful question is "has anybody looked at this since we shipped 3.0",
and the answer is either a name and a date about the current text or
nothing.

See [Scope and limitations](/p/docuwaves/pages/scope-and-limitations) for the
longer version of that boundary.
