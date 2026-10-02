---
order: 2
published: false
title: Installing with the installer
---

On a fresh Linux server, one command sets up a running instance with HTTPS:

```bash
curl -fsSL https://get.docuwaves.app | sudo sh
```

It asks up to two questions: the domain to use, and optionally a Git remote for the content. When it finishes, it prints the address and a setup code. Open the address, enter the code, and pick your administrator's username and password. Continue with [The first run](/p/docuwaves/pages/the-first-run).

Prefer to read a script before you run it as root? Download it first:

```bash
curl -fsSLO https://github.com/Syntaxlab-dev/DocuWaves/releases/latest/download/install.sh
curl -fsSLO https://github.com/Syntaxlab-dev/DocuWaves/releases/latest/download/install.sh.sha256
sha256sum -c install.sh.sha256
less install.sh
sudo sh install.sh
```

## What you need

- **A Linux server**, amd64 or arm64, that you have root on. Tested on Debian 12 and 13, Ubuntu 22.04 and 24.04, Rocky Linux 9 and AlmaLinux 9. Other distributions work if Docker runs on them; the installer says so and carries on.
- **For HTTPS, a domain** whose DNS record already points at the server, and **ports 80 and 443** open to the internet. Let's Encrypt needs both to issue the certificate. If they are not ready yet, install without a domain and add it later.
- **Docker** with the Compose plugin. If it is missing, the installer offers to install it from Docker's official repository (Debian, Ubuntu, Rocky, Alma, RHEL, Fedora). On anything else, install Docker yourself first.

## What it sets up

Everything lives in one directory, `/opt/docuwaves`:

| Path | What it is |
|---|---|
| `compose.yml` | The containers: DocuWaves, and Caddy in front of it |
| `.env` | Every setting, including secrets. Readable by root only |
| `Caddyfile` | The HTTPS proxy's configuration |
| `data/` | Your documentation (the content repository), the database and the session secret |
| `backups/` | Daily backups; the newest seven are kept |
| `caddy/` | Caddy's certificates |

Outside of it:

- the `docuwaves` command, in `/usr/local/bin`. See [The docuwaves command](/p/docuwaves/pages/the-docuwaves-command);
- a systemd timer that runs `docuwaves backup` every night around 03:30.

DocuWaves itself is not reachable from outside. Only Caddy publishes ports (80 and 443), and it gets and renews the certificate on its own.

## The setup code

Between the installation and your first visit, anyone who finds the address could create the administrator account. The installer prevents that with a random **setup code**. The first-run screen asks for it, and without it no account is created.

The code is printed at the end of the installation. It is also stored as `SETUP_TOKEN` in `/opt/docuwaves/.env`. Once the first account exists it is not used again; `docuwaves status` says when it can be removed.

## Options

For scripts, or to skip the questions:

```bash
curl -fsSL https://get.docuwaves.app | sudo sh -s -- --domain docs.example.com --yes
```

| Option | Effect |
|---|---|
| `--domain NAME` | Serve on `NAME`, with HTTPS |
| `--no-domain` | Plain HTTP on port 80 for now. Add a domain later with `docuwaves domain NAME` |
| `--no-proxy` | No Caddy. DocuWaves listens on `127.0.0.1:8091` for your own reverse proxy. See [Behind a reverse proxy](/p/docuwaves/pages/behind-a-reverse-proxy) |
| `--listen ADDR:PORT` | With `--no-proxy`: listen somewhere else, e.g. `0.0.0.0:8091` |
| `--repo-url URL` | A Git remote for the content. For `https://`, the token is asked for, hidden, or read from `DOCUWAVES_REPO_TOKEN` |
| `--repo-ssh-key FILE` | The private deploy key for a `git@…` or `ssh://` remote |
| `--channel NAME` | Which images updates follow: `stable` (default), `latest`, or a version such as `1.2` |
| `--dir PATH` | Install somewhere other than `/opt/docuwaves` |
| `--no-backup-timer` | No nightly backup |
| `--yes` | Ask nothing. Anything not given is left at its default: no domain, no remote |

The token and the key are written to `.env` and nowhere else. They are never printed.

## Already a web server on the machine?

If ports 80 or 443 are taken, the installer stops. You then have two options: stop the other server, or install with `--no-proxy` and add DocuWaves to the server that is already there. It is reachable on `127.0.0.1:8091`. Set `PUBLIC_BASE_URL` in `.env` to the address readers will use.

## Running it again

The installer never touches an existing installation. On a server that already has one, it stops and points you to `docuwaves update`. To start from scratch, run `docuwaves uninstall --purge` first. That deletes your data, backups included.

## Without the installer

The installer only writes a Compose file and starts it. If you would rather do that yourself, see [Installing with Docker](/p/docuwaves/pages/installing-with-docker). Both kinds of installation run the same image.
