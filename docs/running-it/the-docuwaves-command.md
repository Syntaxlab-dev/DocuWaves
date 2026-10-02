---
order: 7
published: false
title: The docuwaves command
---

An instance set up with the [installer](/p/docuwaves/pages/installing-with-the-installer) is run with one command, `docuwaves`. Run it as root (`sudo docuwaves …`).

```
docuwaves status                  what is running, which version, where
docuwaves update                  back up, update, roll back if needed
docuwaves backup                  write a backup now
docuwaves restore <archive>       put a backup back
docuwaves reset-password <user>   set an account's password
docuwaves users                   list the accounts
docuwaves domain <name>           switch to a domain with HTTPS
docuwaves channel [name]          which images updates follow
docuwaves logs                    follow the logs
docuwaves uninstall               remove it
```

The command comes from the image. Every successful `docuwaves update` replaces it with the version that matches the update.

## status

Shows the address, the image and its version, whether the container is healthy, how much space the data takes, and the newest backup. Before the first account exists, it also reminds you to finish the setup.

## update

1. **Backs up** first, exactly like `docuwaves backup`. If the backup fails, nothing else happens.
2. **Pulls** the newest image of your channel. If it is the one already running, it says so and stops.
3. **Restarts** with the new image and waits for the health check to pass, for up to three minutes.
4. **Rolls back** if the health check never passes. The previous image is started again, and the update counts as not applied. The output shows the new version's last log lines, so you can see why.

Run it whenever you like. A good rhythm is once a week, because release images are rebuilt weekly with the latest Debian security fixes (see [Backups and updates](/p/docuwaves/pages/backups-and-updates#about-the-image-and-its-rebuilds)).

## channel

Which image `update` pulls:

| Channel | What you get |
|---|---|
| `stable` | The newest release. The default |
| `1.2` | The newest patch of 1.2: fixes, but no new features |
| `1.2.3` | Exactly that release, forever. Pinned |
| `latest` | The current development state. For trying things out |

```bash
sudo docuwaves channel          # show the current one
sudo docuwaves channel 1.2      # change it
sudo docuwaves update           # and switch now
```

## backup

Writes `/opt/docuwaves/backups/docuwaves-<date>-<time>.tar.gz`, readable by root only, and keeps the newest seven. A systemd timer runs it every night around 03:30. Set `DOCUWAVES_BACKUP_KEEP` in `/etc/default/docuwaves` to keep a different number.

The archive contains:

| Entry | What it is |
|---|---|
| `data/` | The data directory: the content repository, the session secret, the deploy key if you use one |
| `database.sqlite` | The database, copied consistently while the instance kept running (accounts, API tokens, reader votes, …) |
| `content.bundle` | The content repository's whole history as one Git bundle. You can clone from it with `git clone content.bundle`, without DocuWaves |
| `.env`, `compose.yml`, `Caddyfile` | The configuration |
| `BACKUP-INFO` | When the archive was made, and from which version |

> [!WARNING]
> A backup contains `.env`, and with it every secret: the push token or deploy key, the OIDC client secret, the chat API key. Treat the archives like `.env` itself. Copy them off the server, but only to somewhere private.

Backups that stay on the same server do not survive the server. Copy `/opt/docuwaves/backups` somewhere else regularly, for example with your provider's backup or with `rsync` from another machine.

With PostgreSQL in the same Compose file (the `postgres` service), the archive contains `postgres.sql`, made with `pg_dump`, instead of `database.sqlite`. A PostgreSQL server elsewhere has to be backed up there; the command says so.

## restore

```bash
sudo docuwaves restore /opt/docuwaves/backups/docuwaves-20261003-033012.tar.gz
```

It asks before doing anything. Then it stops DocuWaves and moves the current data aside to `data.before-restore-<date>`; nothing is deleted. It unpacks the backup in its place, puts the database back, and starts again. Once the restored instance looks right, delete the folder that was set aside.

`.env` is **not** overwritten. If the one in the archive differs, `restore` tells you, so you can compare the two.

To move an instance to another server: install there, then copy the archive across and restore it.

## reset-password

```bash
sudo docuwaves reset-password alex
```

Asks for the new password twice, hidden. It must be at least eight characters. Every session of that account is signed out. This is the way back in if you have forgotten the administrator's password. `docuwaves users` lists the accounts.

From a script, pipe the password in on one line instead. It is never passed as an argument, where it would end up in the shell history.

## domain

```bash
sudo docuwaves domain docs.example.com
```

Serves the instance on that domain with an HTTPS certificate from Let's Encrypt, which Caddy fetches on the first visit and renews by itself. The domain must point at the server, and ports 80 and 443 must be open. This is also how you change to a different domain later. `docuwaves domain --none` goes back to plain HTTP on port 80.

On an installation made with `--no-proxy`, there is no Caddy to configure. Change the domain in your own proxy, and `PUBLIC_BASE_URL` in `.env`.

## logs

```bash
sudo docuwaves logs           # DocuWaves
sudo docuwaves logs caddy     # the proxy, e.g. for certificate problems
```

## uninstall

```bash
sudo docuwaves uninstall            # stop it; keep /opt/docuwaves
sudo docuwaves uninstall --purge    # and delete /opt/docuwaves, backups included
```

`--purge` asks you to type `delete` first. Docker itself stays installed.

## Changing settings

All settings are in `/opt/docuwaves/.env`; see [Environment variables](/p/docuwaves/pages/environment-variables). After editing it:

```bash
cd /opt/docuwaves && sudo docker compose up -d
```

A plain restart keeps the old values.
