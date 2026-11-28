# The DocuWaves content format

**Version 1.0 (draft)** · 2026-11-27

This document describes how documentation is stored as files: a tree of
plain Markdown and YAML that any tool can read and write without DocuWaves.
DocuWaves is one program that reads and writes this format. The linter in
[`tools/docuwaves-lint/`](../tools/docuwaves-lint/) is another. Both are
checked against the same [conformance cases](conformance/).

The words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as described
in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

## 1. Principles

1. **Files are the content.** Everything a reader sees comes from files in
   the content tree. A database or a search index built from them is a
   cache: deleting it loses nothing.
2. **Forgiving to read, strict to write.** These files are edited by hand and
   arrive through pull requests. A reader MUST NOT refuse a whole tree, or a
   whole project, because one file in it is wrong. A wrong value falls back
   to its default, and the reader reports a *diagnostic* (section 9). A
   writer MUST produce files that cause no diagnostics.
3. **One file, one thing.** A project, a category and each language of a
   page are separate files, so a change to one shows up as a change to one
   file in a diff.

## 2. The content tree

The content tree is the directory `content/` at the root of a repository.
All paths below are relative to it.

```
_site.yml                          site settings (optional)
_site/                             files the site settings point at
<project>/
  _project.yml                     marks the directory as a project
  _versions.yml                    only for a versioned project (section 7)
  _redirects.yml                   old page slugs (section 8)
  assets/                          images and files pages link to
  <category>/
    _category.yml                  marks the directory as a category
    <page>.md                      a page in the default language
    <page>.<lang>.md               the same page in another language
```

### 2.1 Reserved names

A name that starts with `_` is reserved, at every level. A reader MUST NOT
treat a reserved directory as a project or a category, even when it holds a
`_project.yml` or `_category.yml`. A reader MUST ignore a reserved file it
does not know, without a diagnostic. This keeps the namespace free for
later versions of this format.

`assets` is also reserved inside a project (and inside each version
directory). It is never a category.

### 2.2 What makes a project, a category, a page

- A **project** is a directory directly in `content/` that holds a file
  named `_project.yml`. A directory without one is not a project and is
  ignored.
- A **category** is a directory directly in a project's *content directory*
  (the project directory, or a version directory, section 7) that holds a
  file named `_category.yml`.
- A **page** is a regular file directly in a category whose name ends in
  `.md`. Files with other extensions, and subdirectories of a category, are
  not pages. `_pending/` (section 6.3) is reserved.

### 2.3 Slugs

The directory name of a project or a category, and the file name of a page
without its language and `.md`, is its **slug**. Slugs are part of the
public URL.

A writer MUST create slugs matching:

```
^[a-z0-9]+(-[a-z0-9]+)*$
```

A reader SHOULD accept any other name it finds and report
`slug-not-canonical`. It MUST NOT rename anything.

**Page slugs are unique per project and version, not per category.** A
page's URL does not include its category. If two categories of the same
project and version hold a page with the same slug and language, the reader
MUST keep the one in the category whose slug sorts first (byte order) and
report `duplicate-page` for the other one.

## 3. Common rules for YAML files

- Files MUST be UTF-8. Writers SHOULD NOT write a byte order mark.
  Readers MUST accept and ignore a byte order mark at the start of YAML and
  Markdown page files.
- Each YAML file holds one mapping. An empty file or an empty mapping is
  valid, and every field takes its default.
- A file that is not valid YAML, or whose top level is not a mapping, is
  treated as an empty mapping and reported as `yaml-invalid`.
- A field with a value of the wrong type takes its default and is reported
  as `field-invalid`.
- A key the reader does not know is ignored and reported as `unknown-key`.
  Readers MUST keep reading the rest of the file.
- YAML 1.1 and 1.2 parsers disagree on some plain scalars: `yes`, `no`,
  `on`, `off` and unquoted dates. Writers MUST write booleans as `true` or
  `false` and quote dates. What a reader makes of the other forms is not
  defined by this format.

### 3.1 Localizable text

Some text fields are marked *localizable*. They hold either a string, or a
mapping from language code (section 4) to string:

```yaml
name:
  en: Getting started
  de: Erste Schritte
```

