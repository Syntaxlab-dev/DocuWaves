---
title: Checking the files
order: 5
published: true
---

If you edit documentation in Git, you can check the files before DocuWaves
syncs them. `docuwaves-lint` reads your `content/` tree and checks the file
format without a running DocuWaves instance. It flags problems such as invalid
YAML, unknown keys, duplicate page slugs and broken category parents.

For example, two pages with the same slug in different categories of the
same project can produce:

```text
kb/beta/setup.md: error: duplicate-page (already in category 'alpha')
1 error(s), 0 warning(s)
```

Paths are relative to `content/`. An error makes the command exit with status
1. Warnings alone leave it at 0. Pass `--json` to get the parsed model and
diagnostics as JSON.

## Run it locally

From the root of your **content repository**, clone the DocuWaves source into
a sibling directory. The tool needs Python 3.10 or newer and PyYAML.

```sh
git clone --depth 1 --branch v2.3.1 https://github.com/Syntaxlab-dev/DocuWaves.git ../docuwaves-tools
python -m pip install PyYAML
python ../docuwaves-tools/tools/docuwaves-lint/docuwaves_lint.py content
```

Pass the directory that contains `_site.yml` (if present) and the project
folders, as shown in [The file layout](/p/docuwaves/pages/the-file-layout).

## Check pull requests in GitHub Actions

Save this as `.github/workflows/check-content.yml` in the content repository.
The second checkout puts the public DocuWaves source in its own directory
and pins it to the commit for v2.3.1. The job passes your repository's
`content/` to that copy of the linter.

```yaml
name: Check documentation content
on: pull_request

permissions:
  contents: read

jobs:
  lint-content:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/checkout@v7
        with:
          repository: Syntaxlab-dev/DocuWaves
          ref: c7105fd15c6ac603e6fe3e57d085177e8b665fc2
          path: .docuwaves-tools
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install PyYAML
      - run: python .docuwaves-tools/tools/docuwaves-lint/docuwaves_lint.py content
```
