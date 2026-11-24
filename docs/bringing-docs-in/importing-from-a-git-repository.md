---
order: 4
published: true
title: Importing from a Git repository
---

Documentation that already lives in a repository, such as an MkDocs or a Docusaurus site next to the code, can be imported from its address. There is no need to download it and upload a ZIP.

Under **Import**, switch the source to **Git repository** and enter:

- **The address**: the repository's `https://` URL, on GitHub, GitLab, Codeberg, a Forgejo of your own or anywhere else.
- **A folder**, optionally, such as `docs` or `website/docs`, when only part of the repository is documentation.
- **A branch**, optionally. Without one, the repository's default branch is used.
- **A token** for a private repository. It is used for this one clone and is not stored anywhere.

**Preview** clones the repository, one commit deep, and shows what would be created. **Import** clones it again and imports its state at that moment. From there it works exactly like [importing a ZIP](/p/docuwaves/pages/importing-a-zip): MkDocs (`mkdocs.yml` with its `nav`), Docusaurus (`docusaurus.config.*`, `_category_.json`, `sidebar_position`), GitBook and plain Markdown are recognised. Every page arrives as a draft, in one commit, and nothing that exists is overwritten.

## What it reads

Only Markdown, images and media, and the navigation files of the tools above. Source code, the repository's history and its `.git` folder are never taken over. The same limits as for a ZIP apply.

## What it accepts

Only `https://` addresses. `ssh`, `git://` and local paths are refused, and so is an address that points at the server itself or at a link-local address. Private network addresses work, so a Forgejo on the same network is fine. A clone that takes longer than two minutes is stopped: import a ZIP of the docs folder instead.

This is a one-time import. To keep a project in step with a repository on every push, use [docs-as-code](/p/docuwaves/pages/docs-as-code) instead.