Mapping keys that are not language codes, and values that are not strings
or are empty, are dropped. The field's text in a language is that
language's entry. If that entry is missing, it is the default language's
entry. If that is missing too, it is the first entry in the mapping. A
mapping with no usable entry counts as missing.

## 4. Languages

`_site.yml` MAY hold `languages:`, a list of two-letter lowercase codes. The
first one is the **default language**. A reader MUST use at most the first
12 entries and drop entries that are not strings of two letters a–z (after
lowercasing and trimming), as well as duplicates.

- With no languages configured, the site has one language without a code,
  and file names carry no language suffix.
- A page file named `<slug>.<code>.md`, where `<code>` is a configured
  language, is that page in that language. With any other suffix, the dot
  and suffix are part of the slug: `notes.io.md` is the page `notes.io` if
  `io` is not configured.
- `<slug>.md` is the page in the default language. If both `<slug>.md` and
  `<slug>.<default>.md` exist, the reader MUST use the suffixed file and
  report `duplicate-language` for the other one.
- Writers on a site with languages SHOULD always write the suffix.

## 5. Site, project and category files

### 5.1 `_site.yml`

Optional. The fields of this file that concern presentation (branding,
footer, announcement, appearance, custom CSS, analytics) are listed in
[YAML and frontmatter fields](../docs/reference/yaml-and-frontmatter-fields.md).
They do not change what content exists. For this format, the only field
that matters is `languages` (section 4).

### 5.2 `_project.yml`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | localizable text | the slug | The project's name |
| `description` | localizable text | `""` | One line about it |
| `icon` | string | `""` | One emoji, or `lucide:<name>` |
| `color` | string | `""` | An accent colour, `#rgb` or `#rrggbb` |
| `image` | string | `""` | Cover image, relative to this file's directory |
| `order` | integer | `0` | Lower sorts first |
| `visibility` | string | public | Only the exact word `private` makes the project private |
| `review` | string | off | Only the exact word `required` turns approval on |
| `review_every` | integer ≥ 0 | `0` | Days after which a page's review is due; 0 is off |
| `source` | mapping | none | Docs-as-code origin (`repo`, `branch`, `path`), written by DocuWaves |

`visibility` and `review` are compared after trimming and lowercasing. Any
other value means "public" and "off". A reader MUST NOT report a
diagnostic for them. A typo must never hide documentation.

### 5.3 `_category.yml`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | localizable text | the slug | The category's name |
| `icon` | string | `""` | As for a project |
| `image` | string | `""` | Cover image, relative to this file's directory |
| `order` | integer | `0` | Lower sorts first, among categories with the same parent |
| `parent` | string | `""` | The slug of the category this one sits inside |

**Nesting.** Categories stay side by side on disk. `parent` names another
category of the same project and version. A reader MUST treat a category
as top-level, and report `parent-invalid`, when its parent:

- does not exist, or is the category itself,
- would close a loop, or
- would put the category deeper than **4 levels** (a top-level category is
  level 1).

Categories are checked in slug order, and a parent that was dropped counts
as empty for the checks that follow. That makes the result the same on
every read.

## 6. Pages

A page file is optional YAML frontmatter between two lines of `---`,
followed by the body in Markdown. A file that does not start with `---` has
no frontmatter, and the whole file is the body.

