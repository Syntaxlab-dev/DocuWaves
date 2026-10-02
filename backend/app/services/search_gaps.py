"""What readers searched for and did not find: the gaps radar.

A search that finds nothing is the clearest signal a documentation site
gets that a page is missing -- the reader said, in their own words, what
they were looking for. This keeps a tally of those words and shows it under
"Insights" in the admin area.

WHAT IS STORED, and only this: the search words (normalised, at most 100
characters), the language and project they were searched in, how often, and
the first and last day. No address, no account, no time of day, no link
between two searches -- a row says "17 searches for 'proxy einrichten'",
never who searched. Rows not seen for 90 days are dropped, and the admin can
clear the list at any time.

WHAT IS NOT RECORDED:
- searches by signed-in accounts: they may be looking for something in a
  private project, and internal words are not reader feedback;
- searches scoped to a private project (the same reason, for a stranger who
  cannot see it anyway -- they get the 404 answer, see visibility.py);
- the search-as-you-type box: it searches every few keystrokes, and "kub",
  "kube", "kuber" are not three gaps. Only the full results page records
  (`record=1` on the request);
- anything that looks like an e-mail address or a long number (a customer
  or order number, a phone number): a search box is where people paste
  things, and those are the things most likely to be personal.

On by default; SEARCH_GAPS=off switches it off entirely (nothing is
written, and the admin list says so).
"""
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from app.services import db
from app.settings import settings

MAX_QUERY_LENGTH = 100
RETENTION_DAYS = 90
# The table is a top list, not a log: past this many distinct searches the
# least recently seen go first.
_MAX_ROWS = 5000
_MIN_QUERY_LENGTH = 2

_PERSONAL = re.compile(r"@|\d{6,}|\d[\d\s/-]{8,}\d")

_RATE_LIMIT = 30
_RATE_WINDOW_SECONDS = 60
_RATE_SWEEP_AT = 2048
_rate_lock = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}


def is_enabled() -> bool:
    return settings.search_gaps_enabled


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def normalise(query: str) -> str:
    """Lower case, inner whitespace collapsed, clipped. "" for anything not
    worth keeping: too short, or looking like personal data."""
    text = " ".join((query or "").split()).lower()[:MAX_QUERY_LENGTH].strip()
    if len(text) < _MIN_QUERY_LENGTH or _PERSONAL.search(text):
        return ""
    return text


def _rate_limited(client_key: str) -> bool:
    """A script hammering the search endpoint must not be able to fill the
    list with its own words. Counted in memory only, like every other rate
    limit here; the key is never written."""
    if not client_key:
        return False
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW_SECONDS
    with _rate_lock:
        if len(_rate_buckets) > _RATE_SWEEP_AT:
            for key in [k for k, t in _rate_buckets.items() if not t or t[-1] < cutoff]:
                _rate_buckets.pop(key, None)
        recent = [t for t in _rate_buckets.get(client_key, []) if t >= cutoff]
        limited = len(recent) >= _RATE_LIMIT
        if not limited:
            recent.append(now)
        _rate_buckets[client_key] = recent
        return limited


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def record(query: str, language: str = "", project_slug: str = "", client_key: str = "") -> bool:
    """Counts one search that found nothing. True when it was counted."""
    if not is_enabled():
        return False
    text = normalise(query)
    if not text or _rate_limited(client_key):
        return False
    p = _placeholder()
    today = _today()
    with db.get_connection() as conn:
        updated = conn.execute(
            f"UPDATE search_gaps SET hits = hits + 1, last_seen = {p} "
            f"WHERE query = {p} AND language = {p} AND project_slug = {p}",
            (today, text, language or "", project_slug or ""),
        )
        if updated.rowcount == 0:
            conn.execute(
                f"INSERT INTO search_gaps (query, language, project_slug, hits, first_seen, last_seen) "
                f"VALUES ({p},{p},{p},1,{p},{p})",
                (text, language or "", project_slug or "", today, today),
            )
            _trim(conn)
    return True


def _trim(conn) -> None:
    p = _placeholder()
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=RETENTION_DAYS)).isoformat()
    conn.execute(f"DELETE FROM search_gaps WHERE last_seen < {p}", (cutoff,))
    count = conn.execute("SELECT COUNT(*) FROM search_gaps").fetchone()[0]
    if count > _MAX_ROWS:
        conn.execute(
            f"DELETE FROM search_gaps WHERE id IN (SELECT id FROM search_gaps ORDER BY last_seen, hits LIMIT {p})",
            (count - _MAX_ROWS,),
        )


def top(limit: int = 50) -> list[dict]:
    """Most searched first; ties by the most recent."""
    p = _placeholder()
    with db.get_connection() as conn:
        _trim(conn)
        rows = conn.execute(
            f"SELECT id, query, language, project_slug, hits, first_seen, last_seen FROM search_gaps "
            f"ORDER BY hits DESC, last_seen DESC LIMIT {p}",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [
        {
            "id": r[0], "query": r[1], "language": r[2], "project_slug": r[3],
            "hits": r[4], "first_seen": r[5], "last_seen": r[6],
        }
        for r in rows
    ]


def forget(gap_id: int | None = None) -> int:
    """Removes one entry (a page now covers it), or -- with no id -- all."""
    p = _placeholder()
    with db.get_connection() as conn:
        if gap_id is None:
            cursor = conn.execute("DELETE FROM search_gaps")
        else:
            cursor = conn.execute(f"DELETE FROM search_gaps WHERE id = {p}", (gap_id,))
    return cursor.rowcount


def reset_rate_limits() -> None:
    """Tests only."""
    with _rate_lock:
        _rate_buckets.clear()
