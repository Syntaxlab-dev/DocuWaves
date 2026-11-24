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
| `favicon.svg`, `apple-touch-icon.png` | Browser and home-screen icons |
| `img/wordmark.svg`, `img/wordmark-dark.svg` | The logo, light and dark |
| `img/og.png` | 1200×630 link-preview image (Open Graph / Twitter card) |
| `img/*.webp` | Screenshots, made from the PNGs in [`docs/assets/`](../docs/assets/) |
| `robots.txt`, `sitemap.xml` | For search engines |

## Previewing

Open `index.html` through any static server, so the absolute `/img/...`
paths resolve:

```bash
cd website && python3 -m http.server 8000
# then http://localhost:8000
```

## Publishing

Copy the contents of this folder to the web root of docuwaves.app, for
example:

```bash
rsync -av --delete --exclude README.md website/ user@server:/path/to/docuwaves.app/
```

Two things to check after a change to the server's panel: `robots.txt` must
still be this one (the panel writes a `Disallow: /` version when a site is
created), and `sitemap.xml`'s `<lastmod>` should be the date of the last
content change.

## Updating the screenshots

The screenshots are the ones in `docs/assets/`, converted to WebP at the
size the page declares (`width`/`height` on each `<img>`). When those are
retaken, convert them again so the landing page and the documentation show
the same thing.
