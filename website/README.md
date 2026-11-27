# docuwaves.app

The source of the landing page at <https://docuwaves.app>. It is one static
HTML file with its CSS inlined, a handful of images, and no build step:
what is in this folder is exactly what the web server serves.

The user documentation at <https://docs.docuwaves.app> is something else —
that is a DocuWaves instance, and its source is [`docs/`](../docs/).

## Files

| Path | What it is |
|---|---|
| `index.html` | The page. Styles are inline, the only script is the copy button |
| `de/index.html` | The same page in German, at `/de/`. Same styles and images; the two link to each other (`hreflang`) |
| `favicon.svg`, `apple-touch-icon.png` | Browser and home-screen icons |
| `img/logo.svg`, `img/logo-light.svg`, `img/mark.svg` | The logo for dark and light backgrounds, and the mark alone. `favicon.svg` is the simplified mark for small sizes. The wordmark is Montserrat (SIL Open Font Licence), converted to paths |
| `img/og.png` | 1200×630 link-preview image (Open Graph / Twitter card) |
| `img/*.webp` | Screenshots of the reader and the admin |
| `robots.txt`, `sitemap.xml` | For search engines |

## Previewing

Open `index.html` through any static server, so the absolute `/img/...`
paths resolve:

```bash
cd website && python3 -m http.server 8000
# then http://localhost:8000
```

## Publishing

A push to `main` that changes `website/` publishes it:
[`.github/workflows/website.yml`](../.github/workflows/website.yml) checks
that every page parses and every local link exists, copies the folder to the
web root over SSH with `rsync --delete`, and then checks that the live pages
answer. It can also be started by hand from the Actions tab.

It needs the repository secrets `WEBSITE_SSH_HOST`, `WEBSITE_SSH_USER` and
`WEBSITE_SSH_KEY`, and optionally `WEBSITE_PATH`, `WEBSITE_OWNER` and
`WEBSITE_SSH_KNOWN_HOSTS`; the workflow file says what goes in each. Until
the first three are set, the job skips the copy and says so.

On the server, the deploy key is locked to `rrsync` for the document root
(`command="/usr/bin/rrsync <docroot>",restrict` in `authorized_keys`), so it
can write that one folder and do nothing else.

By hand, the same copy is:

```bash
rsync -av --delete --exclude README.md website/ user@server:/path/to/docuwaves.app/
```

Two things to check after a change to the server's panel: `robots.txt` must
still be this one (the panel writes a `Disallow: /` version when a site is
created), and `sitemap.xml`'s `<lastmod>` should be the date of the last
content change.

## Two languages

`index.html` (English, at `/`) and `de/index.html` (German, at `/de/`) are
the same page. A change to one belongs in the other in the same commit: the
CSS block is identical and can be copied over whole, the text is translated.
Both carry `<link rel="alternate" hreflang>` for each other, and
`sitemap.xml` lists both.

## Updating the screenshots

`reader-home`, `editor`, `content-tree` and `theme` are the same files as
the README's, in [`.github/screenshots/`](../.github/screenshots/); copy
them over when those are retaken. `tokens.webp` is the API tokens panel of
a fresh instance. Keep the `width`/`height` on each `<img>` in step with
the file, so the page does not jump while images load.
