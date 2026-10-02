---
order: 1
published: true
title: Behind a reverse proxy
---

DocuWaves listens on port **8000** inside the container; the shipped compose file publishes it on **8091**. Anything public should sit behind a proxy that terminates TLS.

## What the proxy has to forward

Two headers, and they are not optional if the site answers on a domain:

```
X-Forwarded-Proto
X-Forwarded-Host
```

The image already runs uvicorn with `--proxy-headers --forwarded-allow-ips=*`, so it trusts them. From those, plus the request's own scheme and `Host` as a fallback, DocuWaves works out the address **readers** use — which is not the address the container sees.

An nginx location block that does it:

```nginx
server {
    listen 443 ssl;
    server_name docs.example.com;

    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    }
}
```

Caddy needs no configuration for this — it sets those headers itself:

```caddy
docs.example.com {
    reverse_proxy 127.0.0.1:8091
}
```

## Why it matters

Every absolute URL DocuWaves publishes is built from that address:

- `<link rel="canonical">` on every page
- `og:url` in the Open Graph tags a chat client reads to build a link preview
- every `<loc>` in `/sitemap.xml`
- the `Sitemap:` line in `/robots.txt`
- the OIDC `redirect_uri`, which a strict identity provider matches exactly and rejects outright if the scheme is wrong

Get it wrong and the symptoms are indirect: link previews that point at `http://172.18.0.3:8000`, a sitemap search engines cannot use, and an SSO login that fails at the provider.

## Checking it

Ask the application what it thinks:

```bash
curl -s https://docs.example.com/robots.txt | tail -1
```

The last line is the same base URL every canonical tag on the site is built from. If it says `http://` or names an internal host, the headers are not arriving.

## `PUBLIC_BASE_URL`

Set it to override what the application works out for itself:

```bash
PUBLIC_BASE_URL=https://docs.example.com
```

Two reasons to need it: your proxy does not forward those headers, or the site answers at several addresses and exactly one of them is canonical.

It must be an absolute `http://` or `https://` URL. A bare hostname is **ignored** and the auto-detected address is used instead — a canonical tag pointing at `docs.example.com/p/x` is one no crawler can fetch, so a half-filled value is worse than none. A trailing slash is stripped.

## Two things that are easy to get wrong

**Do not let the proxy serve its own `/robots.txt` or `/sitemap.xml`.** DocuWaves serves both at the site root itself, and they are generated from your actual content. A `location = /robots.txt` in the vhost that returns a static file will shadow the application's — silently, and possibly with a `Disallow: /` that keeps the whole site out of search. Some hosting panels add one without being asked. The `curl` above is also the check for this.

**The proxy is the access log.** The image runs uvicorn with `--no-access-log` deliberately: a public site is scanned around the clock by bots probing for WordPress, and logging every request twice buys nothing while burying the lines that matter — startup, sync failures, tracebacks. Your proxy already logs each request with the real client IP.

## Health check

The image declares a health check against `/health`, which confirms the database is reachable. It answers `GET` and `HEAD`, so an uptime monitor using either works.
