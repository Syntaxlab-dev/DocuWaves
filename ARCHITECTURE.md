# How DocuWaves is built

A map for finding your way around the code. [CONTRIBUTING.md](CONTRIBUTING.md)
covers setup and tests. The format of the content files has a spec of its own
in [spec/content-format.md](spec/content-format.md).

## The big picture

```
 browser ──► React app (frontend/)  ──► /api/...  ──► FastAPI (backend/app)
                                                        │
 AI assistant ──► /mcp (routers/mcp.py) ────────────────┤
                                                        ▼
                                  services/*_store.py  (reads: database index)
                                         │      ▲
                       writes: content_files.py │ content_sync.py rebuilds
                                         ▼      │
                              local Git clone of the content repo
                                         │
                              git_content_repo.py  ──►  remote (optional)
```

One container serves both halves: the backend answers `/api/*`, `/mcp` and a
few XML routes (sitemap, feeds), and serves the built frontend
(`backend/static` is a symlink to `frontend/dist`) for everything else.

## Three rules the code relies on

1. **The content repository is the truth. The database is an index.**
   Every project, category and page is a file. `content_sync.py` reads the
   files and rebuilds the `projects`, `categories` and `pages` tables (and the
   search index) from them. Deleting the database loses nothing.
2. **Only `git_content_repo.py` talks to Git.** Everything else reads and
   writes plain files in the local clone, then calls `commit_and_push()` or
   uses `batch()`. GitPython's reader is not thread-safe, so reads of `HEAD`
   go through `_head_hexsha()` and the object-database lock. A test guards
   this (`tests/test_git_read_lock.py`).
3. **Every name that becomes a path is slugified first.** Project, category
   and page names end up as directory and file names.

## A page save, end to end

1. The editor (`frontend/src/pages/admin/PageEditor.tsx`) sends
   `PUT /api/admin/pages/{id}` through `lib/api.ts`.
2. `routers/admin_content.py` checks the session and the user's role on the
   project (`services/project_access.py`; every write route must be listed in
   `WRITE_ROUTES` there, or a test fails).
3. `services/pages_store.update_page()` validates the change and calls
   `content_files.write_page()`, which writes the Markdown file with its YAML
   frontmatter.
4. `git_content_repo.commit_and_push()` commits the file as the editor and
   pushes when a remote is configured. A rejected push is retried after a
   pull. If the same file changed on both sides, the change stays committed
   locally and the editor is told to resolve the conflict.
5. The `pages` row and the search index are updated, and the reader sees
   the new text on the next request.

Edits made directly in the content repository take the other direction:
a background loop in `main.py` pulls the remote every
`CONTENT_REPO_SYNC_INTERVAL_SECONDS` and runs `content_sync.full_sync()`,
which reindexes from the files. "Sync now" in the admin does the same at
once. `routers/sync.py` is a different thing: it lets a code repository's
CI push its `docs/` folder into a project.

## Backend (`backend/app`)

| Where | What |
|---|---|
| `main.py` | App setup, startup work (`lifespan`), router registration, the web manifest, static files |
| `settings.py` | Every environment variable, read in one place |
| `auth_guard.py` | Session and API-token checks used by the routers |
| `cli.py` | The `python -m app.cli` commands (password reset, user list, database snapshot, static preview, demo seed) |
| `routers/` | HTTP endpoints, thin. `public_content.py` for readers, `admin_content.py` for the admin, `mcp.py` for AI assistants |
| `services/*_store.py` | Reading and writing projects, categories, pages, users, tokens |
| `services/content_files.py` | The on-disk format: paths, frontmatter, `_project.yml`, `_category.yml` |
| `services/content_sync.py` | Rebuilds the database index from the files |
| `services/git_content_repo.py` | Clone, pull, commit, push, status |
| `services/db.py` | Raw SQL for SQLite and PostgreSQL (no ORM; placeholders are translated) |
| `services/import_*.py` | Importers for Confluence, BookStack, Wiki.js, MediaWiki, Notion and Git |
| `services/mcp_tools.py` | The tools an AI assistant can call |

Tests live in `backend/tests` and need no server or network.

## Frontend (`frontend/src`)

| Where | What |
|---|---|
| `App.tsx` | Routes: the public site, `/admin/*`, previews |
| `pages/Public*.tsx` | The reader's side: home, project, category, page, search |
| `pages/AdminApp.tsx`, `pages/admin/` | The admin: sidebar, dashboard, lists, the page editor |
| `components/` | Shared pieces: `MarkdownView`, `QuickSearch`, `DocsSidebar`, dialogs |
| `lib/api.ts` | Every call to the backend, with its types |
| `lib/site.tsx` | Branding of the instance (name, logo, colours) |
| `lib/i18n.tsx` | Interface texts in English and German |

Unit tests sit next to the code (`*.test.ts`, run with `npm test`). The
end-to-end tests in `frontend/e2e/` start a real instance with
`e2e/serve.sh`. They run in order and build on each other, so add new ones at
the end of the file.

## Around the app

| Where | What |
|---|---|
| `spec/` | The content-format spec and its conformance cases |
| `tools/docuwaves-lint/` | A standalone checker for content repositories |
| `docs/` | DocuWaves' own documentation, published to docs.docuwaves.app |
| `installer/` | `install.sh` and its tests |
| `website/` | The docuwaves.app landing page (deployed on merge) |
| `.github/workflows/` | Tests, image builds, releases, docs and website deploys |
