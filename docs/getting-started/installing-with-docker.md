---
order: 2
published: true
title: Installing with Docker
---

Three commands. A fourth step only if you want the content pushed somewhere.

## 1. Get DocuWaves

```bash
git clone https://github.com/Syntaxlab-dev/DocuWaves.git
cd DocuWaves
cp .env.example .env
```

## 2. Start it

```bash
docker compose up -d --build
```

Every line in the shipped `.env.example` is commented out, because every setting has a working default. Started this way, DocuWaves creates its own Git repository inside the data volume and commits every save to it — no account, no token, no remote.

The shipped `docker-compose.yml` builds the image from the checkout. If you would rather not build, a published image is available at `ghcr.io/syntaxlab-dev/docuwaves`, for **amd64 and arm64** (a Raspberry Pi 4 or 5, or an ARM cloud server, works too). Point the service at it with `image:` instead of `build:`. Its tags:

| Tag | What it is |
|---|---|
| `stable` | The newest release. This is the tag to run. |
| `1.2.3`, `1.2` | A specific release, or the newest patch of one |
| `latest` | The current state of the default branch, between releases |
| a short commit hash | That exact build |

Every release image, `stable` included, is rebuilt weekly with the latest fixes from its Debian base, and keeps the same tags. Pulling `stable` again picks those fixes up.

Two things in that compose file matter and are easy to lose if you write your own:

- **`ports: "8091:8000"`.** DocuWaves listens on **8000** inside the container. 8091 is just the host side; change that half freely.
- **`volumes: ./data:/data`.** This is where the content repository, the SQLite index and the session secret live. **With no remote configured, this volume is the only copy of your documentation** — treat it as the thing to back up. See [Backups and updates](/p/docuwaves/pages/backups-and-updates).

The image declares a health check against `/health`, which confirms the database is reachable. `docker compose ps` will show it.

## 3. Open it

```
http://<your-server>:8091
```

You should land on the first-run setup screen. If you do, continue with [The first run](/p/docuwaves/pages/the-first-run).

## 4. Optional: push to a Git host

A remote gives you a second copy of the content and a place where other people can read and edit the files. You can do this now or years later — an instance that has been running locally pushes its existing history when a remote is added.

Make an empty repository on GitHub, GitLab, Gitea or anything else that speaks a normal Git remote URL, and get a credential for it — see [Requirements](/p/docuwaves/pages/requirements). Do not add a README, a `.gitignore` or a licence.

Then edit `.env`. For an HTTPS remote:

```bash
CONTENT_REPO_URL=https://github.com/your-org/your-docs-content.git
CONTENT_REPO_TOKEN=github_pat_...
CONTENT_REPO_BRANCH=main
```

For an SSH remote instead, drop the token and give the private key. It is a multi-line value, so quote it:

```bash
CONTENT_REPO_URL=git@github.com:your-org/your-docs-content.git
CONTENT_REPO_SSH_KEY="-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAA...
-----END OPENSSH PRIVATE KEY-----"
```

Set exactly one of the two, matching the URL's scheme. DocuWaves picks which mechanism to use from the URL itself: a `https://` URL gets the token spliced into the remote, a `git@`/`ssh://` URL gets the key written to `/data/content_repo_ssh_key` with `0600` permissions and used through `GIT_SSH_COMMAND`.

No quotes around ordinary values, and no spaces around the `=`. Every other variable is optional; the full list is in [Environment variables](/p/docuwaves/pages/environment-variables).

Recreate the container to pick the change up:

```bash
docker compose up -d
```

Do not point two DocuWaves instances at the same repository.

## Changing settings later

`.env` is read when the container is **created**, not when it is restarted. After editing it:

```bash
docker compose up -d
```

`docker compose restart` leaves the old environment in place, and the symptom is a setting that stubbornly appears to have no effect.
