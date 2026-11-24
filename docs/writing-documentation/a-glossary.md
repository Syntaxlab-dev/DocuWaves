---
order: 16
published: true
title: A glossary
---

Define the terms your documentation uses once, and every page explains them
where they appear: the first use of a term on a page gets a dotted underline,
and its definition shows up in a small bubble on hover, on tap, or when the
term is reached with Tab. All terms are also listed on a page of their own,
linked as **Glossary** on the project's page.

## Writing it

In the admin area, under **Snippets, variables & glossary**, one term per
line:

```yaml
SLA: The availability we promise, as a percentage per month.
Deployment: Shipping a new release to the servers.
API key:
  de: Ein geheimer Schlüssel für die Programmierschnittstelle.
  en: A secret key for the programming interface.
```

A definition is plain text, at most 600 characters — or one per language,
the same shape a project's name takes. A language without its own entry gets
the default language's.

It is the file `_glossary.yml` in the content repository, so a
[docs-as-code](/p/docuwaves/pages/docs-as-code) project can write it by hand:

- in the project's directory, for that project — once the project has
  [versions](/p/docuwaves/pages/freezing-a-version), in the version's
  directory, so a frozen release keeps the definitions it shipped with;
- in `content/`, for every project. A project's own entry wins when both
  define the same term.

## Which words are marked

- Only the **first** use on a page. Twenty underlined words in one paragraph
  would be noise.
- A term with a lowercase letter matches **in any case**: `Deployment` also
  marks "deployment". A term written in **capitals** only matches in
  capitals, so `SLA` never marks the "sla" inside an address.
- Whole words only: `Deployment` does not mark "Redeployments".
- Never inside links, code, or headings.
- With overlapping terms, the longer one wins: "API key" before "API".

Printed pages and PDFs show the text without the underline; the glossary page
prints as a list.
