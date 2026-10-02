---
order: 1
published: true
title: Page templates
---

A new page opens empty, with four skeletons offered above the editor. Pick
one and it fills the body in; type a character instead and the offer is
gone.

## The four

| Template | Structure |
|---|---|
| **How-to** | Prerequisites, numbered steps, a way to check it worked, a troubleshooting table, what comes next |
| **API reference** | An at-a-glance table, parameters, an example call, the response and its fields, an error table |
| **Release notes** | New / Changed / Fixed, upgrade notes, known issues |
| **Course module** | Learning goals, the material, an exercise, questions to check understanding |

## They are structure, not text

Every line a template inserts is a heading, a table header, or an
angle-bracketed slot like `<what the reader will be able to do>`. None of it
is prose you are meant to keep.

That is deliberate. A template that shipped real sentences would be either
wrong for the page being written or copied into it unread — and
documentation that contains text nobody wrote is worse than documentation
that is missing a section. What genuinely carries over between pages is the
*shape*: that an API reference lists its errors, that release notes separate
"changed" from "fixed", that a how-to says what to have ready before step 1.
That part is what a template is.

## Only while the page is empty

The picker appears when the body is empty and disappears as soon as it is
not. Applying a template **replaces the whole body**, so offering it next to
text somebody has written would be the most destructive button in the
editor.

This applies per language tab. An empty translation is an empty page too,
and it is the one most likely to want a structure — so the picker is there
as well, in that language.

## Language

Templates exist in German and English. You get the language the page is
being written in; on an instance that never configured
[languages](/p/docuwaves/pages/enabling-a-second-language) there is no
language code to go on, so you get whatever the admin interface is set to.
A language no translation exists for falls back to English rather than
leaving the picker empty.

They are shipped with the application, not stored in your content
repository — so they arrive with an update and there is nothing to migrate.
There is currently no way to add your own; if you want a fifth structure,
write the page once and copy it.
