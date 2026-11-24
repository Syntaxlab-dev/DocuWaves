"""What happened in the documentation lately, for the admin area: every
commit to the content repo, newest first, with who made it, what it says,
and which pages it touched.

The public changelog (services/changelog.py) answers "what is new for a
reader" and deliberately says nothing about who or how. This is the other
side: drafts, reviews, renames, imports, edits made in Git -- everything,
attributed, because the people asking are the ones writing the docs.

Read straight from the repo history, so it includes changes that never went
through this app (a push from somebody's editor, a docs-as-code sync), and
nothing has to be recorded twice.
"""

from app.services import db, git_content_repo, projects_store, site_languages

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _parse(path: str) -> dict | None:
    """content/<project>/[<version>/]<category>/[_pending/]<slug>[.<lang>].md
    -> {project, version, slug, language, pending}, or None for anything
    that is not a page file."""
    parts = path.split("/")
    if len(parts) < 4 or parts[0] != "content" or not parts[-1].endswith(".md") or parts[1].startswith("_"):
        return None
    pending = "_pending" in parts
    inner = [p for p in parts[2:-1] if p != "_pending"]
    version = inner[0] if len(inner) == 2 else ""
    stem = parts[-1][: -len(".md")]
    slug, language = stem, ""
    if "." in stem:
        head, _, tail = stem.rpartition(".")
        if tail in site_languages.languages():
            slug, language = head, tail
    return {"project": parts[1], "version": version, "slug": slug, "language": language, "pending": pending}


def _title(project_id: int, slug: str, version: str) -> str:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT title FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} "
            f"AND version = {placeholder} ORDER BY language LIMIT 1",
            (project_id, slug, version),
        ).fetchone()
    return row[0] if row else ""


def recent(limit: int = DEFAULT_LIMIT) -> list[dict]:
    limit = max(1, min(MAX_LIMIT, limit))
    projects: dict[str, dict | None] = {}
    entries = []
    for commit in git_content_repo.recent_commits("content", limit):
        pages = []
        seen = set()
        other = 0
        for change in commit["files"]:
            parsed = _parse(change["path"])
            if parsed is None:
                other += 1
                continue
            key = (parsed["project"], parsed["version"], parsed["slug"], parsed["language"], parsed["pending"])
            if key in seen:
                continue
            seen.add(key)
            if parsed["project"] not in projects:
                projects[parsed["project"]] = projects_store.get_project_by_slug(parsed["project"])
            project = projects[parsed["project"]]
            title = _title(project["id"], parsed["slug"], parsed["version"]) if project else ""
            pages.append({
                "project_slug": parsed["project"],
                "project_name": project["name"] if project else parsed["project"],
                "version": parsed["version"],
                "slug": parsed["slug"],
                "language": parsed["language"],
                "pending": parsed["pending"],
                # "" when the page is gone now (deleted, or renamed since).
                "title": title,
                "status": change["status"],
            })
        entries.append({
            "sha": commit["sha"],
            "date": commit["date"],
            "author": commit["author"],
            "message": commit["message"],
            "pages": pages,
            "other_files": other,
        })
    return entries
