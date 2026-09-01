# DocuWaves

A self-hosted documentation CMS. Content is Markdown+YAML files in a Git
repository you control — so a community can contribute the normal way (fork,
edit a `.md` file, open a pull request) — but it's edited through a real
browser UI too: the admin editor writes the file, commits, and pushes on
save, so nobody has to touch `git` directly if they don't want to.

- **Multiple projects in one instance** — one DocuWaves deployment can
  host the docs for every app/tool you maintain, each with its own set of
  categories and pages, so visitors land on one shared homepage and click
  through to exactly the project they're looking for.
- **Categories as tiles** — a project's docs are grouped into categories,
  shown as clickable tiles rather than one long sidebar to scroll through.
- **Markdown, with a live preview** — pages are written in Markdown (GFM:
  tables, checklists, fenced code blocks with syntax highlighting) and
  edited in a split editor/preview pane.
- **Content lives in Git, not a database** — every project/category/page is
  a plain file (see "Content repo structure" below). A community member can
  contribute via a normal pull request; DocuWaves picks up merged changes
  automatically (a background sync job, or a "Sync now" button in the admin
  UI). Full commit history for free, no separate backup story for content.
- **Branded per instance** — name, tagline, logo, favicon, accent colour and
  footer come from a `_site.yml` in the content repo (see "Site branding"),
  so two deployments look like two different products without either of them
  needing its own build.
- **Draft vs. published** — a page stays invisible to the public site
  until you explicitly publish it.
- **Multiple languages, optionally** — a page can exist in several
  languages (`installation.de.md` next to `installation.en.md`), with the
  language in the URL, a switcher in the header, and an honest notice on a
  page that isn't translated yet rather than a dead end (see
  "Multiple languages"). Off unless you ask for it: an instance that never
  sets `languages:` behaves exactly as it always has.
- **Full-text search** across every published page in every project.
- **Single admin account** — password login, or single sign-on via any
  standard OIDC provider (Authentik, Keycloak, Authelia, Zitadel, ...).
- **SQLite by default** (a single file, zero configuration), with
  PostgreSQL as an optional upgrade for larger installs — either way, this
  is only ever a rebuildable search/browse *index* over the content repo's
  files, never the source of truth itself. Losing it isn't losing content;
  DocuWaves rebuilds it from the files on next startup or "Sync now".

## Setup

1. Create a separate Git repository to hold your documentation content (can
   be private or public, on GitHub/GitLab/your own Forgejo/Gitea/anything —
   DocuWaves only needs a normal Git remote URL). It can start completely
   empty.
2. Clone *this* repo (DocuWaves itself) and `cd` into it.
3. `cp .env.example .env`, then set `CONTENT_REPO_URL` (and either
   `CONTENT_REPO_TOKEN` for an HTTPS remote or `CONTENT_REPO_SSH_KEY` for an
   SSH one) to point at the content repo from step 1 — see `.env.example`
   for both forms with real examples.
4. `docker compose up -d --build`
5. Open `http://<your-server>:8091` — the first thing you'll see is the
   setup screen. Pick a username and password; this becomes the one admin
   account.
6. In the admin area, add a project, add a category to it, add a page,
   write some Markdown, and hit "Published" to make it visible on the
   public site. Each of those actions is a real commit, pushed to your
   content repo immediately — check its history any time.

Running without `CONTENT_REPO_URL` set is also fine: DocuWaves starts, the
public site is just empty and the admin area shows a clear "not connected"
message instead of the editor, until you set it and restart.

## Content repo structure

