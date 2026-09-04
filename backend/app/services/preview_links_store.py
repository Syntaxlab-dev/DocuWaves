"""Preview links: a URL that shows ONE unpublished page to somebody who has
no login here, until a date the author picked.

WHAT THIS IS FOR. A draft is written to be read by someone before it goes
live -- the colleague who knows whether the steps are right, the person the
release notes are about. Today the only two states are "in the admin area,
behind the admin password" and "published to the world", and the gap between
them is currently bridged by pasting Markdown into a chat window. This is
that gap, and nothing wider.

WHAT IT DELIBERATELY IS NOT:
- Not an account, and not a step towards one. It reads one page and cannot
  reach anything else -- not the project, not the sidebar, not search, not
  the other drafts in the same category. Multi-user access with roles is its
  own piece of work (see the roadmap), and this must not become a half of it
  that people build habits on.
- Not editable. There is no comment box, no reply, nothing that writes.
- Not permanent. Every link has an expiry date, and there is no "never
  expires" option -- unlike an API token, which an operator configures once
  and uses for years. A preview link is made for a conversation that is over
  in a week, and a link that outlives its reason is exactly the one that
  turns up in a search index or a forwarded email two years later.

WHERE THESE LIVE. In the database, next to `auth`, `sessions` and
`api_tokens`, and for the same reason api_tokens_store.py spells out at
length: this is a CREDENTIAL, and the content repo -- where every page,
image and setting does live -- is a repository whose whole purpose is to be
cloned and read in pull requests. So it is not in _CONTENT_TABLES either: a
reindex, a new image or a re-cloned content repo leave live preview links
alone.

WHAT IS STORED. The SHA-256 hash of the token, never the token. The
plaintext exists once, in the answer to the create call, and is
unrecoverable afterwards -- losing it means making another link, which
costs a click. Same trade as api_tokens_store, same reasoning: the value is
32 bytes out of `secrets`, so there is nothing for a slow hash to protect.

WHAT A LINK POINTS AT. A project slug, a page slug, a language and a
documentation version -- not a page id. Page ids are reassigned by every
full reindex of the content repo (see content_sync.py), so a numeric
reference would quietly repoint an old link at a completely different page.
A rename moves the slug, so the links move with it (repoint_page, called
from pages_store.update_page): somebody who fixed a typo in a title should
not have to re-send every link they handed out. Deleting the page takes its
links with it instead (revoke_for_page) -- there is nothing left to preview,
and a leftover row would hand a live link to whatever page reuses the slug
next.
"""

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone

from app.services import db

# Recognizable in a log or a leaked paste as a DocuWaves preview link, the
# same way `dwt_` marks an API token -- and distinct from it, so the two can
# never be confused for one another by a person or by a secret scanner.
TOKEN_PREFIX = "dwp_"

_TOKEN_BYTES = 32

# How long a link may last. The upper bound is not arbitrary caution: the
# thing being shared is unfinished writing, and a year-long link to it is a
# publication nobody decided to make.
MIN_DAYS = 1
MAX_DAYS = 90
DEFAULT_DAYS = 7

# Per page. Someone sharing one draft with a handful of reviewers needs a
# few; a page accumulating dozens means nothing is ever being revoked, and
# verify() below scans the table on every request.
MAX_LINKS_PER_PAGE = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(_TOKEN_BYTES)


def looks_like_token(value: str) -> bool:
    return value.startswith(TOKEN_PREFIX)


def url_path(token: str) -> str:
    """The reader-facing path a token belongs in. One place, because the
    frontend route (App.tsx) and this have to agree exactly, and the admin
    UI builds the link it hands the author out of what this returns."""
    return f"/preview/{token}"


def clamp_days(days: int) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(MIN_DAYS, min(MAX_DAYS, value))


def is_expired(expires_at: str, today: date | None = None) -> bool:
    """A link expires at the END of its date, like an API token: one made to
    last until 2026-09-11 works for all of 2026-09-11.

    An unparseable value counts as expired. The only way this column holds
    something else is a hand-edited database, and the safe reading of a
    broken expiry on a credential is that it is over."""
    if not expires_at:
        return True
    try:
        return (today or datetime.now(timezone.utc).date()) > date.fromisoformat(expires_at)
    except ValueError:
        return True


_COLUMNS = "id, project_slug, page_slug, language, version, created_at, expires_at, created_by"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "project_slug": row[1],
        "page_slug": row[2],
        "language": row[3],
        "version": row[4],
        "created_at": row[5],
        "expires_at": row[6],
        "created_by": row[7],
    }


