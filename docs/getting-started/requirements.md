---
order: 1
published: true
title: Requirements
---

There is not much to it. DocuWaves is one container and one directory of data. A Git repository holds your documentation — but it does not have to live anywhere but on your own disk.

## On the machine that runs it

- **Docker** with the Compose plugin (`docker compose`, not the older `docker-compose` script). Any Linux host will do; the image is built on `python:3.12-slim`.
- **A writable directory** for the `./data` volume. Everything DocuWaves stores lives there: the content repository itself, the SQLite index, the session signing secret, and the deploy key if you use one.
- **Disk** roughly equal to your documentation plus a little. Documentation is text; images dominate, and each is capped at 10 MB.

`git` and `openssh-client` are installed **inside** the image, so the host does not need them.

## A content repository — created for you

You do not have to prepare anything. Start the container with no configuration and DocuWaves runs `git init` in its data directory, then commits every save there. History, diffs, attribution and restore all work from the first day, without an account anywhere.

That local repository is a normal one. You can clone it off the volume, inspect it with `git log`, and give it a remote later.

> **The one thing this costs you:** with no remote, your content exists in exactly one place — the `./data` volume. It is not backed up by being in Git, because Git is only on that disk. Back the volume up, or add a remote. See [Backups and updates](/p/docuwaves/pages/backups-and-updates).

## A remote, if you want one

Setting `CONTENT_REPO_URL` gives that repository somewhere to push to — a second copy, and a place where other people can read and edit the files. It can be:

- on GitHub, GitLab, Gitea, Forgejo, or anything else that speaks a normal Git remote URL;
- **private or public** — private is the usual choice, since it holds unpublished drafts;
- **completely empty**. DocuWaves bootstraps a repository with no commits at all: it initialises the configured branch and pushes a first commit itself.

You can set this at the start or add it later; an instance that has been running locally pushes its existing history to the new remote. Do not point two DocuWaves instances at the same repository.

## A credential, only with a remote

DocuWaves pushes on every save, so read-only access is not enough. Pick one, matching the URL scheme:

| Remote URL | Credential | Environment variable |
|---|---|---|
| `https://…` | A token with write access to that one repository — on GitHub, a fine-grained PAT with **Contents: Read and write** | `CONTENT_REPO_TOKEN` |
| `git@…` or `ssh://…` | A deploy key with write access; paste the **private** key, `BEGIN`/`END` lines included | `CONTENT_REPO_SSH_KEY` |

Scope the credential to the content repository alone. It is the only repository DocuWaves ever touches.

## Optional

- **A reverse proxy**, if the site should answer on a domain over HTTPS. Recommended for anything public — see [Behind a reverse proxy](/p/docuwaves/pages/behind-a-reverse-proxy).
- **PostgreSQL**, if you would rather not have a SQLite file. It changes nothing about where content lives; see [PostgreSQL](/p/docuwaves/pages/postgresql).
- **An OIDC provider** for single sign-on — Authentik, Keycloak, Authelia, Zitadel, or anything else implementing the spec. See [Single sign-on](/p/docuwaves/pages/single-sign-on).

## What you do not need

- **No GitHub account, and no Git host at all**, unless you want the second copy a remote gives you.
- **No AI provider account.** The [assistant endpoint](/p/docuwaves/pages/the-mcp-endpoint) never calls a language model itself.
- **No CDN and no outbound internet at runtime.** Every asset, including the diagram renderer, is bundled with the application. An instance on an isolated network draws its diagrams exactly like one on the open internet — and with no remote configured, it never needs to reach the network at all.
- **No separate database server**, unless you want one.

Next: [Installing with Docker](/p/docuwaves/pages/installing-with-docker).
