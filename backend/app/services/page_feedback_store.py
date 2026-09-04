""""Was this page helpful?" -- one row per answer.

Why a vote and not comments. A comment box on a documentation site is a
moderation queue: spam, questions nobody answers, and abuse, all of it
public and all of it the operator's problem. A thumb is the smallest thing
that still answers the question an author actually has, which is "is this
page working". Anything more specific belongs in the issue tracker the
footer already links to.

Why it lives in the database rather than in the content repo. Everything
else a reader sees is a file, and this deliberately is not one. An
anonymous vote must never become a commit -- a repository taking a write
per click would be unusable, and the commit log is a record of what the
documentation SAID, not of what visitors thought of it. So this sits beside
the credentials and the API tokens: operational data the instance owns.
It is therefore also the one thing in this database that a backup is
genuinely needed for; see db.py's note on _CONTENT_TABLES.

Pages are named by SLUG, never by pages.id. Those ids are handed out afresh
by every full reindex, so a numeric reference would quietly repoint a
page's votes at whatever page inherited its id.

What is deliberately NOT stored: no IP address, no user agent, no cookie,
no identifier of any kind. The counts are the whole point, and a
documentation site has no business keeping a record of who read what. The
abuse control below is an in-memory counter that forgets by itself.
"""
import threading
import time
from datetime import datetime, timezone

from app.services import db

# One page, one opinion, roughly: a reader changing their mind is fine, a
# script sending ten thousand is not. Deliberately loose -- the cost of
# refusing a genuine second vote is worse than the cost of counting one.
_RATE_LIMIT_VOTES = 20
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_BUCKET_SWEEP_AT = 2048

_rate_lock = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def rate_limited(client_key: str) -> bool:
    """True = this client has voted too often in the last minute.

    `client_key` is whatever the router can see of the caller -- an address,
    usually. It is used ONLY here, in memory, and never written anywhere: the
    bucket is a counter, not a log, and it is swept rather than retained.
    """
    if not client_key:
        return False
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    with _rate_lock:
        if len(_rate_buckets) > _RATE_BUCKET_SWEEP_AT:
            # Behind a proxy every distinct client address becomes a key, so
            # this would otherwise grow for as long as the process lives.
            for key in [k for k, times in _rate_buckets.items() if not times or times[-1] < cutoff]:
                _rate_buckets.pop(key, None)
        recent = [t for t in _rate_buckets.get(client_key, []) if t >= cutoff]
        if len(recent) >= _RATE_LIMIT_VOTES:
            _rate_buckets[client_key] = recent
            return True
        recent.append(now)
        _rate_buckets[client_key] = recent
        return False


def record(project_slug: str, page_slug: str, helpful: bool, language: str = "", version: str = "") -> None:
    placeholder = _placeholder()
    values = ", ".join([placeholder] * 6)
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO page_feedback (project_slug, page_slug, language, version, helpful, created_at) "
            f"VALUES ({values})",
            (project_slug, page_slug, language, version, 1 if helpful else 0, datetime.now(timezone.utc).isoformat()),
        )


def summary(project_slug: str = "") -> list[dict]:
    """Counts per page, worst ratio first -- which is the order an author
    wants: the page most readers said did not help is the one to open.

    Pages with no votes at all are absent rather than listed as zeroes. A
    documentation site has many pages and few votes, and a list that is
    mostly empty rows buries the handful that say something.
    """
    placeholder = _placeholder()
    where = f"WHERE project_slug = {placeholder}" if project_slug else ""
    parameters = (project_slug,) if project_slug else ()
    with db.get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT project_slug, page_slug, language, version,
                   SUM(helpful) AS yes,
                   COUNT(*) - SUM(helpful) AS no,
                   MAX(created_at) AS latest
            FROM page_feedback
            {where}
            GROUP BY project_slug, page_slug, language, version
            """,
            parameters,
        ).fetchall()

    results = [
        {
            "project_slug": row[0],
            "page_slug": row[1],
            "language": row[2],
            "version": row[3],
            "helpful": int(row[4] or 0),
            "not_helpful": int(row[5] or 0),
            "total": int(row[4] or 0) + int(row[5] or 0),
            "last_vote": row[6] or "",
        }
        for row in rows
    ]
    # Sorted here rather than in SQL: the ratio is a division by a count that
    # is sometimes 1, and expressing "worst ratio, then most votes" portably
    # across both backends' integer division rules is more trouble than a
    # sort over a list that is, by construction, only as long as the number
    # of pages anyone has voted on.
    results.sort(key=lambda entry: (entry["helpful"] / entry["total"], -entry["total"]))
    return results


def count() -> int:
    with db.get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM page_feedback").fetchone()
    return int(row[0])


def export_all() -> list[dict]:
    """Every vote, one row per answer, for the backup archive (see
    services/backup.py).

    The individual answers rather than summary(): a backup exists to be
    restorable, and counts cannot be un-summed. There is nothing personal in
    a row -- no address, no identifier, no user agent; the table stores which
    page, which answer, and when, and that is all it has ever stored.

    Oldest first, so an archive read by a person reads chronologically and
    two exports of an unchanged table are byte-identical here."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT project_slug, page_slug, language, version, helpful, created_at "
            "FROM page_feedback ORDER BY created_at, id"
        ).fetchall()
    return [
        {
            "project_slug": row[0],
            "page_slug": row[1],
            "language": row[2],
            "version": row[3],
            "helpful": bool(row[4]),
            "created_at": row[5],
        }
        for row in rows
    ]


def clear(project_slug: str, page_slug: str) -> int:
    """Forgets one page's votes, and says how many it forgot.

    Exists because a page that has been rewritten in response to its own
    feedback is being judged on text nobody voted on. Without this the only
    honest thing an author could do is remember to discount the numbers.
    """
    placeholder = _placeholder()
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM page_feedback WHERE project_slug = {placeholder} AND page_slug = {placeholder}",
            (project_slug, page_slug),
        )
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
