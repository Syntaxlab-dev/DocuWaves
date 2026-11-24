# Roadmap

Where DocuWaves is going, in the order it is planned. Each phase ends in a
release, so every step stays small enough to test and to ship.

This is a plan, not a promise: items move between phases when something
turns out more or less useful than expected. Two rules don't move. Content
stays files in Git, and nothing calls a third party unless an operator
switched it on.

**Want something on it, or higher up?** Say so in
[Discussions](https://github.com/Syntaxlab-dev/DocuWaves/discussions) under
*Ideas*, or open a [feature request](https://github.com/Syntaxlab-dev/DocuWaves/issues/new?template=feature_request.yml).
**Want to help build it?** Issues labelled
[`good first issue`](https://github.com/Syntaxlab-dev/DocuWaves/labels/good%20first%20issue)
are small and self-contained; [CONTRIBUTING.md](CONTRIBUTING.md) says how to
start.

Effort: **S** up to a day, **M** two to five days, **L** more than a week.

## v1.1: foundations and quick wins

| | Item | Effort |
|---|---|---|
| ✅ | Two-factor sign-in: security keys such as a YubiKey, passkeys, authenticator apps, recovery codes | M |
| ✅ | Previous/next links at the end of every page | S |
| ✅ | Renamed pages keep their old address (`_redirects.yml`, a 301) | M |
| ✅ | "Review due": pages nobody has checked for a project's review interval | S |
| ✅ | Activity feed in the admin area, read from the Git history | S |
| ✅ | A first draft, written by AI from existing pages, for a search that found nothing | S |
| ✅ | A notice for admins when a new release is out (can be switched off) | S |
| ✅ | Lint in CI (ruff, oxlint) and a main bundle a quarter of its former size | S |
| ✅ | The admin app split into one file per panel | M |
| ✅ | End-to-end tests with Playwright, in CI | M |
| ✅ | A short README; the details live in the documentation | S |
| ✅ | The landing page in German, published by GitHub Actions | S |
| ✅ | This roadmap, Discussions and `good first issue` labels | S |

## v1.2: teams

| | Item | Effort |
|---|---|---|
| ✅ | Permissions per project (for example, Write for project A only) | L |
| ✅ | E-mail notifications: approval requested or decided, page changed | M |
| ✅ | A log of admin actions (accounts, tokens, branding) | M |
| ✅ | Scheduled publishing | M |
| ✅ | Bulk actions: publish, move or delete several pages at once | M |
| ✅ | Search and replace across a project, with a preview, as one commit | M |
| ✅ | Readers subscribe to one page or category (RSS) | S |

## v1.3: reach

| | Item | Effort |
|---|---|---|
| ✅ | A live demo instance that resets every night | M |
| ✅ | A comparison page: DocuWaves and BookStack, Wiki.js, Docusaurus, Outline | S |
| ✅ | Import straight from a Git repository URL (MkDocs, Docusaurus) | M |
| ✅ | Import from BookStack, Wiki.js and MediaWiki | M |
| ✅ | Export as a static website (HTML zip) | M |
| ✅ | A documentation preview for pull requests, for docs-as-code | M |
| ✅ | AI writing help in the editor: rephrase, shorten, summarise | M |
| ✅ | Translation drafts for a second language, always as a draft | M |
| ✅ | More MCP tools: page history, request approval, create a preview link | S |
| ✅ | Official support and a guide for rootless Podman | S |
| ✅ | Deploy templates for Coolify, Unraid, Proxmox LXC and Kubernetes (Helm) | M |

## v2.0: bigger pieces

| Item | Effort |
|---|---|
| Nested categories | L |
| Inline comments on passages, for reviews | L |
| Suggested changes as a Git branch instead of a direct commit | L |
| Optional semantic search (embeddings, local ones too) | L |
| An API reference page from an OpenAPI file | L |
| Search filters by project, version and language | M |
| A glossary, with tooltips for its terms | M |
| Offline reading as an installable web app (PWA) | M |
| An embeddable search widget for other apps and sites | M |
| An optional, anonymous comment with "Was this helpful?" | S |
| PDF templates with your own branding (header, footer, logo) | M |
| Crop, annotate and blur screenshots in the editor | M |
| New blocks: steps, card grids, badges | M |
| Export a project as EPUB or a Markdown zip | S |
| Webhook formats for Microsoft Teams and Matrix | S |
| Automatic off-site backups (S3 or SFTP) in the installer | M |
| A `/metrics` endpoint for Prometheus | S |