```markdown
---
title: Installation
order: 0
published: true
---

Install it like this.
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `title` | string | the slug | The page title |
| `order` | integer | `0` | Lower sorts first. The same in every language of the page |
| `published` | boolean | `false` | `false` is a draft, which only signed-in users see |
| `reviewed_by` | string | `""` | Who last checked the text |
| `reviewed_at` | string | `""` | When, as `YYYY-MM-DD`. Writers MUST quote it |
| `review_status`, `review_*` | string | `""` | Written by the approval workflow |
| `slug` | string | — | Docs-as-code only |
| `draft` | boolean | `false` | Docs-as-code only |

### 6.1 The body

The body is [CommonMark](https://commonmark.org/) with GitHub's tables,
task lists and strikethrough. DocuWaves' additional blocks (callouts, tabs,
steps, cards, diagrams, formulas, snippets) are fenced or directive syntax
that falls back to readable text in any other Markdown renderer. Their
syntax is described in [Markdown](../docs/writing-documentation/markdown.md).
This version of the format does not standardise them.

### 6.2 Links and images

A relative link in a page is relative to the page file, as in any Markdown
renderer. So an image in the project's `assets/` is `../assets/x.png`, and
it shows in a plain Git hosting preview too. A reader MUST NOT resolve a
path outside the project's content directory.

### 6.3 Proposed changes

`<category>/_pending/<page>[.<lang>].md` holds a proposed new text of a
page that waits for approval. It has the same format as a page. A reader
that does not support approval MUST ignore it, because it is reserved
(section 2.1).

## 7. Versions

A project with a `_versions.yml` is **versioned**. Its categories and
`assets/` live one level deeper, in a directory per version:

```
<project>/
  _project.yml
  _versions.yml
  current/<category>/...           the version being edited
  v2.0/<category>/...              a frozen version
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `current_label` | string | `Current` | What the working version is called |
| `default` | string | `current` | The version an address without a version shows |
| `versions` | list of mappings | `[]` | Frozen versions, newest first, at most 50 |
| `versions[].id` | string | required | Directory name and URL segment |
| `versions[].label` | string | the id | What readers see |
| `versions[].released` | date or string | `""` | When it was released |

A version id MUST match `^[a-z0-9][a-z0-9._-]*$`, be at most 40 characters,
and not be one of `current`, `assets`, `c`, `pages`, `changes`, `feed.xml`,
`print` or `glossary`. A reader MUST drop an entry whose id breaks these
rules or repeats an earlier one, and report `version-invalid`. A `default`
that names no remaining version means `current`.

The project's versions are `current` followed by the frozen ids, in file
order. Directories of the project that are not one of them are ignored.

## 8. Redirects

`<project>/_redirects.yml` keeps old page slugs working after a rename:

```yaml
pages:
  old-slug: new-slug
```

An address with a slug that no page has is redirected to the mapped slug.
The redirect is only used when no page has that slug, so a redirect can
never hide a page. A chain of entries is followed, but it stops after 5
steps or at a slug it has already visited. If no page has the slug it
stops at, there is no redirect. A reader SHOULD report `redirect-loop` for
a chain that comes back to a slug it already visited. Keys and values are
read as text and trimmed, and entries with an empty side are dropped.

## 9. Diagnostics

A conforming reader reports what it could not take as written. Each
diagnostic has a **code**, a **path** (relative to `content/`) and a
level. An *error* means content was dropped or a value replaced. A *warning*
means the tree is readable as intended but not in canonical form.

| Code | Level | When |
|---|---|---|
| `yaml-invalid` | error | A YAML file, or a page's frontmatter, does not parse or is not a mapping |
| `field-invalid` | error | A field has the wrong type or an invalid value and took its default |
| `unknown-key` | warning | A key this version of the format does not define |
| `slug-not-canonical` | warning | A slug does not match the pattern in section 2.3 |
| `duplicate-page` | error | A page slug and language already used in another category of the same project and version |
| `duplicate-language` | warning | Both `<slug>.md` and `<slug>.<default>.md` exist |
| `parent-invalid` | error | A category's `parent` was dropped (section 5.3) |
| `version-invalid` | error | An entry in `_versions.yml` was dropped |
| `redirect-loop` | warning | Redirects that lead back to where they started |

Diagnostics never stop a read. Readers MAY add codes of their own, prefixed
with `x-`.

## 10. Conformance

A **reader** conforms when, for every case in [`conformance/`](conformance/),
the content it reads matches the case's `expected.json`, and it reports the
same set of `(code, path)` diagnostics.

A **writer** conforms when every tree it writes, read by a conforming
reader, gives no diagnostics.

The model in `expected.json` lists what a reader takes from the files. Its
shape is described in [conformance/README.md](conformance/README.md).

## 11. Changes to this format

- A new optional field or file is a **minor** version (1.1). Readers of
  1.0 report it as `unknown-key` or ignore it as reserved, and keep working.
- A change to what an existing file means is a **major** version (2.0).

This is version 1.0. It describes the format DocuWaves 2.3 reads and writes.