This is the on-disk convention DocuWaves reads and writes (and the shape a
community contributor's pull request should follow):

```
content/
  _site.yml               <- this instance's branding (optional)
  _site/                  <- the images it points at
    logo.png
  <project-slug>/
    _project.yml
    assets/
      <image-file>
    <category-slug>/
      _category.yml
      <page-slug>.md            <- the default language
      <page-slug>.<lang>.md     <- the same page in another language
      <another-page-slug>.md
    <another-category-slug>/
      _category.yml
      ...
  <another-project-slug>/
    ...
```

Names starting with an underscore directly inside `content/` are reserved
for DocuWaves itself and are never read as a project — `_site/` can't turn
into a phantom project tile on the homepage.

`_project.yml`:

```yaml
name: My Project
icon: 🚀
color: "#5b8def"
description: A short one-line description shown on the homepage tile.
order: 0
```

`_category.yml`:

```yaml
name: Getting Started
icon: 📘
order: 0
```

A page's `.md` file — YAML frontmatter, then the Markdown body:

```markdown
---
title: Installation
order: 0
published: true
---

# Installation

Write your page content here, normal GitHub-flavored Markdown.
```

`order` (on projects, categories, and pages) controls display order —
lower first. `published: false` (or omitting the field) keeps a page out of
the public site entirely, even if it's merged to the content repo's default
branch; only DocuWaves' own "Publish" toggle (or hand-editing the file)
changes that.

Slugs (the folder/file names themselves) become part of each page's URL, so
keep them stable once published — renaming a project/category/page's name
in the admin editor changes its slug (and therefore moves the file) too.

### Multiple languages

Entirely optional, and off until you switch it on: **a content repo with no
`languages:` in `_site.yml` behaves exactly as it always has** — one
language, no URL prefix, no switcher, no per-language fields anywhere in
the admin UI, and every file stays where it is. Nothing below needs doing
to keep an existing install working.

To offer the docs in more than one language, list them in
`content/_site.yml`, in order — **the first one is the default**:

```yaml
languages: [de, en]
```

That's the whole switch. Three things follow from it:

**1. A page's language is in its filename.** `<page-slug>.<lang>.md`, with
a two-letter code:

```
content/cachepanel/erste-schritte/
  _category.yml
  installation.de.md
  installation.en.md
  erweitert.de.md        <- German only; the missing English is visible at a glance
```

The **slug is the same in all of them** (`installation`), because these are
one page in two languages, not two pages: a reader who switches language
stays on the page they were reading. A plain `<page-slug>.md` with no code
means the default language — so the existing files of a repo that only just
added `languages:` are simply read as German (in the example above), in
place. Nothing is moved or rewritten, and a page can keep that name
forever; the admin editor only spells the code out on files it creates
from now on.

A code is only recognized as a language when it's one you configured, so a
file named `release.v2.md` keeps the slug `release.v2` and doesn't become a
Venda translation of `release`.

**2. Names can be per language.** `name` and `description` in
`_project.yml`, `name` in `_category.yml`, and `name` / `tagline` /
`footer_text` in `_site.yml` each accept **either** a plain string (applies
to every language, exactly as before) **or** a mapping:

```yaml
name:
  de: Erste Schritte
  en: Getting Started
```

A language missing from the mapping falls back to the default language's
value. Both forms are valid at the same time in the same repo — translate
the two names that matter and leave the rest as plain strings.

**3. The language is in the URL**, as a path prefix:

```
/de/p/cachepanel/pages/installation
/en/p/cachepanel/pages/installation
```

An unprefixed URL (every link that was ever shared before you added a
second language) redirects to the default language, so nothing breaks.

**A missing translation is never a dead end.** If a page has no version in
the language being read, the default language's version is served —
`200`, not `404` — with an unobtrusive notice above it saying so ("This
page has not been translated yet — showing the German version"). In the
sidebar and in category listings, such a page is listed normally and marked
with a small muted language code after its title, so the language it opens
in isn't a surprise. **Search stays in one language:** searching in English
returns the English pages, plus the pages that exist *only* in the default
language — never a page and its own translation as two hits.

In the admin editor, a page gets one tab per configured language. A tab for
a language the page doesn't exist in yet opens an empty editor and saves as
`<slug>.<lang>.md` under that same slug — creating a translation, never a
new page. Only the **default language's** title steers the slug, so
renaming a translation can't move the page's URL out from under anyone.
Deleting a page deletes all of its translations; to remove just one, delete
that file in the content repo.

The reader's *interface* language (button labels) is a separate thing they
pick for themselves — but on a multi-language instance it follows whatever
content language they're reading in, for the languages the interface has
translations for.

### Images

Images live in the content repo alongside the Markdown that uses them, in
the project's own `assets/` folder, and are referenced with a **normal
relative Markdown path**:

```markdown
![Dashboard](../assets/dashboard.png)
```

One `..` because a page sits one directory deeper (`<category-slug>/`) than
`assets/`. Relative rather than a rewritten absolute URL on purpose: the
exact same `.md` file then renders its images correctly in GitHub's (or
Gitea's/Forgejo's) own file preview, and in anyone's local Markdown editor,
not just inside DocuWaves.

The admin editor's **Insert image** button uploads a file into that folder,
commits and pushes it like any other content change, and pastes the snippet
at the cursor; the same panel lists the project's existing images so one can
be re-used on another page without uploading it twice. Adding an image by
pull request works just as well — drop the file in `assets/` and reference
it the same way.

Rules DocuWaves enforces, on upload *and* when serving:

- **Allowed types:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.avif`,
  `.svg`. Anything else is refused on upload and 404s when requested.
- **Max 10 MB** per image.
- **The bytes are checked, not the filename** — an upload's real magic
  number has to match its extension, and an `.svg` has to parse as XML with
  no `<script>` element, no `on…=` event attribute and no `javascript:` URL
  in it. The content-type the browser declares is ignored entirely. SVGs are
  additionally served with a restrictive `Content-Security-Policy`, so even
  one committed straight into the repo by hand can't run script.
- **A relative path is resolved against the page's own directory and may
  never leave the page's project directory.** `../assets/x.png` and
  `./screenshots/x.png` are fine; `../../other-project/x.png`, an absolute
  path, or a symlink pointing out of the repo resolve to nothing (404).

Images aren't subject to the draft/published distinction — only pages are.
An image sitting in `assets/` is publicly readable as soon as it's in the
repo, whether or not any published page references it. Don't put anything in
there that isn't meant to be seen; the content repo itself is the boundary.

### Site branding

Every DocuWaves instance carries its own name, logo, colour and footer, and
that identity lives in the content repo too — `content/_site.yml`, with its
images in `content/_site/`. It's in the repo rather than in the database on
purpose: the database is only ever a rebuildable index (see above), so
branding kept there would disappear the moment it's reindexed or the volume
is lost. In the repo it's versioned, reviewable in a pull request, and comes
back with the same `git clone` that restores every page.

The practical consequence: **branding is per instance, automatically.** One
deployment pointed at a company's docs repo and another pointed at a tool's
own docs repo look completely different, without either needing its own
build, image or environment variable.

`_site.yml` — every field is optional, and so is the file itself:

```yaml
languages: [de, en]                   # optional; omit for a single-language site
name: SyntaxLab Docs                  # header, and the browser tab title
tagline: Documentation for every…     # one line under the name on the home page
logo: logo.png                        # a file in _site/; omit for text only
logo_dark: logo-white.png             # optional, used in dark mode
favicon: favicon.png                  # optional
accent: "#00d4d5"                     # accent colour, #rgb or #rrggbb
footer_text: © 2026 SyntaxLab         # optional
footer_links:                         # optional
  - label: Imprint
    url: https://example.com/imprint
```

What each field does:

| Field | Default when absent |
|---|---|
| `languages` | Single-language: no URL prefix, no switcher, no per-language fields (see "Multiple languages") |
| `name` | `DocuWaves`. Shown in the header and used for the tab title — a page reads `<page title> · <name>`, the home page just `<name>` |
| `tagline` | The generic "choose a project" line on the home page |
| `logo` / `logo_dark` | No image; the name renders as text. `logo_dark` falls back to `logo`, so one file works for both modes |
| `favicon` | The shipped DocuWaves icon |
| `accent` | The built-in accent (which is deliberately a different value in light and dark mode) |
| `footer_text` / `footer_links` | No footer at all |

Edit it in the admin area under **Branding** — name, tagline, a colour
picker, footer text, footer link rows and upload buttons for the three
images, with a live preview of the header. Saving writes `_site.yml`,
commits and pushes it like any other content change. Hand-editing the file
in the repo (or in a pull request) works just as well. `name`, `tagline`
and `footer_text` get one input per language once `languages:` names more
than one; `languages` itself is shown there but only editable in the file,
since it decides how every page file in the repo is named.

The images in `_site/` follow exactly the same rules as a project's images
(allowed types, 10 MB, content checked against the extension, SVGs screened
and served with a restrictive CSP, no path escaping the folder) — it's the
same code path, with `_site` in the place of a project slug.

Nothing in this file can take the site down. A missing file, an empty one,
broken YAML, a field holding the wrong type, a key DocuWaves doesn't know,
a colour that isn't a colour, a `javascript:` footer link, a logo naming a
file that isn't there — each one falls back to its default (and the bad
value is logged), rather than erroring the public site over a typo.

## Optional: PostgreSQL

If you'd rather run a real database for the search/browse index (e.g. you
already run Postgres for other services and want everything backed up the
same way — remember this holds no content of its own, only what's already
safely in the content repo):

1. In `.env`, set `DATABASE_URL=postgresql://docuwaves:changeme@postgres:5432/docuwaves`
   (change the password to match `POSTGRES_PASSWORD` below).
2. `docker compose --profile postgres up -d --build`

Every future `docker compose` command that should also (re)start Postgres
needs the same `--profile postgres` flag.

## Optional: single sign-on (OIDC)

DocuWaves speaks standard OpenID Connect, so it works with Authentik,
Keycloak, Authelia, Zitadel, or anything else that implements the spec.

In your identity provider, create an OAuth2/OpenID application with:

- **Redirect URI:** `https://<your-docuwaves-domain>/api/auth/oidc/callback`
  (exact path, only the domain changes)
- A real **signing key** configured for the provider — without one, most
  providers' JWKS endpoint returns no signing keys at all, and DocuWaves
  will refuse to trust tokens it can't verify (fails with a clear error
  rather than silently accepting an unsigned token).

