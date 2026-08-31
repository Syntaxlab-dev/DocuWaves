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
- **Draft vs. published** — a page stays invisible to the public site
  until you explicitly publish it.
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
  <project-slug>/
    _project.yml
    <category-slug>/
      _category.yml
      <page-slug>.md
      <another-page-slug>.md
    <another-category-slug>/
      _category.yml
      ...
  <another-project-slug>/
    ...
```

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
