---
order: 0
published: true
title: Environment variables
---

Everything DocuWaves reads from the environment. All of them are optional; the only one you will normally set is `CONTENT_REPO_URL` and its credential.

One contract runs through the whole list: **blank means the default, and for a feature it means off.** No variable has to be set to keep something working.

## Content repository

| Variable | Default | Purpose |
|---|---|---|
| `CONTENT_REPO_URL` | *(empty — feature off)* | The Git remote holding your Markdown content. Blank is allowed: the application starts, the public site is empty, and the admin area shows **No content repo connected** instead of an editor |
| `CONTENT_REPO_TOKEN` | *(empty)* | Push token, for an `https://` content repo URL. Spliced into the remote URL at push time and never logged |
| `CONTENT_REPO_SSH_KEY` | *(empty)* | Private deploy key, for a `git@` or `ssh://` URL. Written to `/data/content_repo_ssh_key` with `0600` permissions and used through `GIT_SSH_COMMAND` |
| `CONTENT_REPO_BRANCH` | `main` | The branch to track |
| `CONTENT_REPO_PATH` | `/data/content-repo` | Where the working clone lives inside the container |
| `CONTENT_REPO_SYNC_INTERVAL_SECONDS` | `300` | How often the background job pulls and reindexes. There is also a **Sync now** button |

Set exactly one of `CONTENT_REPO_TOKEN` and `CONTENT_REPO_SSH_KEY`, matching the URL's scheme. Which mechanism is used is decided by the URL, not by which variable you filled in.

## Database

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(empty — SQLite)* | PostgreSQL connection string. Filling it in switches every store to Postgres — see [PostgreSQL](/p/docuwaves/pages/postgresql) |
| `SQLITE_PATH` | `/data/docuwaves.db` | Where the SQLite index file lives. Unused when `DATABASE_URL` is set |

## Addresses

| Variable | Default | Purpose |
|---|---|---|
| `PUBLIC_BASE_URL` | *(empty — auto-detected)* | The address readers use, e.g. `https://docs.example.com`. An **override** for what the application works out from `X-Forwarded-Proto` / `X-Forwarded-Host` and the `Host` header |

It must be an absolute `http://` or `https://` URL. A trailing slash is stripped, and anything that is not an absolute URL — a bare hostname, say — is **ignored** in favour of the auto-detected address, because a canonical tag pointing at `docs.example.com/p/x` is one no crawler can fetch. See [Behind a reverse proxy](/p/docuwaves/pages/behind-a-reverse-proxy).

## Single sign-on

| Variable | Default | Purpose |
|---|---|---|
| `OIDC_ISSUER_URL` | *(empty — SSO off)* | Your identity provider's base issuer URL. A trailing slash is stripped. Discovery is fetched from `{issuer}/.well-known/openid-configuration` |
| `OIDC_CLIENT_ID` | *(empty)* | OIDC client id |
| `OIDC_CLIENT_SECRET` | *(empty)* | OIDC client secret |
| `OIDC_PROVIDER_NAME` | `authentik` | The label on the login button — "Sign in with authentik". Cosmetic only |

See [Single sign-on](/p/docuwaves/pages/single-sign-on).

## The documentation chat

| Variable | Default | Purpose |
|---|---|---|
| `CHAT_API_BASE` | *(empty — chat off)* | Base URL of an **OpenAI-compatible** endpoint, i.e. one that answers `POST {base}/chat/completions`. A local Ollama is `http://host:11434/v1` |
| `CHAT_MODEL` | *(empty)* | The model name to ask for, e.g. `llama3.1:8b` |
| `CHAT_MAX_CONCURRENT` | `4` | How many chat questions may wait on the model at once; more get "busy, try again" |
| `CHAT_API_KEY` | *(empty)* | Sent as `Authorization: Bearer`. A local server usually ignores it, but it must be non-empty for the feature to count as configured |

All three or none: half a configuration would be a chat box that fails on
every question, so the feature stays off until the third is filled in. An
instance that sets none of them makes no request to any model, ever. See
[The documentation chat](/p/docuwaves/pages/the-documentation-chat).

## Webhooks

| Variable | Default | Purpose |
|---|---|---|
| `WEBHOOK_URLS` | *(empty — off)* | Discord, Slack or JSON endpoints to notify, comma-separated |
| `WEBHOOK_EVENTS` | `published` | Which of `published`, `updated`, `unpublished`, `review_requested`, `review_decided` to send |
| `WEBHOOK_SECRET` | *(empty)* | Signs JSON deliveries with HMAC-SHA256 |

See [Webhooks](/p/docuwaves/pages/webhooks).

## Search

| Variable | Default | Purpose |
|---|---|---|
| `SEARCH_GAPS` | `on` | The anonymous tally of searches that found nothing, under **Insights**. `off` writes nothing. See [Reader feedback](/p/docuwaves/pages/reader-feedback-and-link-checking#what-readers-searched-for-and-did-not-find) |

## Behind several proxies

| Variable | Default | Purpose |
|---|---|---|
| `CLIENT_IP_HEADER` | *(empty)* | Which header carries the reader's real address when there is **more than one** proxy in front of DocuWaves (e.g. `CF-Connecting-IP` behind Cloudflare and nginx). Feeds the rate limits on sign-in, the chat, page feedback and the search tally. Behind a single reverse proxy leave it empty |

## Sessions

| Variable | Default | Purpose |
|---|---|---|
| `SESSION_SECRET_PATH` | `/data/.session_secret` | Where the session cookie signing key is stored |
| `SESSION_COOKIE_SECURE` | *(on when `PUBLIC_BASE_URL` is https)* | Send the admin session cookie over HTTPS only. Set `true` behind an HTTPS proxy if the address is auto-detected |

The key is generated on first run and written with `0600` permissions. It lives in a file rather than in an environment variable so it never ends up in a `docker-compose.yml` or `.env` that gets shared or committed — and it is persisted rather than regenerated so a container restart does not log every browser out.

This one is real but is **not** listed in `.env.example`. You will not normally need it; it exists so the path can be moved if `/data` is laid out differently.

## Not read by DocuWaves

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | `changeme` | Consumed by `docker-compose.yml` to configure the optional Postgres container. The application never reads it — it reads the password out of `DATABASE_URL` |

If you use Postgres, the two have to agree.
