# DocuWaves

A self-hosted documentation CMS. Unlike a static-site generator (VitePress,
Docusaurus, MkDocs, ...), content lives in a real database and is written
and organized entirely in the browser — no Markdown files to commit, no
build step to run when you just want to fix a typo.

- **Multiple projects in one instance** — one DocuWaves deployment can
  host the docs for every app/tool you maintain, each with its own set of
  categories and pages, so visitors land on one shared homepage and click
  through to exactly the project they're looking for.
- **Categories as tiles** — a project's docs are grouped into categories,
  shown as clickable tiles rather than one long sidebar to scroll through.
- **Markdown, with a live preview** — pages are written in Markdown (GFM:
  tables, checklists, fenced code blocks with syntax highlighting) and
  edited in a split editor/preview pane.
- **Draft vs. published** — a page stays invisible to the public site
  until you explicitly publish it.
- **Full-text search** across every published page in every project.
- **Single admin account** — password login, or single sign-on via any
  standard OIDC provider (Authentik, Keycloak, Authelia, Zitadel, ...).
- **SQLite by default** (a single file, zero configuration), with
  PostgreSQL as an optional upgrade for larger installs.

## Setup

1. Clone this repo and `cd` into it.
2. `cp .env.example .env` (only needed if you want OIDC/SSO or PostgreSQL —
   the defaults work with an empty `.env`).
3. `docker compose up -d --build`
4. Open `http://<your-server>:8091` — the first thing you'll see is the
   setup screen. Pick a username and password; this becomes the one admin
   account.
5. In the admin area, add a project, add a category to it, add a page,
   write some Markdown, and hit "Published" to make it visible on the
   public site.

That's it — no separate database to install (SQLite lives in `./data`,
which is the one directory you should back up).

## Optional: PostgreSQL

If you'd rather run a real database (e.g. you already run Postgres for
other services and want everything backed up the same way):

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
| `DATABASE_URL` | *(empty — SQLite)* | Postgres connection string; switches storage backend |
| `SQLITE_PATH` | `/data/docuwaves.db` | Where the SQLite file lives (only used without `DATABASE_URL`) |
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
