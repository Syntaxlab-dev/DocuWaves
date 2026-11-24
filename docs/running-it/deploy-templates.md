---
order: 11
published: true
title: Deploy templates
---

Ready-made setups for platforms that run containers for you. They all start the same image with the same rules, so every other page of these docs still applies: DocuWaves listens on **8000**, everything it stores is in **`/data`**, and the [environment variables](/p/docuwaves/pages/environment-variables) are the settings.

The files live in [`deploy/`](https://github.com/Syntaxlab-dev/DocuWaves/tree/main/deploy) in the repository, and CI checks that each still parses and renders.

## Kubernetes (Helm)

```bash
git clone https://github.com/Syntaxlab-dev/DocuWaves.git
helm install docs DocuWaves/deploy/helm/docuwaves \
  --set ingress.enabled=true --set ingress.host=docs.example.com \
  --set env.PUBLIC_BASE_URL=https://docs.example.com
```

Secrets such as `CONTENT_REPO_TOKEN` or `SMTP_PASSWORD` go into a Secret of your own, named with `--set existingSecret=…`; each of its keys becomes an environment variable. TLS comes from your ingress controller, for example with cert-manager and `ingress.tls.enabled=true`.

The chart runs **one replica** with the Recreate strategy and a ReadWriteOnce volume, on purpose: one Git working copy and one SQLite index, written by one process. For more availability use [PostgreSQL](/p/docuwaves/pages/postgresql) and a Git remote, so a lost pod or volume loses nothing. The volume is kept when the release is uninstalled.

## Coolify

Add a **Docker Compose** resource and paste [`deploy/coolify/docker-compose.yml`](https://github.com/Syntaxlab-dev/DocuWaves/blob/main/deploy/coolify/docker-compose.yml). Assign a domain to the `docuwaves` service. Coolify routes it to port 8000, issues the certificate, and passes the address on as `PUBLIC_BASE_URL`. Further settings go into the resource's environment variables.

## Unraid

Copy [`deploy/unraid/docuwaves.xml`](https://github.com/Syntaxlab-dev/DocuWaves/blob/main/deploy/unraid/docuwaves.xml) to `/boot/config/plugins/dockerMan/templates-user/` on the server. Then **Docker → Add Container** and pick *DocuWaves* as the template. The data goes to `/mnt/user/appdata/docuwaves`, the web UI to port 8091.

## Proxmox (LXC)

Create a **Debian 13** container with *nesting* enabled (Options → Features), which Docker needs inside an LXC, and at least 1 GB of RAM. Then, inside it and as root, run [the installer](/p/docuwaves/pages/installing-with-the-installer):

```bash
curl -fsSL https://get.docuwaves.app | sh
```

That gives you Docker, HTTPS, nightly backups and the `docuwaves` command, as on any other server. Back up the container with Proxmox's own backup as well.

## Rootless Podman

See [Rootless Podman](/p/docuwaves/pages/rootless-podman), with a Quadlet unit for systemd.

## Whichever you use

1. Open the address and create the administrator account, as in [The first run](/p/docuwaves/pages/the-first-run).
2. Make sure `/data` survives a new container. If an instance you know asks for the first-run setup again, the volume is missing.
3. Without a Git remote, `/data` is the only copy of your documentation. See [Backups and updates](/p/docuwaves/pages/backups-and-updates).
