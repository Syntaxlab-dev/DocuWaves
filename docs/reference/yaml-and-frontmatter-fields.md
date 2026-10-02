---
order: 1
published: true
title: YAML and frontmatter fields
---

Every field in every file DocuWaves reads from the content repository. See [The file layout](/p/docuwaves/pages/the-file-layout) for where each file sits.

Fields marked **localizable** accept either a plain string or a mapping of language code to string, once `languages:` is configured:

```yaml
name:
  de: Erste Schritte
  en: Getting Started
```

A language missing from a mapping falls back to the default language's value.

## `content/_site.yml`

The file is optional, and so is every field in it.

| Field | Type | Default | Notes |
|---|---|---|---|
| `languages` | list of strings | *(none)* | Two-letter lowercase codes, in order; the first is the default. Maximum 12. Only editable in the file |
| `name` | string, **localizable** | `DocuWaves` | Header text and tab title |
| `tagline` | string, **localizable** | *(a generic line)* | One line under the name on the home page |
| `logo` | string | *(none)* | A filename in `content/_site/` |
| `logo_dark` | string | falls back to `logo` | Used in dark mode |
| `favicon` | string | *(the shipped icon)* | A filename in `content/_site/` |
| `accent` | string | *(the built-in accent)* | `#rgb` or `#rrggbb` only |
| `footer_text` | string, **localizable** | *(no footer)* | |
| `footer_links` | list of `{label, url}` | *(none)* | Maximum 12. `url` must start with `http://`, `https://`, `mailto:` or `/` |
| `analytics.umami_url` | string | *(none — off)* | An absolute `http(s)` URL whose path ends in `.js`. Both analytics fields or neither |
| `analytics.umami_website_id` | string | *(none — off)* | Letters, digits, `-` and `_`, 8–64 characters |

Text fields are truncated at 200 characters. See [Branding this instance](/p/docuwaves/pages/branding-this-instance) and [Analytics](/p/docuwaves/pages/analytics).

## `content/<project>/_project.yml`

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | string, **localizable** | the slug | What the project is called |
| `icon` | string | `""` | A single emoji, shown on the tile |
| `color` | string | `""` | An accent for this project |
| `image` | string | *(none)* | Cover image, relative to **this file's** directory — so `assets/cover.png`. See [Tile cover images](/p/docuwaves/pages/tile-cover-images) |
| `description` | string, **localizable** | `""` | One line on the home page tile |
| `order` | integer | `0` | Lower sorts first |
| `visibility` | string | *(public)* | `private` — and only that exact word — makes it a [private project](/p/docuwaves/pages/private-projects) |
| `review` | string | *(off)* | `required` — and only that word — [requires approval](/p/docuwaves/pages/approval-before-publishing) before anything goes live |
| `source` | mapping | *(none)* | `{repo, branch, path}`: the pages come from a code repository ([docs-as-code](/p/docuwaves/pages/docs-as-code)) and are read-only here. Written by the first sync |

The directory name is the slug, and the slug is the URL. `image` is the only field here that is type-checked and dropped when it is not a string — the others are only ever printed, while this one is handed to the filesystem resolver.

## `content/<project>/[<version>/]<category>/_category.yml`

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | string, **localizable** | the slug | |
| `icon` | string | `""` | A single emoji |
| `image` | string | *(none)* | Cover image, relative to this file's directory — one level below `assets/`, so `../assets/x.png` |
| `order` | integer | `0` | Lower sorts first |

## A page: `<page-slug>[.<lang>].md`

YAML frontmatter, then the Markdown body.

```markdown
---
title: Installation
order: 0
published: true
reviewed_by: Alex Winter
reviewed_at: "2026-09-04"
---

Install it like this.
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `title` | string | `""` | Shown above the body. A body opening with an `# H1` that repeats it has the duplicate dropped |
| `order` | integer | `0` | Lower sorts first. Belongs to the page, so it is the same in every translation |
| `published` | boolean | `false` | Omitting it means draft. See [Drafts and publishing](/p/docuwaves/pages/drafts-and-publishing) |
| `reviewed_by` | string | *(none)* | Who checked this text. Written only together with `reviewed_at`, and dropped when the body changes |
| `reviewed_at` | string | *(none)* | `YYYY-MM-DD`. Quote it — unquoted, YAML reads it back as a date object rather than a string |
| `review_status`, `review_*` | strings | *(none)* | Written by the [approval workflow](/p/docuwaves/pages/approval-before-publishing) on the text under review; removed again on approval. Not meant to be edited by hand |
| `slug` | string | *(the file name)* | Docs-as-code only: pins the page's address |
| `draft` | boolean | `false` | Docs-as-code only: `true` keeps a synced page a draft |

DocuWaves writes the first three keys always, and the review pair only when
there is one — a page nobody has reviewed carries neither key, so an
instance that never uses the feature sees no change in any of its files.
See [Review notes](/p/docuwaves/pages/review-notes).

The filename carries the language — a plain `<slug>.md` is the default language — and the slug is the part before any language code.

Reading is forgiving: an `order` that is not a number falls back to `0` rather than failing, because this file may be an arbitrary historical version being shown in the [history panel](/p/docuwaves/pages/page-history).

## `content/<project>/_versions.yml`

Present only once a project has frozen a version. Its absence *is* the unversioned shape.

```yaml
current_label: Current
default: current
versions:
  - id: v2.0
    label: "2.0"
    released: 2026-08-01
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `current_label` | string | `Current` | What the working version is called in the switcher. Truncated at 60 characters |
| `default` | string | `current` | Which version an unprefixed URL shows. A value naming a version that no longer exists falls back to `current` |
| `versions` | list | `[]` | Frozen versions, newest first. Maximum 50 |
| `versions[].id` | string | *(required)* | Directory name and URL segment. Lowercase letters, digits, dots, dashes and underscores, starting with a letter or digit, at most 40 characters |
| `versions[].label` | string | the id | What the switcher shows |
| `versions[].released` | date or string | `""` | An unquoted ISO date is a real YAML date; anything else is kept verbatim |

An entry whose `id` is unusable, reserved (`current`, `assets`, `c`, `pages`) or duplicated is dropped and logged. See [Freezing a version](/p/docuwaves/pages/freezing-a-version).

## What happens to a field you get wrong

It falls back to its default, and the bad value is logged. That applies to a missing file, an empty file, broken YAML, a field holding the wrong type, and a key DocuWaves does not know.

These files are hand-editable and arrive by pull request, so erroring the public site over a typo would be the wrong trade. The one thing that is not silent is a duplicate page slug within a project: the first file wins and the rest are listed in the admin area's content-repo status panel.
