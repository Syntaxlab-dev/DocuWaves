---
order: 3
published: true
title: Docs-as-code
---

A project's documentation can live in the **code repository it documents** —
a `docs/` folder, written in the same pull requests as the code — and
DocuWaves follows it: the repository's CI sends the folder on every push to
the main branch, and the project becomes exactly that.

These pages are written that way: they live in the DocuWaves repository
under `docs/`.

## Setting it up

**1. A sync token.** In the admin area, **API tokens** → scope **Sync**, and
pick the project (create the project first if it is new). A sync token can
replace that one project's content and do nothing else — not another
project, not the [MCP endpoint](/p/docuwaves/pages/the-mcp-endpoint), not
the admin area. DocuWaves never gets access to the code repository.

**2. A CI step.** Store the token as a secret named `DOCUWAVES_TOKEN` in the
code repository and add one job:

<!-- tabs -->
#### GitHub / Forgejo / Gitea
```yaml title=".github/workflows/docs.yml"
on:
  push:
    branches: [main]
    paths: ["docs/**"]
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          cd docs && zip -qr ../docs.zip .
          curl --fail-with-body -X POST \
            -H "Authorization: Bearer ${{ secrets.DOCUWAVES_TOKEN }}" \
            --data-binary @../docs.zip \
            "https://docs.example.com/api/sync/my-project?ref=${GITHUB_SHA::7}&repo=${{ github.server_url }}/${{ github.repository }}&branch=main&path=docs"
```
#### GitLab
```yaml title=".gitlab-ci.yml"
docs:
  image: alpine
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      changes: ["docs/**/*"]
  script:
    - apk add --no-cache zip curl
    - cd docs && zip -qr ../docs.zip .
    - curl --fail-with-body -X POST -H "Authorization: Bearer $DOCUWAVES_TOKEN"
        --data-binary @../docs.zip
        "https://docs.example.com/api/sync/my-project?ref=$CI_COMMIT_SHORT_SHA&repo=$CI_PROJECT_URL&branch=$CI_DEFAULT_BRANCH&path=docs"
```
<!-- /tabs -->

`repo`, `branch` and `path` are optional; they give every page an **Edit in
the repository** button.

## What a sync does

- The ZIP is read like an [import](/p/docuwaves/pages/importing-a-zip) —
  plain Markdown, MkDocs, Docusaurus, GitBook, Obsidian or a DocuWaves
  content folder — and then **replaces** the project's content: new files
  become pages, changed ones are updated, and **a file deleted in the
  repository deletes the page**.
- **Addresses come from file names**, not titles: rewording a heading never
  breaks a link. `slug: my-address` in the front matter pins one;
  `docs/setup/index.md` is the page `setup`, the top `index.md` is `start`.
- **Pages go live.** They were reviewed as a pull request, which is the
  approval. `draft: true` (or `published: false`) in the front matter keeps
  a page a draft.
- **One commit per sync** ("Sync from a1b2c3d"), and **none when nothing
  changed** — syncing on every push is safe. The answer to the CI says what
  was added, changed and removed.
- [Webhooks](/p/docuwaves/pages/webhooks) announce new and changed pages as
  for any edit — except on the first sync into an empty project, which would
  announce every page at once.

## Release tags become versions

Add `version=` to the request and the synced docs are **frozen as that
version** right after the sync — a release tag in the code repository
becomes a [frozen version](/p/docuwaves/pages/freezing-a-version) of its
documentation, with its own entry in the version switcher:

```yaml title=".github/workflows/docs.yml (excerpt)"
on:
  push:
    branches: [main]
    tags: ["v*"]
# … in the run step, after building docs.zip:
#   VERSION=""
#   if [ "$GITHUB_REF_TYPE" = "tag" ]; then VERSION="&version=$GITHUB_REF_NAME"; fi
#   curl … "https://docs.example.com/api/sync/my-project?ref=${GITHUB_SHA::7}${VERSION}"
```

- The tag `v2.0` becomes the version `v2.0`, labelled **2.0** in the switcher
  (`&label=…` names it differently).
- The sync and the freeze are **two commits**: first the docs as of the tag,
  then *"Freeze version 2.0 from v2.0"*.
- The **first** freeze moves the project's content into `current/`, as any
  first freeze does; the next sync writes there automatically.
- Pushing the same tag again — a re-run CI job — leaves the existing version
  alone, and the answer says so.
- An id that cannot be a version (`../x`, `current`) is refused **before**
  anything is written.

Released versions have no **Edit in the repository** button: a release is
changed nowhere, not even in the repository. Readers keep landing on
`current` unless you make a release the default under **Versions**.

## In the admin area

A synced project says so above its categories: which repository, branch and
folder, when the last sync ran, from which commit, and what it changed — with
the history of the last runs.

Its pages and categories are **read-only**: the editor, the
[approval workflow](/p/docuwaves/pages/approval-before-publishing), the MCP
endpoint and the import all refuse to change them, because the next sync
would replace the change. Each page has **Edit in the repository** instead,
which opens the file in GitHub's, GitLab's or Forgejo's editor. Images,
snippets and versions stay editable — the sync does not own them.

The first sync marks the project as synced, in its `_project.yml`:

```yaml title="content/my-project/_project.yml"
source:
  repo: https://github.com/acme/my-project
  branch: main
  path: docs
```

Switch **Where the pages come from** back to *Here, in the editor* in the
project settings to edit the pages in DocuWaves again — until the next sync.