def sweep_expired(today: date | None = None) -> int:
    """Deletes links whose date has passed. Called when links are listed and
    before one is created -- there is no background job in this app, and
    those are the two moments anything cares. An expired row is refused by
    verify() whether or not it has been swept; this is housekeeping, not the
    check."""
    cutoff = (today or datetime.now(timezone.utc).date()).isoformat()
    with db.get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM preview_links WHERE expires_at < {_placeholder()}", (cutoff,))
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def list_for_page(project_slug: str, page_slug: str, language: str, version: str) -> list[dict]:
    """The live links for exactly one translation of one page, newest first.
    Never the token hash: the admin UI has no use for it, and a value that
    does not leave this module cannot leak through an endpoint that forgot
    to strip it."""
    sweep_expired()
    p = _placeholder()
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM preview_links WHERE project_slug = {p} AND page_slug = {p} "
            f"AND language = {p} AND version = {p} ORDER BY id DESC",
            (project_slug, page_slug, language, version),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create(project_slug: str, page_slug: str, language: str, version: str, days: int, created_by: str) -> dict | None:
    """A new link, or None when this page already has MAX_LINKS_PER_PAGE of
    them -- which is a caller who should revoke one, not a limit to raise.

    The returned dict is the ONLY time the token itself is readable."""
    # list_for_page() sweeps expired rows first, so the count this decides on
    # is a count of links that still work.
    existing = list_for_page(project_slug, page_slug, language, version)
    if len(existing) >= MAX_LINKS_PER_PAGE:
        return None
    token = generate_token()
    expires_at = (datetime.now(timezone.utc).date() + timedelta(days=clamp_days(days))).isoformat()
    created_at = _now_iso()
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO preview_links (token_hash, project_slug, page_slug, language, version, created_at, "
            f"expires_at, created_by) VALUES ({p},{p},{p},{p},{p},{p},{p},{p})",
            (hash_token(token), project_slug, page_slug, language, version, created_at, expires_at, created_by),
        )
    return {"token": token, "url_path": url_path(token), "expires_at": expires_at}


def revoke(link_id: int) -> bool:
    with db.get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM preview_links WHERE id = {_placeholder()}", (link_id,))
        return bool(cursor.rowcount)


def repoint_page(project_slug: str, old_slug: str, new_slug: str, version: str) -> int:
    """Follows a page whose slug changed, so links handed out before the
    rename keep working.

    Safe precisely because it is called from the rename itself: this is not
    a guess about which page an old slug used to mean, it is the one write
    that knows. Every translation moves together, as it must -- a page's
    slug is shared by all of them (see content_files.relocate_page), so
    there is no per-language case to consider here."""
    if old_slug == new_slug:
        return 0
    p = _placeholder()
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE preview_links SET page_slug = {p} WHERE project_slug = {p} AND page_slug = {p} "
            f"AND version = {p}",
            (new_slug, project_slug, old_slug, version),
        )
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def revoke_for_page(project_slug: str, page_slug: str, version: str) -> int:
    """Every link to any translation of this page, gone. Called when the page
    is DELETED: the page is not there any more, so neither is anything that
    was pointing at it, and leaving the rows behind would mean a slug that
    somebody later reuses inherits an old link."""
    p = _placeholder()
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM preview_links WHERE project_slug = {p} AND page_slug = {p} AND version = {p}",
            (project_slug, page_slug, version),
        )
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def verify(presented: str) -> dict | None:
    """What this token points at, or None -- the single answer for "no such
    link", "revoked" and "expired" alike, exactly as api_tokens_store.verify
    answers for its own three cases. Whoever holds a link that no longer
    works learns only that it does not work.

    Rows are scanned and compared with hmac.compare_digest rather than looked
    up by hash, for the reason the token module gives: constant-time
    comparison of a secret-derived value is a rule better kept without
    exceptions. MAX_LINKS_PER_PAGE plus sweep_expired() keep the scan small.

    There is no rate limit here and none is needed: the token is 32 bytes of
    urandom, and a limit keyed on the presented value would hand an attacker
    a fresh bucket per guess anyway (again, see api_tokens_store)."""
    if not presented or not looks_like_token(presented):
        return None
    digest = hash_token(presented)
    with db.get_connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS}, token_hash FROM preview_links").fetchall()
    for row in rows:
        if hmac.compare_digest(str(row[8]), digest):
            record = _row_to_dict(row)
            return None if is_expired(record["expires_at"]) else record
    return None
