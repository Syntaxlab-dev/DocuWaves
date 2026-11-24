---
order: 10
published: true
title: Rootless Podman
---

DocuWaves runs under **rootless Podman** as well as under Docker: same image, same settings, no root on the host. Every change to the image is checked by CI against rootless Podman, which builds it, runs it as an ordinary user with a data directory from the host, and checks that the data survives a new container.

Everything on [Installing with Docker](/p/docuwaves/pages/installing-with-docker) applies. This page is about what is different.

## Run it

As the user who should own the instance, not as root:

```bash
mkdir -p ~/docuwaves/data
podman run -d --name docuwaves \
  -p 127.0.0.1:8091:8000 \
  -v ~/docuwaves/data:/data:Z \
  --env-file ~/docuwaves/.env \
  ghcr.io/syntaxlab-dev/docuwaves:stable
```

Three details matter:

- **`-v …:/data` is not optional.** The content repository, the database and the session secret live in `/data`. Without the mount the container starts anyway, with an empty database in its own throwaway layer, and asks for the first-run setup as if the instance were new. Everything done there is gone with the next container. If an instance you know suddenly shows the setup screen, check this first.
- **`:Z`** relabels the directory for SELinux (Fedora, RHEL, Rocky, AlmaLinux). Without it the container cannot write there and the logs fill with `Permission denied`. On a system without SELinux it does nothing, so leave it in.
- **Port 8000 inside, any port outside.** DocuWaves listens on **8000** in the container. A rootless user cannot bind ports below 1024, so publish a high port on `127.0.0.1` and let the [reverse proxy](/p/docuwaves/pages/behind-a-reverse-proxy) in front of it serve 443.

The app runs as root *inside* the container, which under rootless Podman is your own user on the host: the files in `~/docuwaves/data` belong to you, and you can back them up, read them and `git log` them without `sudo`.

## Start it with the system: Quadlet

On Podman 4.4 or newer, a Quadlet file turns the container into a systemd service. Save it as `~/.config/containers/systemd/docuwaves.container`:

```ini
[Unit]
Description=DocuWaves

[Container]
Image=ghcr.io/syntaxlab-dev/docuwaves:stable
ContainerName=docuwaves
PublishPort=127.0.0.1:8091:8000
Volume=%h/docuwaves/data:/data:Z
EnvironmentFile=%h/docuwaves/.env
AutoUpdate=registry

[Service]
Restart=always

[Install]
WantedBy=default.target
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user start docuwaves
loginctl enable-linger "$USER"   # keep it running when you are logged out
```

`enable-linger` is the step people miss: without it, a user's services stop when their last session ends, which on a server is right after you log out.

## Updates

`AutoUpdate=registry` lets Podman do what `docuwaves update` does on a Docker installation. Check, then apply:

```bash
podman auto-update --dry-run
podman auto-update
```

It pulls the newer image for the tag, restarts the service, and rolls back if the new container does not start. To run it on a schedule, enable `systemctl --user enable --now podman-auto-update.timer`. A backup first is still yours to make: see [Backups and updates](/p/docuwaves/pages/backups-and-updates).

## Compose

`podman compose` (or `podman-compose`) reads the shipped `docker-compose.yml` unchanged. On an SELinux system, add `:Z` to its volume line: `./data:/data:Z`.

## What does not apply

[The installer](/p/docuwaves/pages/installing-with-the-installer) and the `docuwaves` command set up Docker, Caddy and a backup timer as root. On a rootless Podman host, use the pieces above instead, and your own reverse proxy.

## Settings in a hosting panel

If a hosting panel creates the container for you, check three things after every change you save there, because panels rebuild the container from their own form:

1. The container port is **8000**.
2. A host directory is mounted at **`/data`**.
3. The environment variables are all still there, and no value starts or ends with a space.
