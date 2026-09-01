# Contributing to DocuWaves

Contributions to DocuWaves itself are welcome — bug fixes, features, better
error messages, translations, documentation of the tool. If you run DocuWaves
and something annoys you, that's exactly the kind of thing worth opening an
issue about.

## Before you build something big

Open an issue first and describe what you have in mind. Not as a formality —
it's so you don't spend an evening on something that turns out to conflict with
how a part of the system is meant to work. Small fixes need no ceremony: just
open the pull request.

## Running it locally

You need Docker, or Python 3.11+ and Node 20+.

```bash
git clone https://github.com/Syntaxlab-dev/DocuWaves.git
cd DocuWaves
cp .env.example .env
```

For a content repo to develop against, you don't need GitHub or a token — a
local bare repository works:

```bash
git init --bare /tmp/docuwaves-dev-content.git
# then in .env:
#   CONTENT_REPO_URL=file:///tmp/docuwaves-dev-content.git
```

Then either `docker compose up -d --build`, or run the two halves directly:

```bash
cd backend  && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev    # proxies /api to localhost:8000
```

## How the pieces fit together

Worth knowing before you change anything:

- **The content repo is the source of truth, the database is not.** Every
  project, category, and page is a file in a Git repository. The database is a
  rebuildable index over those files, used for browsing and full-text search.
  Deleting the database loses nothing; it's rebuilt on the next start or sync.
- **`git_content_repo.py` is the only module that talks to Git.** Everything
  else reads and writes plain files in the local clone and lets that module
  handle commits, pushes, and conflicts. Please keep it that way.
- **Anything user-supplied that becomes a path gets slugified first.** Project,
  category, and page names all end up as directory and file names.
- **Raw SQL, no ORM**, and it has to work on both SQLite and PostgreSQL — see
  the placeholder handling in `db.py`.

## What a good pull request looks like

- One concern per pull request.
- Match the surrounding style. Comments in this codebase explain *why* something
  is the way it is, not what the line does — several of them exist because a bug
  was found the hard way, and they're there so it isn't reintroduced.
- Say in the description what you actually ran to convince yourself it works.
  "Built the container, uploaded an image, checked it appears on the public
  page" is worth more than a green checkmark.
- If you found something broken along the way that's unrelated to your change,
  mention it separately rather than fixing it in the same pull request.

## Reporting a bug

Include what you did, what you expected, and what happened instead — plus your
DocuWaves version (shown in the admin area), whether you're on SQLite or
Postgres, and whether you're behind a reverse proxy. That last one explains a
surprising share of login and redirect problems.

## Security

Found something with security impact? Please don't open a public issue — use
GitHub's private vulnerability reporting on this repository instead.

## License

By contributing you agree that your contribution is licensed under this
project's MIT license.
