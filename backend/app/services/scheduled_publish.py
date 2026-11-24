"""Scheduled publishing: a draft that goes live by itself at a set time.

WHERE THE SCHEDULE LIVES. In the database, not in the page file. A page's
front matter is rewritten by a dozen code paths (saving, reordering,
reviewing, moving), and a `publish_at:` key every one of them had to carry
over is a key one of them would one day drop -- silently, which for a launch
announcement is the worst way to fail. A row keyed by the page's address
(project, page slug, language, version), like a preview link, is written in
one place and read in one place. Renaming a page moves its schedule
(repoint_page); deleting a page removes it (forget_page).

WHO PUBLISHES. The scheduler, a loop in the app that looks once a minute
(run_due). It publishes exactly as the editor's Publish button would --
pages_store.set_published, one commit -- under the name of the person who
scheduled it, so the history and the notifications say who meant it to go
live.

NOT IN PROJECTS THAT REQUIRE APPROVAL. There, going live IS the approval
(services/page_review.py), and a timer that publishes what nobody approved
would be a way around it. Scheduling is refused in such a project; a
schedule left over when a project starts requiring approval is dropped by
the scheduler with a log line rather than carried out.

TIMES are stored in UTC (ISO 8601). The browser sends the moment with its
offset; what the editor shows is converted back to the reader's local time.
A schedule that is already due when the instance starts (it was down at the
time) is carried out at the next tick, late rather than never.
"""
import logging
from datetime import datetime, timezone

from app.services import db

log = logging.getLogger("docuwaves")

TICK_SECONDS = 60


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def parse(value: str) -> datetime | None:
    """An ISO 8601 moment WITH an offset, as UTC; None for anything else.
    A time without an offset is refused rather than guessed: "09:00" means
    a different moment on the server than in the browser that sent it."""
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).replace(microsecond=0)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


_COLUMNS = "project_slug, page_slug, language, version, publish_at, scheduled_by"


def _row(row) -> dict:
    return dict(zip(("project_slug", "page_slug", "language", "version", "publish_at", "scheduled_by"), row, strict=True))


def get(project_slug: str, page_slug: str, language: str, version: str) -> dict | None:
    p = _placeholder()
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM scheduled_publish WHERE project_slug = {p} AND page_slug = {p} "
            f"AND language = {p} AND version = {p}",
            (project_slug, page_slug, language, version),
        ).fetchone()
    return None if row is None else _row(row)


def set_schedule(project_slug: str, page_slug: str, language: str, version: str, moment: datetime, by: str) -> dict:
    p = _placeholder()
    key = (project_slug, page_slug, language, version)
    with db.get_connection() as conn:
        conn.execute(
            f"DELETE FROM scheduled_publish WHERE project_slug = {p} AND page_slug = {p} AND language = {p} AND version = {p}",
            key,
        )
        conn.execute(
            f"INSERT INTO scheduled_publish ({_COLUMNS}) VALUES ({p}, {p}, {p}, {p}, {p}, {p})",
            (*key, _iso(moment), by),
        )
    return get(*key)  # type: ignore[return-value]


def cancel(project_slug: str, page_slug: str, language: str, version: str) -> bool:
    p = _placeholder()
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM scheduled_publish WHERE project_slug = {p} AND page_slug = {p} AND language = {p} AND version = {p}",
            (project_slug, page_slug, language, version),
        )
        return bool(cursor.rowcount)


def upcoming() -> list[dict]:
    with db.get_connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM scheduled_publish ORDER BY publish_at").fetchall()
    return [_row(r) for r in rows]


def due(now: datetime | None = None) -> list[dict]:
    moment = _iso(now or datetime.now(timezone.utc))
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM scheduled_publish WHERE publish_at <= {_placeholder()} ORDER BY publish_at",
            (moment,),
        ).fetchall()
    return [_row(r) for r in rows]


def repoint_page(project_slug: str, old_slug: str, new_slug: str, version: str) -> None:
    if old_slug == new_slug:
        return
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE scheduled_publish SET page_slug = {p} WHERE project_slug = {p} AND page_slug = {p} AND version = {p}",
            (new_slug, project_slug, old_slug, version),
        )


def forget_page(project_slug: str, page_slug: str, version: str) -> None:
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"DELETE FROM scheduled_publish WHERE project_slug = {p} AND page_slug = {p} AND version = {p}",
            (project_slug, page_slug, version),
        )


# ---- The scheduler ----


def run_due(now: datetime | None = None) -> int:
    """Publishes every page whose time has come. Returns how many went live.
    Each schedule is removed once handled -- carried out, or found to be
    impossible (page gone, already live, approval now required) -- so a
    failing one is not retried forever; a git error leaves it for the next
    tick."""
    from app.services import git_content_repo, pages_store, projects_store

    published = 0
    for entry in due(now):
        key = (entry["project_slug"], entry["page_slug"], entry["language"], entry["version"])
        project = projects_store.get_project_by_slug(entry["project_slug"])
        page = (
            pages_store.get_page_by_slug(project["id"], entry["page_slug"], entry["language"], entry["version"])
            if project
            else None
        )
        if page is None or page["published"]:
            cancel(*key)
            continue
        if pages_store.review_required(project):
            log.warning("Scheduled publishing of %s/%s dropped: the project requires approval", *key[:2])
            cancel(*key)
            continue
        try:
            pages_store.set_published(page["id"], True, entry["scheduled_by"] or "scheduler")
        except git_content_repo.GitContentError as exc:
            log.warning("Scheduled publishing of %s/%s failed, retrying: %s", key[0], key[1], exc)
            continue
        except Exception:  # noqa: BLE001 -- one bad page must not stop the others
            log.exception("Scheduled publishing of %s/%s failed", key[0], key[1])
            cancel(*key)
            continue
        cancel(*key)
        published += 1
    return published
