---
order: 17
published: true
title: Steps, cards and badges
---

Three small blocks for pages that guide, point the way, or mark something
as new. Each is ordinary Markdown with a marker DocuWaves understands, so the
same file still reads correctly on GitHub or in any editor: the markers are
HTML comments, which are invisible there, and what is left is a plain list.

## Steps

A numbered list after `<!-- steps -->` is shown as steps: a large number for
each, joined by a line, so a reader can see where they are in a procedure.

```markdown
<!-- steps -->

1. **Download** the installer for your system.
2. **Run** it and follow the prompts.
3. **Open** the address it prints at the end.
```

<!-- steps -->

1. **Download** the installer for your system.
2. **Run** it and follow the prompts.
3. **Open** the address it prints at the end.

A step can hold more than one paragraph, code blocks and images, as any list
item can — indent them under the item.

## Cards

A list after `<!-- cards -->` is shown as a grid of cards, for an overview
page that points to the sections behind it. A link in an item makes the whole
card clickable; a bold link or bold text at the start is its title.

```markdown
<!-- cards -->

- **[Tabs](/p/docuwaves/pages/tabs)** The same step for several systems.
- **[Callouts](/p/docuwaves/pages/callouts-and-code-blocks)** Notes, tips and warnings.
- **[Diagrams](/p/docuwaves/pages/diagrams)** Flowcharts and sequences from text.
```

<!-- cards -->

- **[Tabs](/p/docuwaves/pages/tabs)** The same step for several systems.
- **[Callouts](/p/docuwaves/pages/callouts-and-code-blocks)** Notes, tips and warnings.
- **[Diagrams](/p/docuwaves/pages/diagrams)** Flowcharts and sequences from text.

The cards fill as many columns as the screen has room for and become one
column on a phone.

## Badges

Inline code that starts with `badge:` is shown as a small label — to mark a
feature as new, an option as deprecated, a setting as needing a restart.

| Written | Shown as |
|---|---|
| `` `badge:Beta` `` | `badge:Beta` |
| `` `badge:success:New` `` | `badge:success:New` |
| `` `badge:warning:Deprecated` `` | `badge:warning:Deprecated` |
| `` `badge:danger:Removed in 3.0` `` | `badge:danger:Removed in 3.0` |
| `` `badge:neutral:Linux only` `` | `badge:neutral:Linux only` |

The colours are `info` (the default), `success`, `warning`, `danger` and
`neutral`. On GitHub a badge shows as the code it is written as, which still
says what it means.

The [static website export](/p/docuwaves/pages/exporting-a-static-website)
and the EPUB show badges too; steps and cards appear there as the plain
lists they are written as.
