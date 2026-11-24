"""A log of what administrators did to the instance itself: accounts, API
tokens, branding and the export.

WHY THIS AND NOT THE ACTIVITY FEED. The documentation's own history is the
content repository: every page change is a commit with a name on it
(services/activity.py reads it). What an administrator does to the
INSTANCE -- creating an account, handing out a token, downloading
everything -- writes no file and so leaves no commit. This is where it is
written down instead.

WHAT IS RECORDED. When, who, from which address, what, and to what
("anna", "token 'CI'"), plus a short detail where one helps ("role:
editor"). Never a password, a token value, or a request body: a log is the
thing that gets pasted into an issue, and the detail strings below are
built by the endpoints from known fields, never copied from input.

HOW NOTHING IS MISSED. Endpoints call record() with a readable entry. The
middleware (auth_guard.py) then records every successful admin-only change
the endpoint did NOT record, as its method and path -- so a route added
later without a call here is still in the log, just less readable.

KEPT: the newest MAX_ENTRIES. An instance's admin actions are a few a week;
this is years of them, and a cap means the table never needs a cleanup job.
"""
from datetime import datetime, timezone

from fastapi import Request

from app.services import db

MAX_ENTRIES = 5000
_DETAIL_MAX = 200


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _actor(request: Request | None) -> str:
    user = getattr(getattr(request, "state", None), "user", None)
    if user:
        return user["username"]
    session = getattr(request, "session", None) if request is not None else None
    try:
        return (session or {}).get("username") or ""
    except AssertionError:  # no SessionMiddleware on this request
        return ""


def _address(request: Request | None) -> str:
    if request is None:
        return ""
    from app.services.client_address import client_address

    try:
        return client_address(request) or ""
    except Exception:  # noqa: BLE001 -- an address is a nicety, never a reason to fail
        return ""


def record(request: Request | None, action: str, target: str = "", detail: str = "") -> None:
    """One entry. Marks the request as logged, so the middleware does not
    add a generic entry for the same change."""
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO admin_log (at, actor, address, action, target, detail) VALUES ({p}, {p}, {p}, {p}, {p}, {p})",
            (_now_iso(), _actor(request), _address(request), action[:80], target[:120], detail[:_DETAIL_MAX]),
        )
        conn.execute(
            "DELETE FROM admin_log WHERE id NOT IN "
            f"(SELECT id FROM admin_log ORDER BY id DESC LIMIT {MAX_ENTRIES})"
        )
    if request is not None and hasattr(request, "state"):
        request.state.admin_logged = True


def entries(limit: int = 100, before: int | None = None) -> list[dict]:
    """Newest first. `before` = an id, for the next page."""
    limit = max(1, min(limit, 500))
    p = _placeholder()
    where, params = ("WHERE id < " + p, (before,)) if before else ("", ())
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, at, actor, address, action, target, detail FROM admin_log {where} "
            f"ORDER BY id DESC LIMIT {limit}",
            params,
        ).fetchall()
    keys = ("id", "at", "actor", "address", "action", "target", "detail")
    return [dict(zip(keys, row, strict=True)) for row in rows]
