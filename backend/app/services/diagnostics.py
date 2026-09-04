"""One page that answers "is this instance all right?", so nobody has to
answer it by reading container logs.

WHAT THIS IS FOR. Self-hosted means the person operating this has no
dashboard, no support channel and no colleague who knows the deployment.
When something is off -- pages missing, a push failing, the disk filling --
the questions are always the same handful, and every one of them is
answerable from inside the process. Asking them from a page beats asking
them from `docker exec`.

TWO RULES THIS FILE FOLLOWS.

Nothing here raises. Every section is wrapped, because a diagnostics page
that 500s when one thing is broken is a diagnostics page that is unavailable
in exactly the situation it exists for. A section that could not be measured
says so and the rest still renders.

Nothing here is a secret. This is behind the admin login, but it is also the
page an operator screenshots into a forum thread when they are stuck. So:
paths yes, sizes yes, counts yes; no token values, no password hash, no
remote URL (git_content_repo embeds the push token in it), no environment
dump. `has_remote` is a boolean, and that is the whole truth an operator
needs about it here.
"""

import logging
import platform
import shutil
from pathlib import Path

from app.services import (
    api_tokens_store,
    content_sync,
    content_versions,
    db,
    doc_chat,
    git_content_repo,
    preview_links_store,
    page_feedback_store,
    site_languages,
    backup,
)
from app.settings import settings

log = logging.getLogger("docuwaves")


def _safe(section, default):
    """Runs one section, or answers `default` plus the reason. See the module
    docstring: one broken measurement must not take the page with it."""
    try:
        return section()
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
        log.warning("Diagnostics section failed: %s", exc)
        return {**default, "error": str(exc)}


def _instance() -> dict:
    return {
        "python": platform.python_version(),
        # Which backend, never the DSN: DATABASE_URL carries a password.
        "database": "postgres" if db.is_postgres() else "sqlite",
        "content_repo_path": settings.content_repo_path,
        "sqlite_path": "" if db.is_postgres() else settings.sqlite_path,
        # Whether an operator pinned the public address, not what they pinned
        # it to -- the address is in the reader's own URL bar anyway.
        "public_base_url": settings.public_base_url,
        "languages": site_languages.languages(),
        "default_language": site_languages.default_language(),
        "sync_interval_seconds": settings.content_repo_sync_interval_seconds,
        # An env-var feature, so this page is the only place an operator can
        # see whether it took. Never the API key -- `enabled` is the whole
        # truth that is theirs to read here.
        "chat": doc_chat.status(),
    }


def _content() -> dict:
    """Counts straight out of the index. They are the fastest answer to the
    single most common report -- "a page of mine isn't showing up" -- because
    the difference between `pages` and `published` usually is the answer."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        categories = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        published = conn.execute(
            f"SELECT COUNT(*) FROM pages WHERE published = {placeholder}",
            (True if db.is_postgres() else 1,),
        ).fetchone()[0]
        slugs = [row[0] for row in conn.execute("SELECT slug FROM projects ORDER BY sort_order, name").fetchall()]
    return {
        "projects": int(projects),
        "categories": int(categories),
        "pages": int(pages),
        "published": int(published),
        "drafts": int(pages) - int(published),
        # Per project, because "which versions does this instance serve" is a
        # question with a different answer per project and no single one.
        "versions": {slug: content_versions.version_ids(slug) for slug in slugs},
    }


def _storage() -> dict:
    """Sizes, and the free space they are competing for.

    The disk is measured at the content repo's own path rather than at a
    fixed /data: that is where this instance actually writes, whatever it was
    configured with."""
    repo = backup.summary()
    root = Path(settings.content_repo_path)
    probe = root if root.exists() else root.parent
    usage = shutil.disk_usage(probe) if probe.exists() else None
    database_bytes = 0
    if not db.is_postgres():
        sqlite_file = Path(settings.sqlite_path)
        database_bytes = sqlite_file.stat().st_size if sqlite_file.is_file() else 0
    return {
        "content_files": repo["files"],
        "content_bytes": repo["bytes"],
        "database_bytes": database_bytes,
        "disk_total_bytes": usage.total if usage else 0,
        "disk_free_bytes": usage.free if usage else 0,
    }


def _operations() -> dict:
    return {
        "api_tokens": api_tokens_store.count(),
        "preview_links": _live_preview_links(),
        "feedback_votes": page_feedback_store.count(),
        "last_sync": content_sync.last_sync(),
        # A file the index could not take, and why. These are the pages that
        # exist in the repo and are invisible on the site, which is the
        # failure people spend longest chasing.
        "conflicts": content_sync.conflicts(),
    }


def _live_preview_links() -> int:
    """Links across every page that still work. The store's own sweep runs
    first, so this is a count of what a reader could open right now rather
    than a count of rows nobody has cleaned up."""
    preview_links_store.sweep_expired()
    with db.get_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM preview_links").fetchone()[0])


def _checks() -> dict:
    """The three things that are either true or the instance cannot do its
    job, each stated as a plain boolean with its reason next to it."""
    results = []

    root = Path(settings.content_repo_path)
    writable = False
    reason = "The content repo directory does not exist."
    if root.is_dir():
        probe = root / ".docuwaves-write-check"
        try:
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            writable, reason = True, ""
        except OSError as exc:
            reason = str(exc)
    results.append({"id": "content_repo_writable", "ok": writable, "detail": reason})

    status = git_content_repo.status()
    # A local-only repository is a COMPLETE state, not a degraded one -- the
    # only failure here is a repo that cannot be opened at all.
    results.append(
        {
            "id": "content_repo_open",
            "ok": status.get("last_commit") is not None or not status.get("error"),
            "detail": status.get("error") or "",
        }
    )
    results.append(
        {
            "id": "remote_reachable",
            # Not applicable rather than failing on a local instance.
            "ok": True if not status.get("has_remote") else bool(status.get("connected")),
            "detail": "" if not status.get("has_remote") else (status.get("error") or ""),
            "skipped": not status.get("has_remote"),
        }
    )
    return {"checks": results}


def report() -> dict:
    return {
        "instance": _safe(_instance, {"python": "", "database": ""}),
        "content": _safe(_content, {"projects": 0, "categories": 0, "pages": 0, "published": 0, "drafts": 0, "versions": {}}),
        "storage": _safe(_storage, {"content_files": 0, "content_bytes": 0, "database_bytes": 0, "disk_total_bytes": 0, "disk_free_bytes": 0}),
        "operations": _safe(_operations, {"api_tokens": 0, "preview_links": 0, "feedback_votes": 0, "last_sync": "", "conflicts": []}),
        "repo": _safe(git_content_repo.status, {"configured": False}),
        **_safe(_checks, {"checks": []}),
    }
