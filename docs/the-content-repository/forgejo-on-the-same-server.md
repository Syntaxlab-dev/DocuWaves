---
order: 4
published: false
title: Forgejo on the same server
---

DocuWaves keeps your documentation in a Git repository. Without a remote, that repository has only one copy, on the server. A Git host gives it a second copy, a place to browse the files, and a way for others to send changes as pull requests.

If you would rather not use GitHub or GitLab, [Forgejo](https://forgejo.org) is a small, free Git host you can run yourself. This page puts it on the same server as an instance set up by the [installer](/p/docuwaves/pages/installing-with-the-installer). It shares that instance's Caddy, so it gets HTTPS too.

What you end up with:

- `docs.example.com`: DocuWaves, as before;
- `git.example.com`: Forgejo, where the content repository lives;
- DocuWaves pushes every save to Forgejo over the server's internal Docker network, which never leaves the machine.

> [!NOTE]
> A second copy **on the same server** protects against mistakes, not against losing the server. Keep copying the backups somewhere else (see [The docuwaves command](/p/docuwaves/pages/the-docuwaves-command#backup)).

## 1. A DNS record

Point `git.example.com` at the server, the same way as the documentation's domain.

## 2. Start Forgejo

Create `/opt/forgejo/compose.yml`:

```yaml
name: forgejo

services:
  forgejo:
    image: codeberg.org/forgejo/forgejo:16
    restart: unless-stopped
    environment:
      USER_UID: "1000"
      USER_GID: "1000"
      FORGEJO__server__ROOT_URL: https://git.example.com/
      FORGEJO__server__DISABLE_SSH: "true"
      FORGEJO__service__DISABLE_REGISTRATION: "true"
    volumes:
      - ./data:/data
    networks:
      - docuwaves

# DocuWaves' network, so that its Caddy can reach Forgejo, and DocuWaves
# can push to it, by the name "forgejo".
networks:
  docuwaves:
    name: docuwaves_default
    external: true
```

Then start it:

```bash
cd /opt/forgejo && sudo docker compose up -d
```

`DISABLE_REGISTRATION` keeps strangers from creating accounts. You add accounts yourself, as Forgejo's administrator. SSH is off because nothing here needs it: DocuWaves pushes over HTTP, and so can you.

## 3. Let Caddy serve it

Add a second block to `/opt/docuwaves/Caddyfile`, below the one that is there:

```
git.example.com {
	reverse_proxy forgejo:3000
}
```

Reload Caddy:

```bash
cd /opt/docuwaves && sudo docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Caddy fetches the certificate for `git.example.com` on the first visit. `docuwaves update` never touches the Caddyfile, so the block stays.

## 4. Set up Forgejo

Open `https://git.example.com`. The first visit shows Forgejo's installation page:

- **Database type:** SQLite3 is enough.
- **Server domain** and **Forgejo base URL:** `git.example.com` and `https://git.example.com/`.
- Under **Administrator account settings**, create your administrator.

Then, signed in:

1. **Create an empty repository**, for example `docs-content`. Do not add a README, a `.gitignore` or a licence.
2. **Create a token:** *Settings → Applications → Generate new token*. Give it the permission **repository: Read and write**, and copy it.

## 5. Point DocuWaves at it

Add three lines to `/opt/docuwaves/.env`:

```bash
CONTENT_REPO_URL=http://forgejo:3000/your-name/docs-content.git
CONTENT_REPO_TOKEN=the-token-from-step-4
CONTENT_REPO_BRANCH=main
```

Use `http://forgejo:3000`, not the public address. It is the internal network, where nothing passes over the internet, so plain HTTP is fine there.

Apply it:

```bash
cd /opt/docuwaves && sudo docker compose up -d
```

On that start, DocuWaves pushes its whole history to the empty repository. From then on, every save is a commit in Forgejo. You can watch them under *Commits*. The admin area's status bar now shows **Content repo connected**.

## Backups

`docuwaves backup` covers DocuWaves, not Forgejo. Forgejo has its own backup command:

```bash
cd /opt/forgejo && sudo docker compose exec -u git forgejo forgejo dump -c /data/gitea/conf/app.ini -f /data/forgejo-dump.zip
```

The content repository, the part that matters, is in both backups anyway: in DocuWaves' as `content.bundle`, and in Forgejo's as the repository itself.

## Updates

```bash
cd /opt/forgejo && sudo docker compose pull && sudo docker compose up -d
```

The tag `:16` follows Forgejo 16's fixes. Before you move to a new major version, read Forgejo's release notes.