Then, in DocuWaves' `.env`:

```
OIDC_ISSUER_URL=https://your-idp.example.com/application/o/docuwaves/
OIDC_CLIENT_ID=<client id from your provider>
OIDC_CLIENT_SECRET=<client secret from your provider>
OIDC_PROVIDER_NAME=authentik
```

`OIDC_ISSUER_URL` is the base URL DocuWaves fetches
`{OIDC_ISSUER_URL}/.well-known/openid-configuration` from to find the
authorization/token/JWKS endpoints itself — you don't need to look those
up individually. `OIDC_PROVIDER_NAME` only controls the login button's
label ("Sign in with authentik"); it's optional.

Restart the container (`docker compose up -d --build`) and a login button
appears on the login page alongside the password form — the password path
stays available regardless, SSO is additive, not a replacement.

**First login on a brand-new instance:** if no admin account exists yet, the
first successful SSO login creates one automatically, using your SSO
username, and skips the setup screen entirely. On an already-configured
instance, the SSO username must exactly match the existing admin account's
username, or the login is rejected — SSO authenticates *who* you are, it
never grants access on its own.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONTENT_REPO_URL` | *(empty)* | Git remote holding your Markdown content — required for the admin editor to work |
| `CONTENT_REPO_TOKEN` | *(empty)* | Push token, for an `https://` content repo URL |
| `CONTENT_REPO_SSH_KEY` | *(empty)* | Private deploy key, for a `git@`/`ssh://` content repo URL |
| `CONTENT_REPO_BRANCH` | `main` | Branch to track |
| `CONTENT_REPO_SYNC_INTERVAL_SECONDS` | `300` | How often the background job pulls + reindexes on its own |
| `CONTENT_REPO_PATH` | `/data/content-repo` | Where the local working clone lives (inside the container) |
| `DATABASE_URL` | *(empty — SQLite)* | Postgres connection string; switches the search-index backend |
| `SQLITE_PATH` | `/data/docuwaves.db` | Where the SQLite index file lives (only used without `DATABASE_URL`) |
| `OIDC_ISSUER_URL` | *(empty — SSO off)* | Your identity provider's base issuer URL |
| `OIDC_CLIENT_ID` | *(empty)* | OIDC client ID |
| `OIDC_CLIENT_SECRET` | *(empty)* | OIDC client secret |
| `OIDC_PROVIDER_NAME` | `authentik` | Label shown on the SSO login button |

## Development

```
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev   # proxies /api to localhost:8000
```

## License

MIT — see [LICENSE](LICENSE).
