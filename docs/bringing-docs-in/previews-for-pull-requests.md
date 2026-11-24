---
order: 6
published: true
title: Previews for pull requests
---

With [docs-as-code](/p/docuwaves/pages/docs-as-code), the documentation is
changed in pull requests. A reviewer wants to see the result before the
merge, and the import's warnings (a link that points nowhere, a missing
image) are best found before they are live.

DocuWaves builds a preview **without an instance**: the docs folder is
imported into a throwaway DocuWaves inside the CI job, exactly as the real
sync would import it, and written out as a static website. No token, no
server, nothing published.

## In GitHub Actions

```yaml
name: Docs preview
on:
  pull_request:
    paths: ["docs/**"]
permissions:
  contents: read
jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Build the preview
        run: |
          mkdir -p out
          docker run --rm -v "$PWD/docs:/docs:ro" -v "$PWD/out:/out" \
            ghcr.io/syntaxlab-dev/docuwaves:latest \
            python -m app.cli preview-site /docs /out/site.zip --name "Our docs" --summary /out/summary.json
          mkdir -p preview && cd preview && unzip -q ../out/site.zip
      - uses: actions/upload-artifact@v4
        with:
          name: docs-preview
          path: preview/
```

The run's **docs-preview** artifact is the site: download it and open
`index.html`. `summary.json` lists the page count and every warning, so the
job can also print them, or fail on them if you want that.

DocuWaves' own repository does the same with
`.github/workflows/docs-preview.yml`, which also writes the warnings into
the job summary.

## Anywhere else

The command is the same in any CI, or on your own machine:

```bash
docker run --rm -v "$PWD/docs:/docs:ro" -v "$PWD/out:/out" \
  ghcr.io/syntaxlab-dev/docuwaves:latest \
  python -m app.cli preview-site /docs /out/site.zip
```

The preview is the [static export](/p/docuwaves/pages/backups-and-updates),
so it shows pages, navigation, images and callouts, without search, chat or
the version switcher.
